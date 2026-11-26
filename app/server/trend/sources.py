"""브라우저나 모델 호출 없이 공개 검색·뉴스룸에서 최근 신호를 모은다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
import ssl
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from lxml import etree, html

from tools import web
from . import newsroom, sites
from .stories import reference

SEOUL = ZoneInfo("Asia/Seoul")
GOOGLE_NS = {"ht": "https://trends.google.com/trending/rss"}
FOOD = re.compile(
    r"음료|음식|디저트|제과|편의점|식품|간편식|빵집|도시락|김밥|커피|라[테떼]|카페|베이커리|팝콘|간식|과자|스무디|"
    r"과일|아메리카노|피스타치오|케이크|초콜릿|브런치|제철|샌드위치|주스|티백|초코|맥주|"
    r"위스키|와인|샴페인|하이볼|녹차|말차|생수|탄산|식빵|젤리|라면|너구리|농심|삼양식품|스낵|소르베|쿠키"
)
MAX_BYTES = 2_000_000
MAX_AGE = timedelta(days=45)
LOTTE_INTERMEDIATE = Path(__file__).with_name("globalsign-gcc-r3-dv-tls-ca-2020.pem")


def now_seoul() -> datetime:
    return datetime.now(SEOUL)


class _OfficialRedirect(HTTPRedirectHandler):
    def __init__(self, site: str):
        self.site = site

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if sites.article_site(newurl) != self.site:
            raise URLError("뉴스룸의 공식 기사 밖으로 이동했어요")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, headers: dict | None = None, *, official_site: str | None = None) -> bytes:
    if official_site and sites.article_site(url) != official_site:
        raise ValueError("뉴스룸의 공식 기사 주소가 아니에요")
    request = Request(url, headers={"User-Agent": "ax-trend-feed/1.0", **(headers or {})})
    if official_site:
        def open_request(context=None):
            return build_opener(_OfficialRedirect(official_site), HTTPSHandler(context=context)).open(request, timeout=6)
    else:
        def open_request(context=None):
            return urlopen(request, timeout=6, context=context)

    try:
        response = open_request()
    except URLError as error:
        if (urlsplit(url).hostname != urlsplit(sites.LOTTE_NEWSROOM).hostname
                or not isinstance(error.reason, ssl.SSLCertVerificationError)):
            raise
        # 이 뉴스룸의 서버가 빠뜨린 공개 중간 인증서만 보완한다. 시스템 루트와 호스트 검증은 유지한다.
        # https://secure.globalsign.com/cacert/gsgccr3dvtlsca2020.crt
        context = ssl.create_default_context()
        context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
        context.load_verify_locations(cafile=LOTTE_INTERMEDIATE)
        response = open_request(context)
    with response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("수집 문서의 크기 제한을 넘었어요")
    return payload


def _time(raw: str) -> datetime:
    value = parsedate_to_datetime(raw)
    if value.tzinfo is None:
        raise ValueError("출처 날짜에 시간대가 없어요")
    return value.astimezone(SEOUL)


def _nodes(payload: bytes) -> list[ET.Element]:
    channel = ET.fromstring(payload).find("channel")
    if channel is None:
        raise ValueError("RSS 채널을 읽지 못했어요")
    return channel.findall("item")


def _google_context(item: ET.Element) -> dict | None:
    for article in item.findall("ht:news_item", GOOGLE_NS):
        title = (article.findtext("ht:news_item_title", "", GOOGLE_NS) or "").strip()
        link = (article.findtext("ht:news_item_url", "", GOOGLE_NS) or "").strip()
        publisher = sites.publisher(link)
        if FOOD.search(title) and publisher:
            return reference(f"{publisher}, 구글 트렌드 관련 기사", None, title, link)
    return None


def google_topics(now: datetime) -> list[dict]:
    items = _nodes(fetch(sites.GOOGLE_RSS))
    if not items:
        raise ValueError("급상승 검색어가 비어 있어요")
    rows = []
    seen = set()
    for item in items:
        topic = (item.findtext("title") or "").strip()
        try:
            when = _time(item.findtext("pubDate") or "")
        except (ValueError, TypeError, OverflowError):
            continue
        context = _google_context(item)
        if (not topic or topic.casefold() in seen or not (FOOD.search(topic) or context)
                or not now - timedelta(days=2) <= when <= now):
            continue
        seen.add(topic.casefold())
        link = sites.GOOGLE_TRENDS + "?" + urlencode({"geo": "KR", "q": topic, "hl": "ko"})
        traffic = item.findtext("ht:approx_traffic", "", GOOGLE_NS).strip()
        rows.append({
            "topic": topic, "when": when.isoformat(), "url": link, "context": context,
            "label": f"표시 검색량 {traffic}" if traffic else "급상승 검색어",
        })
    return rows


def _text(node) -> str:
    return " ".join(node.text_content().split())


def _naver_days(payload: bytes) -> dict[date, dict[str, tuple[int, str]]]:
    page = html.fromstring(payload.decode("utf-8-sig"))
    # 분류 쿠키가 적용됐는지 확인해 의류 등 기본 분류의 순위를 섞지 않는다.
    if not page.xpath(f"//*[@data-default-cid='{sites.NAVER_FOOD_ID}']"):
        raise ValueError("네이버 식품 분류를 확인하지 못했어요")
    days = {}
    for column in page.find_class("keyword_rank"):
        date_cells = column.find_class("title_cell")
        if not date_cells:
            continue
        date_match = re.search(r"\d{4}\.\d{2}\.\d{2}", _text(date_cells[0]))
        if not date_match:
            continue
        day = date.fromisoformat(date_match[0].replace(".", "-"))
        ranks = {}
        for row in column.xpath(".//ul[contains(@class, 'rank_list')]//a[@href]"):
            titles, numbers = row.find_class("title"), row.find_class("num")
            if not titles or not numbers:
                continue
            topic, raw_rank = _text(titles[0]), _text(numbers[0])
            if not raw_rank.isdecimal():
                continue
            rank = int(raw_rank)
            link = urljoin(sites.NAVER_HOME, row.get("href"))
            if topic and 1 <= rank <= 10 and sites.publisher(link):
                ranks[topic] = (rank, link)
        if ranks:
            days[day] = ranks
    return days


def naver_topics(now: datetime) -> list[dict]:
    payload = fetch(sites.NAVER_HOME, {"Cookie": f"_datalab_cid={sites.NAVER_FOOD_ID}"})
    days = {d: ranks for d, ranks in _naver_days(payload).items() if d <= now.date()}
    if not days or (now.date() - max(days)).days > 2:
        raise ValueError("네이버 식품 분류의 최근 순위를 확인하지 못했어요")
    latest = max(days)
    week = [latest - timedelta(days=n) for n in range(6, -1, -1)]
    previous = days.get(latest - timedelta(days=1))
    rows = []
    for topic, (rank, url) in sorted(days[latest].items(), key=lambda entry: entry[1][0]):
        previous_rank = previous[topic][0] if previous and topic in previous else None
        label = f"식품 {rank}위"
        if previous_rank is not None:
            delta = previous_rank - rank
            movement = "상승" if delta > 0 else "하락"
            label += f", 전날보다 {abs(delta)}계단 {movement}" if delta else ", 전날과 같음"
        elif previous is not None:
            label += ", 전날 10위 밖"
        rows.append({
            "topic": topic, "week": [
                {"day": d.isoformat(), "rank": days[d][topic][0] if topic in days[d] else None}
                for d in week if d in days
            ],
            "label": label, "rank": rank, "previousRank": previous_rank, "url": url,
            "when": f"{latest.isoformat()}T00:00:00+09:00",
        })
    return rows


def article(title: str, url: str, day: date, keyword: str | None = None) -> dict | None:
    source = sites.publisher(url)
    if not source or not title:
        return None
    pub_date = day.isoformat()
    return {
        "id": "news-" + sha256(url.encode()).hexdigest()[:12],
        "title": title, "keyword": keyword or title, "url": url,
        "publisher": source, "source": "web", "date": pub_date, "verdict": None,
        "summary": None, "image": None, "alt": None, "photoCredit": None,
        "sources": [reference(source, pub_date, title, url)],
    }


def _complete_news(rows: list[dict], site: str, rss_items: dict[str, ET.Element] | None = None) -> list[dict]:
    ordered = sorted(rows, key=lambda row: row["date"], reverse=True)
    distinct = {}
    for row in ordered:
        distinct.setdefault(article_key(row["url"]), row)
    latest = list(distinct.values())[:newsroom.STORIES_PER_NEWSROOM]

    def load(row):
        if rss_items and row["url"] in rss_items:
            newsroom.from_rss(row, rss_items[row["url"]])
        if row["summary"] and row["image"]:
            return row
        try:
            return newsroom.from_article(row, fetch(row["url"], official_site=site), site)
        except (OSError, etree.LxmlError, ValueError):
            return row

    if not latest:
        return []
    with ThreadPoolExecutor(max_workers=len(latest)) as pool:
        return list(pool.map(load, latest))


def _newsroom_html(now: datetime, url: str, site: str, selectors: tuple[str, str, str]) -> list[dict]:
    page = html.fromstring(fetch(url).decode("utf-8-sig"))
    anchor_xpath, title_xpath, date_xpath = selectors
    links = page.xpath(anchor_xpath)
    if not links:
        raise ValueError("뉴스룸에서 보도자료 목록을 읽지 못했어요")
    rows = []
    for anchor in links:
        titles = anchor.xpath(title_xpath)
        dates = anchor.xpath(date_xpath)
        if not titles or not dates:
            continue
        title = _text(titles[0])
        if not FOOD.search(title):
            continue
        link = urljoin(url, anchor.get("href"))
        if sites.article_site(link) != site:
            continue
        raw = _text(dates[0])
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", raw):
            raw = "20" + raw
        try:
            day = date.fromisoformat(raw.replace(".", "-"))
        except ValueError:
            continue
        if now.date() - MAX_AGE <= day <= now.date() and (row := article(title, link, day)):
            rows.append(row)
    return _complete_news(rows, site)


def bgf_news(now: datetime) -> list[dict]:
    return _newsroom_html(now, sites.BGF_NEWSROOM, "bgf", (
        "//li[@class='pr']/a[@href]", ".//div[@class='txt']/p[1]", ".//h3/span",
    ))


def lotte_news(now: datetime) -> list[dict]:
    return _newsroom_html(now, sites.LOTTE_NEWSROOM, "lotte", (
        "//a[@class='list' and contains(@href, 'detailsKey=')]",
        ".//p[@class='tit']", ".//p[@class='listDate']",
    ))


def _shinsegae_latest(now: datetime) -> list[dict]:
    after = (now.astimezone(SEOUL).date() - timedelta(days=3)).isoformat() + "T00:00:00"
    url = sites.SHINSEGAE_POSTS + "?" + urlencode({
        "after": after, "per_page": 100, "_fields": "date_gmt,title,link",
    })
    posts = json.loads(fetch(url))
    if not isinstance(posts, list):
        raise ValueError("뉴스룸의 최신 발표 목록을 읽지 못했어요")
    distinct = {}
    for post in posts:
        try:
            title = unescape(post["title"]["rendered"]).strip()
            link = post["link"]
            published = datetime.fromisoformat(post["date_gmt"]).replace(tzinfo=UTC)
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        day = published.astimezone(SEOUL).date()
        if (published > now or day < now.date() - MAX_AGE or not FOOD.search(title)
                or sites.article_site(link) != "shinsegae"):
            continue
        # 같은 발표의 사진 페이지들에도 날짜와 제목이 붙는다. 목록에 있는 대표 기사 주소를 우선한다.
        key = (day, title)
        if key not in distinct or len(link) < len(distinct[key]["url"]):
            distinct[key] = article(title, link, day)
    return list(distinct.values())


def shinsegae_news(now: datetime) -> list[dict]:
    try:
        recent = _shinsegae_latest(now)
    except (OSError, ValueError):
        recent = None
    try:
        items = _nodes(fetch(sites.SHINSEGAE_RSS))
    except (OSError, ValueError, ET.ParseError):
        if recent is None:
            raise
        items = []
    rows = []
    rss_items = {}
    for item in items:
        title = item.findtext("title", "").strip()
        url = item.findtext("link", "").strip()
        if not FOOD.search(title) or sites.article_site(url) != "shinsegae":
            continue
        try:
            published = _time(item.findtext("pubDate") or "")
            day = published.date()
        except (ValueError, TypeError, OverflowError):
            continue
        if published <= now and now.date() - MAX_AGE <= day and (row := article(title, url, day)):
            rows.append(row)
            rss_items.setdefault(url, item)
    return _complete_news([*(recent or []), *rows], "shinsegae", rss_items)


def cached_news(keywords: list[str], today: date) -> list[dict]:
    """기존 흐름 찾기에서 저장한 출처와 날짜가 있는 주장을 다시 쓴다."""
    rows = []
    for keyword in dict.fromkeys(keywords):
        try:
            claims = web.filter_claims(web.load(keyword) or [], today=today)
        except (OSError, TypeError, ValueError, AttributeError):
            continue
        for claim in claims:
            if claim.date is None:
                continue
            day = date.fromisoformat(claim.date)
            row = article(claim.text, claim.url, day, keyword)
            if row and today - MAX_AGE <= day <= today:
                rows.append(row)
    return rows


def collect(now: datetime) -> tuple[dict, dict]:
    loaders = {
        "google": google_topics, "naver": naver_topics,
        "bgf": bgf_news, "lotte": lotte_news, "shinsegae": shinsegae_news,
    }
    with ThreadPoolExecutor(max_workers=len(loaders)) as pool:
        futures = {name: pool.submit(load, now) for name, load in loaders.items()}
        results = {}
        for name, future in futures.items():
            try:
                results[name] = {"ok": True, "rows": future.result()}
            except (OSError, ET.ParseError, etree.LxmlError, ValueError, TypeError, KeyError):
                results[name] = {"ok": False, "rows": []}
    channels = {name: results.pop(name) for name in ("google", "naver")}
    return channels, results


def article_key(url: str) -> tuple[str, str, tuple]:
    """공식 링크에서 쿼리의 순서와 유입 표시를 걷어낸다."""
    parsed = urlsplit(url)
    query = tuple(sorted((k, v) for k, v in parse_qsl(parsed.query) if not k.startswith("utm_")))
    return parsed.netloc, parsed.path.rstrip("/"), query
