"""합성 사례로 과거 기획 검색과 대화의 근거 연결을 확인한다."""

import asyncio

import pytest

from agent import machine, research
from events import event_adapter
from export_aisdk import data_part, ui_parts
from ideas import similarity, store
from ideas.board import Entry
from ideas.history import lookup
from ideas.models import IdeaRow
from llm.base import set_llm
from llm.fake import FakeLLM


@pytest.fixture
def cases(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path / "ideas")
    entries = [
        Entry(IdeaRow(
            id="견본/중단 #1", name="견본 블렌드 A", status="폐기", owner="가상담당자",
            concept="첫 배합에는 오렌지 농축액을 사용했다. 확인용 비공개 원문.",
            reason="원가 상승으로 목표 단가를 맞추지 못했다.",
            last_work="소량 시생산을 마쳤다.", verdict="추가 양산 보류",
        )),
        Entry(IdeaRow(id="single-word", name="오렌지 민트 워터", status="출시")),
        Entry(IdeaRow(id="active", name="견본 블렌드 B", status="기획 중", concept="오렌지 농축액 원가")),
        Entry(IdeaRow(id="released", name="견본 보리차", brand="새벽샘", category="곡물차", pack="유리병", status="출시")),
        Entry(IdeaRow(id="discontinued", name="견본 허브차", status="단종")),
    ]
    monkeypatch.setattr(similarity, "entries", lambda: entries)
    return entries


def test_multi_term_query_matches_original_and_reason_over_one_word_product(cases):
    query = "오렌지 농축액 원가가 걸렸던 과거 사례를 찾아줘"
    assert [row.id for row in similarity.search_cases(query)] == [cases[0].row.id]
    assert [row.id for row in similarity.search_cases("오렌지농축액")] == [cases[0].row.id]


def test_search_reads_attributes_decision_earlier_work_and_attachment_name(cases):
    row_id = cases[0].row.id
    store.write_log(row_id, "older", "공급사 현장 방문", "배합_관능패널.xlsx", b"sample")
    store.write_log(row_id, "newer", "최종 후속 회의", None, None)
    assert [row.id for row in similarity.search_cases("공급사 현장")] == [row_id]
    assert [row.id for row in similarity.search_cases("배합_관능패널.xlsx")] == [row_id]
    assert [row.id for row in similarity.search_cases("소량 시생산")] == [row_id]
    assert [row.id for row in similarity.search_cases("양산 보류")] == [row_id]
    assert [row.id for row in similarity.search_cases("새벽샘 곡물차 유리병")] == ["released"]
    assert [row.id for row in similarity.search_cases("견본 허브차")] == ["discontinued"]
    assert similarity.search_cases("근거 없는 자작나무 향") == []


def test_blank_search_lists_past_cases_and_keeps_recorded_launches(cases):
    cases.append(Entry(IdeaRow(id="formerly-launched", name="견본 산딸기차", status="보류",
                               launched_on="2024-09-17")))
    assert [row.id for row in similarity.search_cases("")] == [
        cases[0].row.id, "single-word", "released", "discontinued", "formerly-launched",
    ]
    items, found = lookup("산딸기차", "산딸기차")
    assert items[0]["status"] == "출시"
    assert "출시 이력" in found[0].text


def test_card_marks_missing_record_and_omits_full_history(cases):
    row = cases[0].row
    row.reason = "원가 상승 " + "가" * 240 + " 가상담당자 test@example.org /Users/sample/test.txt"
    items, found = lookup("오렌지 농축액 원가", "오렌지 농축액 원가")
    assert items[0]["concept_excerpt"].startswith("첫 배합에는 오렌지 농축액")
    assert set(items[0]["conditions"]) == {"농축액", "오렌지", "원가"}
    assert len(items[0]["reason"]) <= 180
    assert found[0].url == "/ideas?idea=%EA%B2%AC%EB%B3%B8%2F%EC%A4%91%EB%8B%A8%20%231"
    assert "확인용 비공개 원문" not in found[0].text
    row.reason = "원가 상승 가상담당자 test@example.org /Users/sample/test.txt"
    items, found = lookup("오렌지 농축액 원가", "오렌지 농축액 원가")
    assert all(value not in items[0]["reason"] for value in ("가상담당자", "test@example.org", "/Users/"))
    items, found = lookup("견본 허브차", "견본 허브차")
    assert items[0]["has_original"] is False
    assert items[0]["reason"] is None
    assert "사유 기록은 없어요" in found[0].text


def test_investigation_preserves_trend_and_brings_case_into_real_planning_path(cases, monkeypatch):
    monkeypatch.setattr(research, "verdicts", lambda: [])
    monkeypatch.setattr(research, "_published_news", lambda query, today: [])
    fake = FakeLLM()
    set_llm(fake)

    async def collect():
        return [event async for event in machine.turn(
            "history-test", "오렌지 농축액 원가 트렌드를 확인하고 아이디어도 내 주세요.", [], 1,
        )]

    events = asyncio.run(collect())
    trend = next(event for event in events if event.t == "card" and event.kind == "trend")
    history = next(event for event in events if event.t == "card" and event.kind == "history")
    assert events.index(trend) < events.index(history)
    assert [item["id"] for item in history.payload["items"]] == [cases[0].row.id]
    assert event_adapter.validate_python(history.model_dump()) == history
    parts = ui_parts([history.model_dump(exclude_none=True)], None)
    assert parts[-1] == data_part(history)

    notes = machine.CONVS["history-test"].evidence
    case = next(item for item in notes if item["source"] == "아이디어 보드")
    assert case["url"].startswith("/ideas?idea=")
    prompt = next(call["user"] for call in fake.calls if call["task"] == "ideas")
    assert cases[0].row.reason in prompt and "아이디어 보드" in prompt
    assert "첫 배합에는 오렌지 농축액을 사용했다." in prompt
    assert "오렌지 민트 워터" not in prompt
    assert "확인용 비공개 원문" not in prompt
