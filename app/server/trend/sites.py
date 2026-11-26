"""수집 채널과 외부 출처 허용 목록."""

import re
from urllib.parse import SplitResult, parse_qs, unquote, urlencode, urljoin, urlsplit, urlunsplit

GOOGLE_RSS = "https://trends.google.com/trending/rss?geo=KR"
GOOGLE_TRENDS = "https://trends.google.com/trends/explore"
NAVER_HOME = "https://datalab.naver.com/"
NAVER_FOOD_ID = "50000006"

BGF_NEWSROOM = "https://origin.bgf.co.kr/bgflive/detail/?category=pr"
LOTTE_NEWSROOM = "https://company.lottechilsung.co.kr/kor/company/news/list.do"
SHINSEGAE_RSS = "https://www.shinsegaegroupnewsroom.com/?" + urlencode({"s": "음료", "feed": "rss2"})
SHINSEGAE_POSTS = "https://www.shinsegaegroupnewsroom.com/wp-json/wp/v2/posts"

PRESS_PHOTO_PATHS = {
    "bgf": {"origin.bgf.co.kr": "/assets/upload/image/"},
    "lotte": {"company.lottechilsung.co.kr": "/image/"},
    "shinsegae": {
        "www.shinsegaegroupnewsroom.com": "/wp-content/uploads/",
        "images.shinsegaegroupnewsroom.com": "/wp-content/uploads/",
    },
}
PHOTO_SUFFIX = re.compile(r"\.(?:jpe?g|png|webp|avif)$", re.I)
GENERIC_PHOTO = re.compile(r"logo|placeholder|favicon|default|spacer|blank", re.I)

PUBLISHERS = {
    "origin.bgf.co.kr": "BGF리테일",
    "company.lottechilsung.co.kr": "롯데칠성음료",
    "www.shinsegaegroupnewsroom.com": "신세계그룹 뉴스룸",
    "www.yna.co.kr": "연합뉴스",
    "www.yonhapnewstv.co.kr": "연합뉴스TV",
    "www.etnews.com": "전자신문",
    "m.ekn.kr": "에너지경제신문",
    "www.asiatime.co.kr": "아시아타임즈",
    "www.newsis.com": "뉴시스",
    "www.news1.kr": "뉴스1",
    "www.mk.co.kr": "매일경제",
    "www.hankyung.com": "한국경제",
    "www.edaily.co.kr": "이데일리",
    "www.hani.co.kr": "한겨레",
    "www.donga.com": "동아일보",
    "ir.newspim.com": "뉴스핌",
    "blog.google": "구글코리아",
    "trends.google.com": "구글 트렌드",
    "datalab.naver.com": "네이버 데이터랩",
}


def publisher(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme == "https":
            return PUBLISHERS.get(parsed.hostname)
    except ValueError:
        pass
    return None


def _clean_https(url: str) -> SplitResult | None:
    try:
        parsed = urlsplit(url)
        if (parsed.scheme == "https" and parsed.hostname and parsed.port is None
                and parsed.username is None and parsed.password is None):
            return parsed
    except ValueError:
        pass
    return None


def article_site(url: str) -> str | None:
    parsed = _clean_https(url)
    if parsed is None:
        return None
    query = parse_qs(parsed.query)
    if parsed.hostname == "origin.bgf.co.kr" and parsed.path in ("/bgflive/view", "/bgflive/view/"):
        if re.fullmatch(r"[0-9]+", query.get("id", [""])[0]):
            return "bgf"
    if parsed.hostname == "company.lottechilsung.co.kr" and parsed.path == "/kor/company/news/view.do":
        if re.fullmatch(r"[0-9]+", query.get("detailsKey", [""])[0]):
            return "lotte"
    if parsed.hostname == "www.shinsegaegroupnewsroom.com" and re.fullmatch(r"/[\w%-]+/?", parsed.path):
        return "shinsegae"
    return None


def press_photo(article_url: str, value: str) -> str | None:
    site = article_site(article_url)
    value = value.strip()
    if site is None or not value or "\\" in value or any(c in value for c in "\r\n\t"):
        return None
    url = urljoin(article_url, value)
    # 일부 롯데칠성 원문은 같은 보도사진을 HTTP로 적는다. 확인된 호스트와 경로에서 HTTPS로 제공한다.
    if site == "lotte" and url.startswith("http://"):
        url = "https://" + url.removeprefix("http://")
    parsed = _clean_https(url)
    if parsed is None:
        return None
    path = unquote(parsed.path)
    prefix = PRESS_PHOTO_PATHS[site].get(parsed.hostname)
    if (not prefix or not path.startswith(prefix) or not PHOTO_SUFFIX.search(path)
            or "\\" in path or any(part in (".", "..") for part in path.split("/"))
            or GENERIC_PHOTO.search(path.rsplit("/", 1)[-1])):
        return None
    return urlunsplit(parsed._replace(fragment=""))
