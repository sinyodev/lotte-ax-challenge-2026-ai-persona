"""하루 한 번 수집·발행하고 마지막으로 발행한 호를 읽는다."""

from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3

from . import editorial, newsroom, sources
from .stories import stories
from .verdicts import verdicts

STORE = Path(__file__).resolve().parents[1] / "store" / "trend"
REFRESH_INTERVAL = timedelta(minutes=5)
CHANNEL_NAMES = ("google", "naver")
COLLECTION_VERSION = 3


def publication_slot(now: datetime) -> datetime:
    local = now.astimezone(sources.SEOUL)
    morning = local.replace(hour=8, minute=30, second=0, microsecond=0)
    return morning if local >= morning else morning - timedelta(days=1)


@contextmanager
def _connect():
    directory = Path(os.environ.get("AX_TREND_DIR", STORE))
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / "tracking.sqlite", timeout=20)
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS collection (name TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS edition (day TEXT PRIMARY KEY, topic TEXT UNIQUE, data TEXT NOT NULL);
        """)
        with db:
            yield db
    finally:
        db.close()


def _snapshot(db) -> dict:
    row = db.execute("SELECT data FROM collection WHERE name = 'latest'").fetchone()
    return json.loads(row[0]) if row else {}


def _collect(db, now: datetime, previous: dict) -> tuple[dict, dict]:
    channels, newsletters = sources.collect(now)
    prior_news = previous.get("news", {})
    news = {
        name: result if result["ok"] else prior_news.get(name, result)
        for name, result in newsletters.items()
    }
    if not any(channel["ok"] for channel in [*channels.values(), *newsletters.values()]):
        # 실패를 다음 새로 고침과 발행에 넘기지 않고 마지막 성공 수집 시각을 둔다.
        return previous, channels
    snapshot = {"version": COLLECTION_VERSION, "collectedAt": now.isoformat(), "channels": channels, "news": news}
    db.execute(
        "INSERT OR REPLACE INTO collection (name, data) VALUES ('latest', ?)",
        (json.dumps(snapshot, ensure_ascii=False),),
    )
    return snapshot, channels


def _internal_items() -> list[dict]:
    return [{
        "keyword": item["keyword"], "title": f"{item['keyword']} 검색 흐름",
        "source": "internal", "publisher": "내부 자료", "url": None,
        "date": item["series"][-1]["month"] + "-01", "verdict": item,
    } for item in verdicts() if item["series"]]


def _news(snapshot: dict, now: datetime, keywords: list[str]) -> list[dict]:
    live = [story for publisher in snapshot.get("news", {}).values() for story in publisher["rows"]]
    terms = [row["topic"] for channel in snapshot.get("channels", {}).values() for row in channel["rows"]]
    cached = sources.cached_news([*keywords, *terms, "음료", "편의점"], now.date())
    approved = [story for story in stories() if story["date"] <= now.date().isoformat()]
    cutoff = (now.date() - sources.MAX_AGE).isoformat()
    recent = [row for row in [*live, *cached] if cutoff <= row["date"] <= now.date().isoformat()]
    combined = {}
    for story in [*approved, *recent]:
        combined.setdefault(sources.article_key(story["url"]), story)
    return sorted(combined.values(), key=lambda story: story["date"], reverse=True)


def feed_packet(now: datetime | None = None) -> dict:
    now = now or sources.now_seoul()
    with _connect() as db:
        snapshot = _snapshot(db)
    internal = _internal_items()
    news = _news(snapshot, now, [row["keyword"] for row in internal])
    return {"items": [*(newsroom.newsletter_copy(row) for row in news), *internal],
            "collected_at": snapshot.get("collectedAt")}


def feed() -> list[dict]:
    return feed_packet()["items"]


def refresh(now: datetime | None = None) -> dict:
    now = now or sources.now_seoul()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = _snapshot(db)
        last = previous.get("collectedAt")
        if (previous.get("version") != COLLECTION_VERSION or not last
                or now - datetime.fromisoformat(last) >= REFRESH_INTERVAL):
            _collect(db, now, previous)
    return feed_packet(now)


def publish(now: datetime | None = None) -> bool:
    now = (now or sources.now_seoul()).astimezone(sources.SEOUL)
    slot = publication_slot(now)
    day = slot.date()
    day_key = day.isoformat()
    with _connect() as db:
        # 여러 서버 작업자와 새로 고침이 겹쳐도 슬롯마다 한 차례만 발행한다.
        db.execute("BEGIN IMMEDIATE")
        previous = _snapshot(db)
        if db.execute("SELECT 1 FROM edition WHERE day = ?", (day_key,)).fetchone():
            # 제목만 있던 캐시는 보강하고 이미 발행한 호는 그대로 둔다.
            if previous and previous.get("version") != COLLECTION_VERSION:
                _collect(db, now, previous)
            return False
        last = previous.get("collectedAt")
        if previous.get("version") == COLLECTION_VERSION and last and slot <= datetime.fromisoformat(last) <= now:
            snapshot, channels = previous, previous["channels"]
        else:
            snapshot, channels = _collect(db, now, previous)
        published = {row[0] for row in db.execute("SELECT topic FROM edition WHERE topic IS NOT NULL")}
        if day > editorial.APPLE_EDITION:
            published.add("사과")
        issue = editorial.choose_issue(day, channels, _news(snapshot, now, []), published)
        if issue is None and day == editorial.APPLE_EDITION and "사과" not in published:
            issue = editorial.approved_edition(day)
        payload = {"day": day_key, "collectedAt": now.isoformat(), "channels": channels, "issue": issue}
        topic = editorial.topic_key(issue["topic"]) if issue else None
        db.execute("INSERT INTO edition (day, topic, data) VALUES (?, ?, ?)",
                   (day_key, topic, json.dumps(payload, ensure_ascii=False)))
    return True


def tracking(now: datetime | None = None) -> dict:
    slot = publication_slot(now or sources.now_seoul())
    day_key = slot.date().isoformat()
    with _connect() as db:
        db.execute("BEGIN")
        latest = db.execute("SELECT data FROM edition WHERE day = ?", (day_key,)).fetchone()
        previous = db.execute(
            "SELECT data FROM edition WHERE day <= ? AND topic IS NOT NULL ORDER BY day DESC LIMIT 1",
            (day_key,),
        ).fetchone()
    edition = json.loads(latest[0]) if latest else {
        "day": day_key,
        "collectedAt": None,
        "channels": {name: {"ok": False, "rows": []} for name in CHANNEL_NAMES},
        "issue": None,
    }
    if edition["issue"] is None:
        saved = json.loads(previous[0])["issue"] if previous else None
        approved = editorial.approved_edition(slot.date())
        editions = [issue for issue in (saved, approved) if issue]
        edition["issue"] = max(editions, key=lambda issue: issue["date"], default=None)
    return {"edition": edition, "nextAt": (slot + timedelta(days=1)).isoformat()}
