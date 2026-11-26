"""보고서의 "실제 자료와 대조" 구역(agent/proposal_compare.py). 표와 테스트 기록은 지어낸 것이다. 모델을 부르지 않는다."""

import sys
import types

import pytest

from agent import proposal, proposal_compare as PC
from agent.note import Note
from shelftest import method
from test_calibrate_sales import MONTHS, concept, data, key, pos_rows, run, sale, write  # noqa: F401 — data는 준비물

RUN = "run-0000000000aa"


@pytest.fixture
def note(data):  # noqa: F811
    old = [sale("T-9", "견본소다 딸기 300ml 캔", "탄산", True, 400, 1000, m, brand="견본T-1") for m in MONTHS[5:8]]
    write(data, "pos_clean", pos_rows() + old + [{**old[1], "channel": "대형마트"}])
    write(data, "past_tests", [
        {"product": "견본소다 딸기", "year": 2021, "category": "탄산", "intent_top2": 0.5, "trial_12m": 0.1, "ratio": 0.2},
        {"product": "견본커피 신제품", "year": 2022, "category": "캔커피", "intent_top2": 0.4, "trial_12m": 0.02, "ratio": 0.05},
    ])
    write(data, "assets", [
        {"asset_id": "Z-1", "sku": "Z", "name": "견본소다 수박", "brand": "견본T-1", "category": "탄산", "status": "단종",
         "launched": "2019-05-01", "ended": "2019-09-30", "peak_sales_100m": 12, "reason": "견본 사유"},
        {"asset_id": "Z-2", "sku": "Y", "name": "견본커피 옛것", "brand": "다른", "category": "캔커피", "status": "단종"},
    ])
    run(RUN, 10, [key("T-1")] * 2 + [key("T-2")] * 6 + [method.NO_PURCHASE] * 92)
    n = Note(shelf_kind="탄산", concepts=[{"id": "c1", "name": "견본 신제품 소다", "brand": "견본T-1"}], runs={"c1": RUN})
    return n


def paper():
    return {"chat_id": "chat", "evidence": {"compare": []}}


def parts(test):
    return {c["title"]: c["lines"] for c in test["evidence"]["compare"]}


def test_three_parts_in_report_style(note):
    test = paper()
    PC.add(note, note.concepts[0], test)
    got = parts(test)
    assert list(got) == [PC.SALES, PC.GAP, PC.SIMILAR]
    money = got[PC.SALES]
    assert money[0] == "기간 2027-06~2027-08, 편의점 기준"
    assert money[1].startswith("가상 매출 ") and "중앙" in money[1] and money[2].startswith("가상 판매수량 ")
    assert money[3].startswith("순증 가상 매출 ") and money[4].startswith("옮겨 온 자사 제품의 가상 매출 감소: ")
    assert any(line.startswith("가정 · ") for line in money)
    text = "\n".join(line for lines in got.values() for line in lines)
    assert "시장점유율" not in text
    assert not any(line.rstrip(".").endswith(("요", "습니다")) for line in text.splitlines())


def test_gap_and_similar_come_from_the_tables(note):
    test = paper()
    PC.add(note, note.concepts[0], test)
    got = parts(test)
    assert got[PC.GAP][0] == "견본소다 딸기(2021): 구매 의향 TOP2 50% → 출시 12개월 실제 구매경험률 10.0%, 의향 대비 실제 0.20"
    assert "과거 컨셉테스트 전체 2건의 의향 대비 실제 구매 비율 0.05~0.20" in got[PC.GAP]
    similar = got[PC.SIMILAR]
    assert similar[0] == "견본소다 딸기 300ml 캔: 판매 2025-06~2025-08(3개월), 편의점 비중 75%, 정점 2025-07(월 800개)"
    assert any(line.startswith("판매 자료에 없는 과거 제품 · 견본소다 수박") and "견본 사유" in line for line in similar)
    assert not any("견본콜라" in line or "견본커피" in line for line in similar)  # 경쟁사와 다른 종류는 뺀다


def test_adds_once_and_keeps_others(note):
    test = paper()
    test["evidence"]["compare"].append({"title": "기존 대조", "lines": ["그대로"]})
    PC.add(note, note.concepts[0], test)
    PC.add(note, note.concepts[0], test)
    assert [c["title"] for c in test["evidence"]["compare"]] == ["기존 대조", PC.SALES, PC.GAP, PC.SIMILAR]


def test_nothing_without_data_or_for_another_chat(note, monkeypatch, tmp_path):
    other = {"chat_id": "다른 대화", "evidence": {"compare": []}}
    PC.add(note, note.concepts[0], other)
    assert other["evidence"]["compare"] == []
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path / "없음"))
    monkeypatch.setitem(sys.modules, "calibrate.followup", None)
    test = paper()
    PC.add(note, note.concepts[0], test)
    assert test["evidence"]["compare"] == []


def test_one_broken_part_does_not_stop_the_rest(note, monkeypatch):
    monkeypatch.setattr(PC, "gap_lines", lambda kind: 1 / 0)
    test = paper()
    PC.add(note, note.concepts[0], test)
    assert PC.GAP not in parts(test) and PC.SALES in parts(test)


def test_followup_lines_when_there(note, monkeypatch):
    fake = types.ModuleType("calibrate.followup")
    fake.report_lines = lambda n, c: ["조사 응답 30명 반영"]
    import calibrate

    monkeypatch.setitem(sys.modules, "calibrate.followup", fake)
    monkeypatch.setattr(calibrate, "followup", fake, raising=False)
    test = paper()
    PC.add(note, note.concepts[0], test)
    assert parts(test)[PC.FOLLOWUP] == ["조사 응답 30명 반영"]


def test_registered():
    assert PC.add in proposal.REPORT_EXTRAS
