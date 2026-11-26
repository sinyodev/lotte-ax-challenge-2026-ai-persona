"""음용 상황의 화면 이름(참가자 검수 11-25): 화면·말·보고서만 바뀌고 가상 소비자에게 가는 글과 답의 열쇠는 그대로."""

from __future__ import annotations

import hashlib

import pytest

from agent import phrases as P
from agent import result_brief
from shelftest import explore, method, result, waiting
from tools import consumer
from tools.occasion_display import data_name, same, show

OLD_OUT, NEW_OUT = "밖에서 식사와 함께", "밖에서 식사할 때 입가심"
OLD_HOME, NEW_HOME = "집에서 식사와 함께", "집에서 식사할 때 입가심"

# 이름을 바꾸기 전의 코드로 잰 값(제공 자료가 없는 매대, 같은 손님·같은 방문). 바뀌면 저장된 답을 다시 쓸 수 없다.
PROMPT_DIGEST = {4: "96ae9c8dcd6bcc02bb2c9270c8bee4fb4e526be9f26dc7f843fc7c317c051a67",
                 11: "c3a49c6e3eabf0aaf73a623cd9b9027285c2cdf48ef2f0c9f803246cff36f3cf"}
SHELF_V = {4: "0be4576bce", 11: "080475396b"}


@pytest.fixture(autouse=True)
def no_onsite_tables(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path / "missing"))


def _plans(rnd: int):
    return [method.plan(band, sex, occ, 6, "밀키스 화채 견본 500ml", 1800, None, round_number=rnd)
            for band, sex, occ in (("19-29", None, "D7"), ("30-39", "여자", "D8"))]


@pytest.mark.parametrize("rnd", [4, 11])
def test_shopper_prompts_and_shelf_v_unchanged(rnd):
    out, texts = [], []
    for p in _plans(rnd):
        for v in p.visits:
            for cond in (method.BASELINE, method.CONCEPT):
                s, u, _ = method.prompts(p, v, cond)
                out.append(hashlib.sha256((s + "\0" + u).encode()).hexdigest())
                texts.append(s + u)
    assert hashlib.sha256("|".join(out).encode()).hexdigest() == PROMPT_DIGEST[rnd]
    assert method.shelf_v(rnd) == SHELF_V[rnd]
    joined = "\n".join(texts)
    assert NEW_OUT not in joined and NEW_HOME not in joined


def test_data_names_stay_for_the_shopper():
    occ = method.occasions()
    assert occ["D7"]["상황"] == OLD_OUT and occ["D8"]["상황"] == OLD_HOME
    p = method.plan("19-29", None, "D7", 4, "견본 500ml", 1800, None)
    assert {v["상황"] for v in p.visits if v["상황 번호"] == "D7"} == {OLD_OUT}


def test_show_mapping():
    assert show(OLD_OUT) == NEW_OUT and show(OLD_HOME) == NEW_HOME
    assert show(NEW_OUT) == NEW_OUT and show("혼자 마실 때") == "혼자 마실 때"
    assert data_name(NEW_HOME) == OLD_HOME and same(OLD_OUT, NEW_OUT) and not same(OLD_OUT, NEW_HOME)


def test_part1_uses_display_names_and_reads_both():
    occ = consumer.all_occasions()
    assert occ["D7"].name == NEW_OUT and occ["D8"].name == NEW_HOME
    assert consumer.occasion_code_of(OLD_OUT) == "D7" == consumer.occasion_code_of(NEW_OUT)
    assert consumer.occasion_code_of(OLD_HOME) == "D8" == consumer.occasion_code_of(NEW_HOME)
    assert P.when_phrase("20대", NEW_OUT) == "20대가 밖에서 식사할 때 입가심으로 마실 때"


def test_persist_upgrades_old_note():
    from agent import persist
    from agent.note import Note, Slot

    n = Note(occasion=Slot(OLD_OUT, "chilseong"))
    n.occasion_code = "D7"
    back = persist.from_dict(persist.to_dict(n))
    assert back.occasion.value == NEW_OUT and back.occasion_code == "D7"


def _meta():
    return {"line": "견본 500ml", "concept": {"name": "견본"}, "status": "done", "shelf_products": [],
            "participants": [{"visit": "T1", "age": "19-29", "sex": "여자"},
                             {"visit": "T2", "age": "19-29", "sex": "남자"}]}


def _rows():
    return [{"visit": "T1", "cond": method.CONCEPT, "uuid": "x1", "occasion": "D7", "product": "견본 500ml", "sentence": ""},
            {"visit": "T2", "cond": method.CONCEPT, "uuid": "x2", "occasion": "D8", "product": method.NO_PURCHASE}]


def test_views_show_new_names():
    meta, rows = _meta(), _rows()
    summary = result.summarize(meta, rows, {})
    assert {o["occasion"] for o in summary["by_occasion"]} == {NEW_OUT, NEW_HOME}
    ex = explore.summarize(meta, [(None, r) for r in rows])
    assert {o["occasion"] for o in ex["occasions"]} == {NEW_OUT, NEW_HOME}
    recent = waiting._recent(meta, rows, {})
    assert {r["occasion"] for r in recent} == {NEW_OUT, NEW_HOME}


def test_old_result_view_name_is_shown_new_in_brief():
    res = {"by_occasion": [{"occasion": OLD_OUT, "n": 50, "picked": 10}]}
    assert result_brief.top_occasion(res) == NEW_OUT


@pytest.mark.parametrize("said", [OLD_OUT, NEW_OUT])
def test_planner_old_or_new_name_reads_same_code(said):
    from types import SimpleNamespace

    from agent import machine
    from agent.note import Note
    from agent.steps import NONE, ReadTask

    n, log = Note(), machine.TurnLog(text=said, ids=[])
    machine._note(n, log, ReadTask(do="note", slot="occasion", value=said), SimpleNamespace(occasion_code=NONE))
    assert n.occasion.value == NEW_OUT and n.occasion_code == "D7"
    assert all("식사와 함께" not in b.sentence for b in log.received)
