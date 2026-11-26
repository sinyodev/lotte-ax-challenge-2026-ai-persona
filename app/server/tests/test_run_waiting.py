"""도는 테스트의 기다리는 화면(11-25): 진행, 남은 시간, 지금까지의 한 줄, 방금 다녀간 손님."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shelftest import method, result, waiting
from shelftest.method import Person

LINE = "새음료 캔 250ml"
T0 = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)


def _at(sec: float) -> str:
    return (T0 + timedelta(seconds=sec)).isoformat(timespec="milliseconds")


def _meta(total: int, mode: str = "target", participants=None) -> dict:
    return {"total": total, "mode": mode, "line": LINE, "concept": {"name": "새음료"},
            "shelf_products": [["콜라 캔 355ml", "콜라 캔 355ml", False]],
            "participants": participants or [{"visit": f"V{i:03d}", "age": "19-29", "sex": "여자"} for i in range(total)]}


def _row(i: int, cond: str, product: str, sec: float, **extra) -> dict:
    return {"visit": f"V{i:03d}", "cond": cond, "uuid": f"u{i}", "occasion": "", "product": product,
            "sentence": "시원해 보여서 골랐어요.", "at": _at(sec), **extra}


def _person(i: int, text: str = "손님 서술") -> Person:
    return Person(uuid=f"u{i}", sex="여자", band="19-29", age=24, occupation="", text=("", "", "", "", text, ""))


def test_steps_count_both_shelves_and_skips():
    meta = _meta(4)
    rows = [_row(0, method.CONCEPT, LINE, 1), _row(1, method.CONCEPT, "콜라 캔 355ml", 2),
            _row(0, method.BASELINE, "콜라 캔 355ml", 3), {"visit": "V002", "skip": True, "at": _at(4)}]
    done, total, concept, both = waiting._steps(meta, rows)
    assert (done, total, concept, both) == (5, 8, 2, 1)
    # 두 매대의 답이 다 오면 남은 걸음이 없다
    rows += [_row(1, method.BASELINE, LINE, 5), _row(3, method.CONCEPT, LINE, 6), _row(3, method.BASELINE, LINE, 7)]
    assert waiting._steps(meta, rows)[0] == 8


def test_reused_baseline_answers_do_not_start_the_bar_at_half():
    # 컨셉이 없는 매대의 답을 모두 저장분에서 다시 썼다: 손님이 다녀가기 전에는 0에서 시작한다
    meta = _meta(4)
    rows = [_row(i, method.BASELINE, "콜라 캔 355ml", 0, reused=True) for i in range(4)]
    assert waiting._steps(meta, rows)[:2] == (0, 4)
    rows.append(_row(0, method.CONCEPT, LINE, 1))
    assert waiting._steps(meta, rows)[:2] == (1, 4)
    rows += [_row(i, method.CONCEPT, LINE, 2 + i) for i in range(1, 4)]
    assert waiting._steps(meta, rows)[:2] == (4, 4)


def test_eta_from_recent_fresh_answers_only():
    rows = [_row(i, method.BASELINE, LINE, 0, reused=True) for i in range(50)]
    assert waiting._eta(rows, 100, T0.timestamp()) is None  # 다시 쓴 답뿐이면 속도를 모른다
    rows += [_row(i, method.CONCEPT, LINE, 2 * i) for i in range(11)]  # 20초에 11개 → 초당 0.5개
    eta = waiting._eta(rows, 100, (T0 + timedelta(seconds=20)).timestamp())
    assert eta == 200.0
    assert waiting._eta(rows, 0, T0.timestamp()) == 0.0


def test_recent_uses_concept_rows_newest_first_without_ids():
    meta = _meta(8)
    rows = []
    for i in range(8):
        rows.append(_row(i, method.CONCEPT, LINE if i % 3 == 0 else method.NO_PURCHASE if i == 4 else "콜라 캔 355ml", i))
    rows.append(_row(0, method.BASELINE, "콜라 캔 355ml", 20))  # 컨셉이 없는 매대의 답은 쓰지 않는다
    people = {f"u{i}": _person(i) for i in range(8)}
    people["u7"] = _person(7, "김하늘 씨는 대학생이다")
    rows[7]["sentence"] = "하늘이도 좋아해서 골랐어요."
    recent = waiting._recent(meta, rows, people)
    assert [r["visit"] for r in recent] == ["V007", "V006", "V005", "V004", "V003", "V002"]
    assert recent[0]["said"] == ""  # 이름이 든 말은 비운다
    assert recent[1] == {"visit": "V006", "age": "20대", "sex": "여자", "occasion": None, "chose": "새음료",
                         "said": "시원해 보여서 골랐어요.", "ours": True}
    assert recent[2]["chose"] == "콜라 캔 355ml" and recent[3]["chose"] == "사지 않음"
    assert all("uuid" not in r for r in recent)


def test_target_lead_needs_thirty():
    meta = _meta(40)
    rows = [_row(i, method.CONCEPT, LINE if i < 7 else "콜라 캔 355ml", i) for i in range(29)]
    pairs, _ = result.concept_visits(rows)
    assert waiting._lead(meta, pairs, None) is None
    rows.append(_row(29, method.CONCEPT, "콜라 캔 355ml", 29))
    pairs, _ = result.concept_visits(rows)
    assert waiting._lead(meta, pairs, None) == {"kind": "target", "picked": 7, "n": 30, "name": "새음료"}


def test_explore_lead_needs_ten_per_cell_and_single_leader():
    cells = [{"age": "19-29", "sex": "여자", "n": 10, "picked": 2}, {"age": "50-59", "sex": "여자", "n": 12, "picked": 5}]
    assert waiting._lead({}, [], {"cells": cells}) == {"kind": "group", "age": "50대", "sex": "여자", "picked": 5, "n": 12}
    assert waiting._lead({}, [], {"cells": [*cells[:1], {**cells[1], "n": 9}]}) is None
    assert waiting._lead({}, [], {"cells": [cells[0], {**cells[0], "sex": "남자"}]}) is None  # 공동 1위
    assert waiting._lead({}, [], {"cells": [{**c, "picked": 0} for c in cells]}) is None


def test_running_view_has_waiting_and_done_view_does_not(tmp_path, monkeypatch):
    from shelftest import runner, store

    monkeypatch.setattr(store, "RUNS_DIR", tmp_path)
    meta = {**_meta(2), "id": "run-0123456789ab", "status": "stopped", "chat_id": "c", "concept_id": "k",
            "concept": {"id": "k", "name": "새음료", "pack": "250ml 캔", "container": "캔", "volume": 250, "price": 1500},
            "target": {"age": "19-29", "sex": "여자"}, "occasion_code": None, "requested": 2, "model": "m",
            "started_at": _at(0), "updated_at": _at(0)}
    store.save_meta(meta)
    assert "waiting" not in runner.view("run-0123456789ab")
    meta["status"] = "running"
    store.save_meta(meta)
    monkeypatch.setattr(runner, "ensure_running", lambda run_id: None)
    out = runner.view("run-0123456789ab")
    assert out["waiting"]["steps_total"] == 4 and out["waiting"]["steps_done"] == 0
    assert out["waiting"]["recent"] == [] and out["waiting"]["lead"] is None and out["waiting"]["eta_s"] is None
