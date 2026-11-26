"""기획에 쓰는 내부 추이와 외부 소식을 각각 확인해 작업대에 남긴다."""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
from datetime import date
from urllib.parse import urlsplit

from agent import find, steps
from agent.find import Found
from events import Activity, Card
from onsite.concepts import CONCEPTS
from tools import web
from trend.verdicts import verdicts


def compact(text: str) -> str:
    return "".join(text.casefold().split())


def selected_topic(text: str) -> str:
    topic = re.search(r"^기획에 앞서 (.{1,100}?) 관련 내부 자료", text, re.MULTILINE)
    if topic:
        return topic.group(1).strip()
    value = compact(text)
    for concept in CONCEPTS:
        for term in [concept["name"], *concept["keywords"]]:
            if compact(term) in value:
                return term
    # 대화에 지정한 검색어를 받는다. 열려 있는 피드의 인기 검색어 목록과는 독립적이다.
    explicit = re.match(r"^(?:요즘\s+)?([^\n?!.]{1,50}?)\s+(?:트렌드|검색\s*추이|관련\s*소식|관련\s*뉴스)", text.strip())
    return explicit.group(1).strip() if explicit else ""


def feed_context(text: str) -> list[Found]:
    lines = text.splitlines()
    title = next((line.removeprefix("읽은 소식: ").strip() for line in lines if line.startswith("읽은 소식: ")), "")
    if not title:
        return []
    found = {}
    for line in lines:
        if not line.startswith("출처: "):
            continue
        for entry in line.removeprefix("출처: ").split("; "):
            for url in re.findall(r"https?://[^\s,;<>]+", entry):
                publisher = entry.partition(url)[0].strip() or "기획자가 고른 소식"
                found[url] = Found(key=f"selected:{url}", tool="selected", origin="web", text=title,
                                   source=publisher, said_source=publisher, fact=title, sentence=title, url=url)
    return list(found.values())


def _internal_item(verdict, title):
    return {"keyword": verdict["keyword"], "source": "internal", "title": title, "publisher": "내부 자료",
            "date": verdict["series"][-1]["month"], "url": None, "verdict": verdict}


def internal_results(query: str):
    terms = [query]
    for concept in CONCEPTS:
        if compact(concept["name"]) in compact(query):
            terms.extend(concept.get("keywords", []))
    normalized = compact(" ".join(terms))
    all_verdicts = verdicts()
    matching = [v for v in all_verdicts if v["series"] and compact(v["keyword"]) in normalized]
    items = [_internal_item(v, f"{v['keyword']} 검색 흐름") for v in matching]
    risk = next((v for v in matching if set(v["stage"]) & {"피크아웃", "광고성 바이럴"}), None)
    if not risk:
        return items, None
    sentence, required = plain_risk(risk)
    alternative = next((v for v in all_verdicts if v["series"] and v not in matching
                        and "상승기" in v["stage"] and not set(v["stage"]) & {"광고성 바이럴", "피크아웃"}), None)
    if alternative:
        keyword = alternative["keyword"]
        items.append(_internal_item(alternative, f"함께 비교할 {keyword}"))
    # 판정 이름("피크아웃", "계절성 수요")은 말에 내지 않는다. 뜻을 숫자 하나와 함께 쉬운 말로 넘긴다
    alert = Found(key=f"research:{risk['keyword']}", tool="research", origin="internal", text=sentence,
                  source="내부 자료", said_source="", fact=sentence, sentence=sentence,
                  extra={"required": required})
    return items, alert


_PEAK_PCT = re.compile(r"의 (\d+%)예요")
_SEASON_MONTH = re.compile(r"두 해 모두 (\d+)월에")
_AD_PCT = re.compile(r"광고·협찬은 (\d+%)")


def plain_risk(verdict: dict) -> tuple[str, list[str]]:
    """판정을 쉬운 말로: "수박화채는 해마다 7월에만 많이 찾아요. 올해 검색은 작년 7월의 39% 수준이에요."
    돌려주는 required는 말에 꼭 들어가야 하는 숫자(없으면 빈 목록)."""
    from tools.consumer import josa

    kw = verdict["keyword"]
    text = " ".join(verdict.get("reasons") or [])
    peak = _PEAK_PCT.search(text) if "피크아웃" in verdict["stage"] else None
    month = _SEASON_MONTH.search(text) if "계절성 수요" in verdict["stage"] else None
    ad = _AD_PCT.search(text) if "광고성 바이럴" in verdict["stage"] else None
    out, required = [], []
    if month:
        out.append(f"{kw}{josa(kw, '은/는')} 해마다 {month.group(1)}월에 가장 많이 찾아요.")
    if peak:
        when = f"작년 {month.group(1)}월" if month else "작년 가장 많이 찾던 때"
        out.append(f"올해 검색은 {when}의 {peak.group(1)} 수준이에요.")
        required.append(peak.group(1))
    if ad:
        out.append(f"SNS에서 갑자기 많이 언급된 달은 광고·협찬 글이 {ad.group(1)}였어요.")
        required.append(ad.group(1))
    if not out:
        out.append(f"{kw} 검색 흐름은 조심해서 봐야 해요.")
    if not month and peak and not ad:
        out[0] = f"{kw} " + out[0]
    return " ".join(out), required or [kw]


def _published_news(query: str, today: date | None) -> list[Found]:
    from trend import feed

    key = compact(query)
    articles = [{"claim": row["title"], "source": row["publisher"], "url": row["url"], "date": row["date"]}
                for row in feed() if row["source"] == "web" and key in compact(row["title"] + row["keyword"])]
    return find.news(web.filter_claims(articles, today=today))


async def _news(query: str, today: date | None, *, search: bool) -> list[Found]:
    fake = os.getenv("AX_LLM") == "fake"
    cache_key = f"fake:{query}" if fake else query
    raw = web.load(cache_key)
    if raw is None and not search:
        # 아직 종류가 모호한 첫 질문은 이 단어로 실제 수집한 글에서만 찾는다.
        return await asyncio.to_thread(_published_news, query, today)
    if raw is None:
        try:
            raw = await steps.trend(query, today=today)
        except steps.StepFailed:
            raw = []
        if raw:
            web.save(cache_key, raw)
    claims = web.filter_claims(raw, today=today)
    # 가짜 응답기의 기본 답은 제로 탄산 견본이다. 다른 기획이나 실제 검색에 재사용하지 않는다.
    usable = []
    for claim in claims:
        try:
            address = urlsplit(claim.url)
            if address.scheme not in ("http", "https") or not address.hostname:
                continue
        except ValueError:
            continue
        if address.hostname != "example.com" or (fake and query == "제로 탄산"):
            usable.append(claim)
    return find.news(usable) if usable else await asyncio.to_thread(_published_news, query, today)


async def investigate(note, log, query: str, today: date | None, *, explicit: bool):
    internal = note.next_id("research")
    yield Activity(id=internal, label="내부 트렌드 자료를 확인하고 있어요", status="running")
    items, alert = await asyncio.to_thread(internal_results, query)
    yield Activity(id=internal, label="내부 트렌드 자료를 확인했어요", status="done")
    external = note.next_id("research-web")
    yield Activity(id=external, label="최근 소식을 찾아보고 있어요", status="running")
    search = bool(note.kind or explicit or note.thoughts)
    news = feed_context(log.text) + await _news(query, today, search=search)
    note.web_done.add(query)
    unique = {}
    for item in news:
        unique.setdefault(item.url, item)
    log.founds.extend(unique.values())
    if alert:
        log.founds.insert(0, alert)
    items.extend({"keyword": query, "title": item.text, "source": "web", "publisher": item.source,
                  "url": item.url, "date": item.date, "verdict": None} for item in unique.values())
    yield Activity(id=external, label="최근 소식 확인을 마쳤어요", status="done")
    yield Card(id="trend", stage="idea", kind="trend", title="트렌드 조사", status="ready", payload={"items": items})
    yield Activity(id=note.next_id("research-summary"), label="기획에 참고할 흐름을 정리했어요", status="done")
    from ideas import history

    text = compact(query + " " + log.text.split("\n읽은 소식:", 1)[0])
    concept = next((c for c in CONCEPTS if compact(c["name"]) in text), None)
    try:
        cases, found = await asyncio.to_thread(history.lookup, query, log.text, concept=concept)
    except (OSError, sqlite3.Error, ValueError):
        yield Card(id="history", stage="idea", kind="history", title=history.TITLE, status="error", payload=None)
        return
    log.founds.extend(found)
    yield Card(id="history", stage="idea", kind="history", title=history.TITLE, status="ready", payload={"items": cases})
