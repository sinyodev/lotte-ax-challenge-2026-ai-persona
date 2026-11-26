"""W2 판정과 공개 자료 수집, 발행 약속을 만든 자료로 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import json
from threading import Event

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import onsite
import trend
from routes import trend as trend_route
from tools import web
from trend import editorial, newsroom, publishing, sites, sources


def test_verdict_uses_matching_months_and_keeps_all_stages(monkeypatch):
    rows = []
    for year in (2024, 2025):
        for month in range(1, 13):
            def row(keyword, search, mentions=100, ads=0.15):
                return {
                    "month": f"{year}-{month:02d}", "keyword": keyword, "search_index": search,
                    "sns_mentions": mentions, "sns_organic": mentions * (1 - ads), "ad_share": ads,
                }

            seasonal = (100 if year == 2024 else 54) if month == 7 else 8
            spike = year == 2025 and month == 7
            rows += [
                row("유자 소다", seasonal),
                row("얼그레이 주스", 63 if year == 2025 else 30, 700 if spike else 100, 0.75 if spike else 0.15),
                row("라임티", 35 + month % 3),
            ]
    tables = {
        "trend": list(reversed(rows)),
        "trend_related": [
            {"keyword": "유자소다", "related": "유자소다 편의점 가격", "share": 0.25},
            {"keyword": "유자소다", "related": "유자소다 제품 만드는 법", "share": 0.75},
        ],
        "trend_volume": [{"keyword": "유자 소다", "searches_at_100": 3500}],
    }
    monkeypatch.setattr(onsite, "available", lambda: True)
    monkeypatch.setattr(onsite, "load", tables.__getitem__)

    seasonal = trend.verdict(" 유자소다 ")
    assert seasonal["stage"] == ["피크아웃", "계절성 수요"]
    assert seasonal["series"][0]["month"] == "2024-01"
    assert seasonal["series"][-1]["month"] == "2025-12"
    assert seasonal["product_search_share"] == 0.25
    assert len(seasonal["related"]) == 2
    assert any("3,500" in line for line in seasonal["reasons"])

    viral = trend.verdict("얼그레이 주스")
    assert set(viral["stage"]) == {"광고성 바이럴", "상승기"}
    assert viral["ad_share_peak"] == 0.75
    assert viral["product_search_share"] is None
    assert trend.verdict("라임티")["stage"] == ["안정기"]


def test_verdict_without_onsite_data():
    assert trend.verdict("유자소다") == {
        "keyword": "유자소다", "stage": [], "reasons": [], "series": [], "ad_share_peak": None,
        "product_search_share": None, "related": [], "source": "internal",
    }


def test_public_google_and_naver_discover_topics_from_documents(monkeypatch):
    rss = """<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
      <item><title>멜팅퐁</title><pubDate>Thu, 15 Jan 2026 21:15:00 -0800</pubDate>
      <ht:approx_traffic>700+</ht:approx_traffic><ht:news_item>
      <ht:news_item_title>새 디저트 ‘멜팅퐁’, 수제 소르베를 선보여</ht:news_item_title>
      <ht:news_item_url>https://www.yna.co.kr/example</ht:news_item_url>
      </ht:news_item></item>
      <item><title>오픈광고</title><pubDate>Thu, 15 Jan 2026 21:30:00 -0800</pubDate>
      <ht:news_item><ht:news_item_title>편의점 광고</ht:news_item_title>
      <ht:news_item_url>https://threads.net/@brand/post/12</ht:news_item_url></ht:news_item></item>
      <item><title>축구</title><pubDate>Thu, 15 Jan 2026 22:45:00 -0800</pubDate></item>
      <item><title>녹차</title><pubDate>Mon, 12 Jan 2026 22:00:00 -0800</pubDate></item>
    </channel></rss>"""
    rank_list = []
    for d in range(9, 16):
        rank_list.append(
            f'<div class="keyword_rank"><span class="title_cell">2026.01.{d:02d}</span>'
            f'<ul class="rank_list"><li><a href="/shoppingInsight/sKeyword.naver?keyword=quince">'
            f'<span class="title">모과</span><em class="num">{2 if d == 15 else 5}</em></a></li></ul></div>'
        )
    page = '<div data-default-cid="50000006"></div>' + "".join(rank_list)

    def fetch(url, headers=None):
        if url == sites.GOOGLE_RSS:
            return rss.encode()
        assert url == sites.NAVER_HOME
        assert headers == {"Cookie": "_datalab_cid=50000006"}
        return page.encode("utf-8")

    monkeypatch.setattr(sources, "fetch", fetch)
    now = datetime(2026, 1, 16, 16, 0, tzinfo=sources.SEOUL)
    google, = sources.google_topics(now)
    assert google["topic"] == "멜팅퐁" and not sources.FOOD.search(google["topic"])
    assert google["label"] == "표시 검색량 700+"
    issue = editorial.choose_issue(now.date(), {
        "google": {"ok": True, "rows": [google]}, "naver": {"ok": True, "rows": []},
    }, [], set())
    assert issue["topic"] == "멜팅퐁" and issue["title"] == "구글에서 ‘멜팅퐁’ 검색이 급상승했어요"
    assert "수제 소르베를 선보여" in issue["observation"]
    assert any(ref["url"] == "https://www.yna.co.kr/example" for ref in issue["sources"])
    assert "편의점 간식 매대" in issue["question"] and issue["menu"] is None
    naver, = sources.naver_topics(now)
    assert naver["topic"] == "모과"
    assert naver["rank"] == 2 and naver["previousRank"] == 5
    assert len(naver["week"]) == 7
    assert "3계단 상승" in naver["label"]
    with pytest.raises(ValueError):
        sources._naver_days(page.replace("50000006", "50000000").encode())


@pytest.fixture
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_TREND_DIR", str(tmp_path / "trend"))


def _ranked_topic(day: date, topic: str) -> dict:
    yesterday = day - timedelta(days=1)
    return {
        "topic": topic, "when": yesterday.isoformat() + "T00:00:00+09:00", "rank": 2, "previousRank": 4,
        "url": sites.NAVER_HOME,
        "week": [{"day": (day - timedelta(days=i)).isoformat(), "rank": 2 if i == 1 else 4}
                 for i in range(7, 0, -1)],
    }


def _channels(now, topic):
    return {
        "google": {"ok": True, "rows": []},
        "naver": {"ok": True, "rows": [_ranked_topic(now.date(), topic)]},
    }


def test_publication_slot_is_0830_korean_time():
    before = datetime.fromisoformat("2026-01-16T23:29:59+00:00")
    at = datetime.fromisoformat("2026-01-16T23:30:00+00:00")
    assert publishing.publication_slot(before).isoformat() == "2026-01-16T08:30:00+09:00"
    assert publishing.publication_slot(at).isoformat() == "2026-01-17T08:30:00+09:00"


def test_concurrent_publication_deduplicates_and_retains_past_issue(monkeypatch, isolated_store):
    first = datetime(2026, 1, 16, 8, 30, tzinfo=sources.SEOUL)
    collected = []

    def collector(now):
        collected.append(now.date())
        if now.date() <= date(2026, 1, 17):
            return _channels(now, "모과"), {}
        return {name: {"ok": False, "rows": []} for name in publishing.CHANNEL_NAMES}, {}

    monkeypatch.setattr(sources, "collect", collector)
    with ThreadPoolExecutor(max_workers=4) as executors:
        receipts = list(executors.map(publishing.publish, [first] * 4))
    assert receipts.count(True) == 1
    assert collected == [first.date()]

    initial = publishing.tracking(first)
    issue = initial["edition"]["issue"]
    assert issue["topic"] == "모과"
    assert issue["sources"][0]["source"] == "네이버 데이터랩"
    assert issue["menu"] is None
    assert "4위에서 최신 2위로" in issue["observation"]
    assert "같은 가격·용량의 기존 과일 음료" in issue["question"]
    assert initial["nextAt"] == "2026-01-17T08:30:00+09:00"

    repeated = first + timedelta(days=1)
    assert publishing.publish(repeated)
    assert publishing.tracking(repeated)["edition"]["issue"] == issue

    outage = repeated + timedelta(days=1)
    assert publishing.publish(outage)
    result = publishing.tracking(outage)["edition"]
    assert result["day"] == "2026-01-18"
    assert not result["channels"]["google"]["ok"] and not result["channels"]["naver"]["ok"]
    assert result["issue"] == issue
    assert publishing.feed_packet(outage)["collected_at"] == repeated.isoformat()


def test_new_public_topic_can_replace_a_previously_published_topic(monkeypatch, isolated_store):
    first = datetime(2026, 1, 16, 8, 30, tzinfo=sources.SEOUL)
    second = first + timedelta(days=1)
    monkeypatch.setattr(sources, "collect", lambda now: (_channels(now, "모과" if now == first else "오미자"), {}))
    assert publishing.publish(first)
    assert publishing.publish(second)
    assert publishing.tracking(second)["edition"]["issue"]["topic"] == "오미자"


def test_refresh_uses_shared_web_cache_and_excludes_social_links(monkeypatch, isolated_store):
    now = datetime(2026, 11, 24, 8, 30, tzinfo=sources.SEOUL)
    calls = []

    def collector(at):
        calls.append(at)
        return _channels(at, "모과"), {}

    monkeypatch.setattr(sources, "collect", collector)
    web.save("모과", [
        {"claim": "모과차 신제품을 선보였어요.", "source": "신세계", "date": "2026-11-23",
         "url": "https://www.shinsegaegroupnewsroom.com/example/"},
        {"claim": "임의 계정의 모과차 소식", "source": "Threads", "date": "2026-11-24",
         "url": "https://threads.com/@example/post/12"},
        {"claim": "임의 계정의 모과차 소식", "source": "Mastodon", "date": "2026-11-24",
         "url": "https://mastodon.social/@example/12"},
    ])
    packet = publishing.refresh(now)
    assert packet["collected_at"] == now.isoformat()
    assert packet == publishing.refresh(now + timedelta(seconds=1))
    assert publishing.publish(now + timedelta(seconds=1))
    assert calls == [now]
    assert any(row["title"] == "모과차 신제품을 선보였어요." for row in packet["items"])
    assert not any("임의 계정" in row["title"] for row in packet["items"])


def test_router_serves_approved_press_photos_and_source_evidence(monkeypatch, isolated_store):
    now = datetime(2026, 11, 24, 15, tzinfo=sources.SEOUL)
    monkeypatch.setattr(sources, "now_seoul", lambda: now)
    app = FastAPI()
    app.include_router(trend_route.router)
    client = TestClient(app)
    feed = client.get("/api/trends").json()
    assert feed["collected_at"] is None
    assert [item["id"] for item in feed["items"]] == [
        "evening-decaf", "frozen-smoothie", "dolce-latte", "dubai-desserts",
    ]
    for story in feed["items"]:
        image = client.get(story["image"])
        assert image.status_code == 200 and image.headers["content-type"].startswith("image/")
        assert story["sources"] and story["verdict"] is None
    assert len(feed["items"][-1]["sources"]) == 4
    assert client.get("/api/trends/photos/unknown").status_code == 404

    tracking = client.get("/api/trends/tracking").json()
    assert tracking["edition"]["collectedAt"] is None
    issue = tracking["edition"]["issue"]
    assert issue["id"] == "apple-tea" and issue == editorial.approved_edition(now.date())
    assert client.get(issue["image"]).headers["content-type"] == "image/webp"
    assert client.get("/api/trends/유자소다").json()["series"] == []


def test_lifespan_publishes_without_any_browser_or_request(monkeypatch, isolated_store):
    now = datetime(2026, 1, 16, 8, 30, tzinfo=sources.SEOUL)
    monkeypatch.setenv("AX_TREND_SCHEDULE", "1")
    monkeypatch.setattr(sources, "now_seoul", lambda: now)
    monkeypatch.setattr(sources, "collect", lambda at: (_channels(at, "모과"), {}))
    publish = publishing.publish
    finished = Event()

    def watched_publish(at):
        result = publish(at)
        finished.set()
        return result

    monkeypatch.setattr(publishing, "publish", watched_publish)
    app = FastAPI()
    app.include_router(trend_route.router)
    with TestClient(app):
        assert finished.wait(2)
        assert publishing.tracking(now)["edition"]["issue"]["topic"] == "모과"


def test_official_list_reads_three_latest_articles_and_keeps_only_source_media(monkeypatch):
    now = datetime(2026, 1, 16, 14, tzinfo=sources.SEOUL)
    links = [
        ("/bgflive/view/?id=1", "26.01.10"),
        ("/bgflive/view/?id=2", "26.01.11"),
        ("/bgflive/view/?id=3", "26.01.12"),
        ("/bgflive/view/?id=4", "26.01.13"),
        ("https://origin.bgf.co.kr.evil.example/bgflive/view/?id=5", "26.01.14"),
        ("/assets/coffee-story.jpg", "26.01.15"),
    ]
    listing = '<ul>' + ''.join(
        f'<li class="pr"><a href="{url}"><div class="txt"><h3><span>{day}</span></h3>'
        '<p>유자 음료 출시</p></div></a></li>'
        for url, day in links
    ) + '</ul>'
    detail = """
    <div class="contents_detail"><div class="title"><h1>유자 음료 출시</h1></div></div>
    <div class="detail_inner">
      <p>‘유자 음료 출시’</p>
      <p>신제품은 이달 둘째 주부터 편의점 냉장 매대에서 250mL 규격으로 판매한다.</p>
      <p>추가 제품 정보.</p>
      <img src="https://outside.example/photo.jpg">
      <img src="/assets/upload/image/editor/logo.png">
      <img src="/assets/upload/image/editor/quince.webp" alt="유자 음료 보도사진">
    </div>
    """
    calls = []

    def fetch(url, headers=None, *, official_site=None):
        if url == sites.BGF_NEWSROOM:
            return listing.encode()
        assert official_site == "bgf"
        calls.append(url)
        return detail.encode()

    monkeypatch.setattr(sources, "fetch", fetch)
    result = sources.bgf_news(now)
    assert len(calls) == len(result) == newsroom.STORIES_PER_NEWSROOM
    assert [r["url"].split("=")[-1] for r in result] == ["4", "3", "2"]
    assert set(calls) == {r["url"] for r in result}
    for row in result:
        assert row["summary"] == "신제품은 이달 둘째 주부터 편의점 냉장 매대에서 250mL 규격으로 판매한다."
        assert row["image"] == "https://origin.bgf.co.kr/assets/upload/image/editor/quince.webp"
        assert row["alt"] == "유자 음료 보도사진"
        assert row["photoCredit"] == "BGF리테일"
        assert row["sources"][0]["text"] == row["summary"]


def test_official_rss_provides_article_fields_without_fetching_detail(monkeypatch):
    now = datetime(2026, 1, 16, 14, tzinfo=sources.SEOUL)
    rss = """
    <rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>
      <title>편의점, 새로운 모과차 음료 출시</title>
      <link>https://www.shinsegaegroupnewsroom.com/new-quince-drink/</link>
      <pubDate>Fri, 16 Jan 2026 00:00:00 GMT</pubDate>
      <description><![CDATA[<p>편의점, 새로운 모과차 음료 출시</p>]]></description>
      <content:encoded><![CDATA[
         <p>모과차는 한 잔 분량의 온장 상품으로 일부 점포에서 먼저 판매한다.</p>
         <img src="https://images.shinsegaegroupnewsroom.com/wp-content/uploads/2026/quince.png">
      ]]></content:encoded>
    </item></channel></rss>
    """

    def fetch(url, headers=None, *, official_site=None):
        if url.startswith(sites.SHINSEGAE_POSTS + "?"):
            raise OSError("최신 목록을 읽을 수 없음")
        assert url == sites.SHINSEGAE_RSS and official_site is None
        return rss.encode()

    monkeypatch.setattr(sources, "fetch", fetch)
    row, = sources.shinsegae_news(now)
    assert row["summary"] == "모과차는 한 잔 분량의 온장 상품으로 일부 점포에서 먼저 판매한다."
    assert row["image"] == "https://images.shinsegaegroupnewsroom.com/wp-content/uploads/2026/quince.png"
    assert row["alt"] is None
    assert row["photoCredit"] == "신세계그룹 뉴스룸"


def test_description_and_photo_stay_empty_without_valid_article_content():
    url = "https://company.lottechilsung.co.kr/kor/company/news/view.do?detailsKey=5"
    row = sources.article("모과 음료 출시 소식", url, date(2026, 1, 15))
    body = """
      <div class="conTxt">
        <p>모과 음료 출시 소식.</p>
        <img src="https://company.lottechilsung.co.kr.evil.example/image/news.png">
        <img src="https://company.lottechilsung.co.kr@outside.example/image/news.png">
        <img src="https://company.lottechilsung.co.kr:444/image/news.png">
        <img src="/image/%2e%2e/common/logo.jpg">
      </div>
    """
    assert sites.article_site(url) == "lotte"
    assert sites.article_site(url.replace("view.do?", "script.js?")) is None
    assert sites.press_photo(url, "http://company.lottechilsung.co.kr/image/2026/quince.jpg") == (
        "https://company.lottechilsung.co.kr/image/2026/quince.jpg"
    )
    result = newsroom.from_article(row, body.encode(), "lotte")
    assert all(result[key] is None for key in ("summary", "image", "alt", "photoCredit"))


def test_old_collection_is_refreshed_without_reissuing_the_daily_edition(monkeypatch, isolated_store):
    now = datetime(2026, 1, 16, 9, tzinfo=sources.SEOUL)
    url = "https://www.shinsegaegroupnewsroom.com/quince-tea-launch/"
    live = sources.article("모과차, 일부 점포에서 출시", url, now.date())
    live.update(summary="편의점은 한 잔을 바로 마실 수 있는 모과차를 냉장 매대에 배치했어요.",
                image="https://images.shinsegaegroupnewsroom.com/wp-content/uploads/2026/tea.jpg")
    calls = []

    def collector(at):
        calls.append(at)
        return _channels(at, "모과"), {"shinsegae": {"ok": True, "rows": [] if at == now else [live]}}

    monkeypatch.setattr(sources, "collect", collector)
    assert publishing.publish(now)
    issue = publishing.tracking(now)["edition"]["issue"]
    with publishing._connect() as db:
        db.execute("UPDATE collection SET data = json_remove(data, '$.version')")
    web.save("모과", [{"claim": "같은 주소에 저장된 요약 없는 제목", "url": url, "date": "2026-01-16", "source": "기존 검색"}])
    restart = now + timedelta(seconds=1)
    assert not publishing.publish(restart)
    assert publishing.tracking(restart)["edition"]["issue"] == issue
    packet = publishing.refresh(restart)
    assert calls == [now, restart]
    item, = [item for item in packet["items"] if item["url"] == url]
    assert item["summary"] == live["summary"] and item["image"] == live["image"]


def test_newsletter_keeps_the_source_when_simplifying_press_copy():
    excerpt = "일부 점포에서 두 가지 음료를 시범 판매한다."
    row = {"id": "news-sample", "title": "“새로운 맛의 만남” 견본식품, 새 음료 2종 출시!", "summary": excerpt,
           "sources": [{"text": excerpt}]}
    item = newsroom.newsletter_copy(row)
    assert item["title"] == "견본식품, 새 음료 2종 출시"
    assert item["summary"] == "일부 점포에서 두 가지 음료를 시범 판매해요."
    assert item["sources"][0]["text"] == row["summary"] == excerpt


def test_current_newsroom_includes_food_outside_beverage_search_and_keeps_source_date(monkeypatch):
    now = datetime(2026, 11, 24, 8, 30, tzinfo=sources.SEOUL)
    base = "https://www.shinsegaegroupnewsroom.com/"
    def post(title, slug, utc):
        return {"title": {"rendered": title}, "link": base + slug + "/", "date_gmt": utc}

    posts = [post("모과 간편식 출시", "quince-meal-2", "2026-11-23T23:05:00"),
             post("모과 간편식 출시", "quince-meal", "2026-11-23T23:00:00"),
             post("늦은 커피 발표", "future-coffee", "2026-11-24T00:00:00"),
             post("겨울 의류 출시", "winter-apparel", "2026-11-23T23:10:00")]
    def fetch(url, headers=None, *, official_site=None):
        if url.startswith(sites.SHINSEGAE_POSTS + "?"):
            return json.dumps(posts).encode()
        if url == sites.SHINSEGAE_RSS:
            raise OSError("음료 RSS 사용 불가")
        assert official_site == "shinsegae" and url == base + "quince-meal/"
        return b"<html></html>"

    monkeypatch.setattr(sources, "fetch", fetch)
    item, = sources.shinsegae_news(now)
    assert (item["date"], item["title"], item["url"]) == ("2026-11-24", "모과 간편식 출시", base + "quince-meal/")


def test_live_edition_has_priority_over_archived_example(monkeypatch, isolated_store):
    now = datetime(2026, 11, 24, 14, tzinfo=sources.SEOUL)
    monkeypatch.setattr(sources, "collect", lambda at: (_channels(at, "유자"), {}))
    assert publishing.publish(now)
    packet = publishing.tracking(now)
    assert packet["edition"]["issue"]["topic"] == "유자"
    assert packet["nextAt"] == "2026-11-25T08:30:00+09:00"
