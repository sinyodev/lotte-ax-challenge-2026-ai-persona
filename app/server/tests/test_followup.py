"""지어낸 조사와 창작 매대로 후속 개선(약속 v1.20)의 올리기부터 개선안까지 잇는다."""

import asyncio
import base64
import json
from dataclasses import fields, make_dataclass
from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import chats
import main
from agent import followup as talk
from agent import improve, machine, persist
from agent.note import Note
from calibrate import followup, overlay
from events import Card
from onsite.survey import CONCEPT_NAMES, RATING_FIELDS, RESPONDENT_FIELDS, SHEETS
from shelftest import method, runner, store
from test_improve_w7 import card, engine, turn  # noqa: F401 — engine은 fixture

CHAT = "chat-followup-0001"
TESTED = CONCEPT_NAMES[0]
# (낼 수 있는 가격, 구매의향, 의견): 지어낸 답
ANSWERS = [(1500, 5, "견본 추억"), (1500, 4, "견본 추억"), (1500, 4, "견본 호기심"), (1800, 5, "견본 시원"),
           (2000, 4, "견본 추억"), (1500, 2, "너무 달다"), (1500, 1, "견본 인위"), (None, 2, "너무 달다"),
           (1200, 3, "갈래 없음"), (1500, 4, "견본 호기심")]


def workbook(answers=ANSWERS, *, names=CONCEPT_NAMES, birth=2002, gender="여성") -> bytes:
    people, ratings = [], []
    for i, (wtp, intent, comment) in enumerate(answers):
        rid = f"견본-{i}"
        people.append({"rid": rid, "gender": gender, "birth_year": birth, "age_band": "19~29세", "region": "견본권역",
                       "job": "견본", "income": None, "buy_coffee": 1, "buy_soda": 1, "buy_juice": 1,
                       "main_channel": "견본", "novelty": 3, "health": 3, "price_sens": 3, "seconds": 300,
                       "order": "견본", "timestamp": "2026-10-01", "phone_hash": "겹침" if i == 0 else f"해시-{i}"})
        for p, name in enumerate(names, 1):
            mine = name == TESTED
            ratings.append({"rid": rid, "concept": name, "understand": 3, "like": 4, "distinct": 3,
                            "intent": intent if mine else 3, "price_ok": 3, "wtp": wtp if mine else None, "monthly": 1,
                            "shown_price": 1800, "price_format": "정가", "position": p, "comment": comment if mine else ""})
    people.append({**people[0], "rid": "중복", "timestamp": "2026-10-09"})
    ratings += [{**r, "rid": "중복"} for r in ratings[:len(names)]]
    out = BytesIO()
    with pd.ExcelWriter(out) as writer:
        for index, rows, names_of in ((0, people, RESPONDENT_FIELDS), (1, ratings, RATING_FIELDS)):
            pd.DataFrame(rows, columns=list(names_of.values())).rename(
                columns={v: k for k, v in names_of.items()}).to_excel(writer, sheet_name=SHEETS[index], index=False)
        pd.DataFrame([], columns=["영역", "문항 내용"]).to_excel(writer, sheet_name=SHEETS[2], index=False)
        pd.DataFrame([], columns=["구분", "항목", "모집단 비중(추정)"]).to_excel(writer, sheet_name=SHEETS[3], index=False)
    return out.getvalue()


@pytest.fixture
def tested(engine, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv("AX_FOLLOWUP_DIR", str(tmp_path / "followup"))
    concept = {"id": "a", "name": TESTED, "price": "1,800원", "pack": "500ml 페트", "_container": "페트", "_volume": 500,
               "_flavor": "견본 과일 맛", "_carb": "보통", "headline": "견본 소구", "points": []}
    note = machine.CONVS[CHAT] = Note(concepts=[concept], confirmed=True, shelf_kind="탄산")

    async def run():
        spec = machine.shelf_spec(CHAT, note, concept)
        spec.total, spec.age = 12, "19-29"
        run_id = runner.create(spec)
        await runner._run(run_id)
        return run_id

    note.last_run = note.runs["a"] = run_id = asyncio.run(run())
    return note, run_id


def upload(note, **kw):
    return followup.create(note, CHAT, "견본.xlsx", workbook(**kw))


def reply(step, upload_id, text="견본", joined=False):
    ids = [f"{step}:{upload_id}"] if joined else [step, upload_id]
    return turn(CHAT, text, ids, "followup")


def say(events):
    return next(e.text for e in events if e.t == "say")


def buttons(events):
    return [(a.id, a.label) for e in events if e.t == "actions" for a in e.actions]


def stages(events):
    return [e.current for e in events if e.t == "stage"]


@pytest.mark.parametrize(("comment", "labels"), [
    ("견본 맛이 너무 달 것 같다", ["강한 단맛"]), ("덜 달 것 같다", []), ("인위적일까", ["인위적인 맛"]), ("과일 함량이 낮다", ["낮은 과일 함량"]),
    ("기존 것과 뭐가 다른지 모르겠다", ["기존 제품과 비슷함"]), ("한정이면 굳이", ["한정이라 덜 찾음"]),
    ("한정판이니 한 번 사 볼래", ["한정판의 매력"]), ("추억이 난다", ["추억"]), ("믿음이 안 간다", ["낯선 브랜드"]),
    ("믿음이 간다", []), ("믿음이 가요", ["브랜드 신뢰"]), (None, []), (float("nan"), []), ("다른 말", []),
])
def test_opinion_rules(comment, labels):
    assert followup.classify(comment) == labels


def test_upload_aggregates_only_the_tested_concept_and_target(tested):
    note, run_id = tested
    visits = followup.concept_rows(run_id)
    uid = upload(note)
    s = followup.load(uid)
    assert s["n"] == {"raw": 11, "clean": 10, "target": 10}
    assert s["removed"] == [{"label": "중복 응답", "count": 1}]
    assert s["target"] == "20대" and s["base_run"] == run_id and s["concept"] == {"id": "a", "name": TESTED, "price": 1800}
    price, worry, hope = s["diffs"]
    assert price["text"] == "1,800원을 낼 수 있어요" and (price["actual"], price["actual_n"]) == (22, 9)
    blocked = sum(followup.PRICE_BARRIER in v["barriers"] for v in visits)
    assert price["virtual"] == round(100 * (1 - blocked / len(visits))) and price["virtual_n"] == 12
    assert (worry["actual"], worry["actual_n"]) == (30, 10) and worry["virtual"] is not None
    assert (hope["actual"], hope["virtual"], hope["virtual_n"]) == (50, None, None)
    # 1,500원은 9명 중 8명: 1500×8/9가 가장 크다
    assert s["best_price"] == 1500
    assert [p["price"] for p in s["curve"]] == list(range(1400, 2001, 100))
    best = next(p for p in s["curve"] if p["price"] == 1500)
    assert best["share"] == 88.9 and best["money"] == round(1500 * 800 / 9)
    assert s["opinions"]["good"][0] == {"text": "추억", "n": 3, "intent": 100}
    assert s["opinions"]["bad"][0] == {"text": "강한 단맛", "n": 2, "intent": 0}
    assert "10명뿐" in s["note"]
    kept = (followup.folder(uid) / "respondents.json").read_text(encoding="utf-8")
    assert "견본" not in kept and "해시" not in kept


def test_rejects_wrong_files_and_missing_tests(tested):
    note, _ = tested
    with pytest.raises(ValueError, match="엑셀"):
        followup.create(note, CHAT, "a.csv", b"x")
    with pytest.raises(ValueError, match="양식"):
        followup.create(note, CHAT, "a.xlsx", b"not excel")
    with pytest.raises(ValueError, match="20대의 답이 없어요"):
        upload(note, birth=1980)
    with pytest.raises(ValueError, match="매대 테스트 결과가 없어요"):
        followup.create(Note(), CHAT, "a.xlsx", workbook())
    with pytest.raises(ValueError, match="매대 테스트 결과가 없어요"):
        followup.create(note, "other-chat-000", "a.xlsx", workbook())
    with pytest.raises(ValueError, match="답이 없어요"):
        upload(note, names=CONCEPT_NAMES[1:])
    assert not list(followup.root().glob("fu-*"))  # 실패한 올리기는 남기지 않는다


def test_best_price_outside_the_window_is_shown():
    rows = [{"weight": 1.0, "wtp": w} for w in (2100, 2100, 2100, 2100)]
    curve, best = followup.price_curve(rows, 1800)
    assert best == 2100 and [p["price"] for p in curve][-1] == 2100
    assert followup.price_curve([{"weight": 1.0, "wtp": None}], 1800) == ([], None)


def test_overlay_matches_survey_weights_by_sex_and_is_repeatable():
    rows = [{"sex": "여자", "weight": 3.0, "wtp": 1500, "intent": 4, "opinions": ["추억"]},
            {"sex": "여자", "weight": 1.0, "wtp": None, "intent": 2, "opinions": ["강한 단맛"]},
            {"sex": "남자", "weight": 2.0, "wtp": 2000, "intent": 5, "opinions": []}]
    people = [{"uuid": f"u{i}", "sex": "여자" if i < 80 else "남자"} for i in range(100)]
    out = overlay.assign(rows, people)
    assert out == overlay.assign(rows, list(reversed(people))) and len(out) == 100
    women = [out[f"u{i}"] for i in range(80)]
    assert sum(w["wtp"] == 1500 for w in women) == 60 and sum(w["wtp"] is None for w in women) == 20
    assert out["u99"]["lines"] == ["이 제품에 낼 수 있는 가격은 2,000원까지라고 답했습니다."]
    worried = next(w for w in women if w["wtp"] is None)
    assert worried["lines"] == ["이 제품의 걱정: 단맛이 강할 것 같다"]
    # 그 성별의 응답이 없으면 전체에서 나눈다
    assert len(overlay.assign(rows[:2], people)) == 100


def test_upload_apply_ideas_conversation(tested, monkeypatch, tmp_path):
    note, run_id = tested
    monkeypatch.setattr(followup, "can_retest", lambda: False)
    uid = upload(note)
    with pytest.raises(ValueError, match="아직 조사 답을"):
        overlay.lines(uid, "fixture-person-0")

    t = reply("upload", uid, "조사 결과 올리기")
    payload = card(t, "followup")
    assert stages(t) == ["followup"] and payload["step"] == "diff" and payload["can_retest"] is False
    assert payload["track"] == {"total": 12, "original": followup.picks(run_id)["picked"], "retest": None, "improved": None}
    assert buttons(t) == [(f"apply:{uid}", talk.BTN_FIT)]  # 다시 테스트를 못 하면 버튼은 하나
    assert next(e.id for e in t if e.t == "actions") == "followup"
    assert "10명뿐" in say(t) and say(t).count("?") == 1
    assert say(t).startswith("조사 결과를 읽었어요.") and say(t).endswith("가상 소비자를 최적화할까요?")
    dumped = next(e for e in t if e.t == "card").model_dump(exclude_none=True)
    assert dumped["payload"]["diffs"][2]["virtual"] is None  # 화면은 null을 받는다
    assert payload["fit"] is None and payload["saved"] is False and payload["ideas"] == []
    Card.model_validate(dumped)

    t = reply("apply", uid, joined=True)
    applied = card(t, "followup")
    assert applied["step"] == "applied" and applied["fit"]["n"] == 12
    assert say(t) == talk.fit_text(followup.load(uid), "") and talk.RETEST_NOT_READY not in say(t)
    assert say(t).startswith("가상 소비자를 최적화했어요.") and say(t).endswith("개선안을 찾아볼까요?")
    assert buttons(t) == [(f"ideas:{uid}", talk.BTN_IDEAS)]
    got = [overlay.lines(uid, f"fixture-person-{i}") for i in range(12)]
    assert any("낼 수 있는 가격은 1,500원까지" in x for lines in got for x in lines)
    assert all("의향" not in x and "견본" not in x for lines in got for x in lines)
    assert overlay.lines(uid, "없는 사람") == []

    assert talk.RETEST_NOT_READY in say(reply("retest", uid))
    assert talk.RETEST_NOT_READY in say(reply("retest-result", uid))

    # 개선안은 후속 개선 안에서 보인다(개선안 테스트로 넘어가지 않는다)
    t = reply("ideas", uid)
    assert stages(t) == ["followup"] and not any(e.t == "card" and e.kind == "improve" for e in t)
    shown = card(t, "followup")
    assert shown["step"] == "ideas" and note.improve is None and shown["track"]["improved"] is None
    ideas = shown["ideas"]
    assert [i["kind"] for i in ideas] == ["price", "flavor", "appeal"]
    assert [i["after"] for i in ideas] == ["1,500원", "단맛을 줄인 견본 과일 맛", "어릴 때 먹던 그 맛"]
    assert all(set(i) == {"kind", "before", "after", "change", "reason", "evidence", "effect"} for i in ideas)
    assert all("소비자 조사 20대 10명 중" in i["evidence"] for i in ideas)
    assert buttons(t) == [(f"save:{uid}", talk.BTN_SAVE)] and "고칠 곳이 세 가지" in say(t)

    t = reply("save", uid)
    assert stages(t) == ["followup"] and card(t, "followup")["saved"] is True
    assert [b[0] for b in buttons(t)] == ["go-shelf", "report"]
    assert buttons(t)[0][1] == talk.BTN_SHELF_AGAIN and say(t).startswith("가상 소비자 인사이트에 추가했어요.")
    saved = json.loads((followup.root() / "insights.json").read_text(encoding="utf-8"))
    assert followup.root().is_relative_to(tmp_path) and [r["upload_id"] for r in saved] == [uid]
    assert saved[0]["people"] == 12 and saved[0]["survey_n"] == 10

    # 저장한 노트로 이어진다
    again = persist.from_dict(persist.to_dict(note))
    assert again.followup == {"upload_id": uid, "step": "ideas"}
    lines = followup.report_lines(again, {"id": "a"})
    assert any("1,500원" in x for x in lines) and all(not x.endswith("요") for x in lines)
    assert followup.report_lines(again, {"id": "b"}) == [] and followup.report_lines(Note(), {"id": "a"}) == []


def test_guidance_and_unknown_upload(tested):
    note, _ = tested
    for t in (turn(CHAT, "조사 결과 올리기"), turn(CHAT, "조사 결과 올리기", ["upload-survey"], "download-3")):
        assert say(t) == talk.ASK_FILE and buttons(t) == [(talk.UPLOAD, talk.BTN_UPLOAD)]
    assert say(reply("apply", "fu-000000000000")) == talk.GONE
    uid = upload(note)
    machine.CONVS["other-chat-000"] = Note()
    assert say(turn("other-chat-000", "x", ["apply", uid], "followup")) == talk.GONE


def _with_overlay(monkeypatch):
    """총지휘가 이을 runner.Spec.overlay를 시험에서 흉내 낸다(메타에 적고, 새 실행으로 만든다)."""
    if "overlay" in {f.name for f in fields(runner.Spec)}:
        return
    spec = make_dataclass("Spec", [("overlay", str | None, None)], bases=(runner.Spec,))
    create = runner.create

    def made(s):
        if not getattr(s, "overlay", None):
            return create(s)
        meta = store.load_meta(machine.CONVS[CHAT].last_run)
        meta = {**meta, "id": "run-0123456789ab", "overlay": s.overlay, "status": "running", "fp": "견본"}
        store.save_meta(meta)
        return meta["id"]

    monkeypatch.setattr(runner, "Spec", spec)
    monkeypatch.setattr(runner, "create", made)


def test_retest_compares_the_same_visits(tested, monkeypatch):
    note, run_id = tested
    _with_overlay(monkeypatch)
    uid = upload(note)
    assert "먼저 조사에 맞춰야" in say(reply("retest", uid))
    t = reply("apply", uid)
    assert buttons(t) == [(f"retest:{uid}", "다시 테스트하기")] and card(t, "followup")["can_retest"]
    t = reply("retest", uid)
    retest = card(t, "followup")["retest_run"]
    assert retest != run_id and card(t, "shelf-run")["run_id"] == retest
    assert buttons(t) == [(f"retest-result:{uid}", "결과 보기")]
    assert note.last_run == note.runs["a"] == run_id  # 처음 결과의 자리는 그대로 둔다
    assert "12명 중 0명" in say(reply("retest-result", uid))
    assert "12명 중 0명" in say(turn(CHAT, "결과 보기", (), "auto"))  # 테스트 카드가 스스로 보내는 말

    rows = [r for r in store.answers(run_id) if r.get("cond") == method.CONCEPT]
    line = store.load_meta(run_id)["line"]
    was = [r for r in rows if r["product"] == line]
    other = next(r["product"] for r in rows if r["product"] != line) if len(was) < len(rows) else method.NO_PURCHASE
    for r in rows:
        store.append_answer(retest, {**r, "product": other if r["product"] == line else line})
    meta = store.load_meta(retest)
    store.save_meta({**meta, "status": "done"})
    p = followup.paired(run_id, retest)
    assert (p["n"], p["before"], p["after"]) == (12, len(was), 12 - len(was))
    assert (p["gained"], p["lost"]) == (12 - len(was), len(was))
    t = turn(CHAT, "결과 보기", (), "auto")
    assert say(t).startswith("다시 테스트가 끝났어요. 실제 20대의 답에 맞추니") and card(t, "followup")["track"]["retest"] == 12 - len(was)

    out = followup.people_view(uid)
    assert out["status"] == "done" and out["total"] == out["asked"] == 12
    assert out["after"] == {"n": 12, "picked": 12 - len(was)}
    assert set(out["people"][0]) == {"id", "who", "lines", "before", "after", "said"}
    assert "fixture-person" not in str(out) and any(x["lines"] for x in out["people"])

    t = reply("ideas", uid)
    shown = card(t, "followup")  # 개선안은 후속 개선 카드에 실린다(개선안 테스트 카드를 내지 않는다)
    assert stages(t) == ["followup"] and not any(e.t == "card" and e.kind == "improve" for e in t)
    assert shown["step"] == "ideas" and shown["retest_run"] == retest and shown["track"]["retest"] == 12 - len(was)
    assert shown["ideas"] and shown["ideas"][0]["kind"] == "price" and buttons(t) == [(f"save:{uid}", talk.BTN_SAVE)]
    assert any("다시 물은 결과" in x for x in followup.report_lines(note, {"id": "a"}))


def test_one_button_fits_and_retests_and_old_buttons_still_work(tested, monkeypatch):
    note, run_id = tested
    _with_overlay(monkeypatch)
    uid = upload(note)
    t = reply("upload", uid)
    assert buttons(t) == [(f"apply-retest:{uid}", "가상 소비자 고치고 다시 테스트"), (f"ideas:{uid}", talk.BTN_IDEAS)]
    assert say(t).endswith("같은 12명에게 다시 물어볼까요?")
    t = reply("apply-retest", uid, joined=True)
    retest = card(t, "followup")["retest_run"]
    assert retest and retest != run_id and card(t, "shelf-run")["run_id"] == retest
    assert say(t).startswith("가상 소비자 12명을 실제 20대와 같은 비율로 맞췄어요. 가상 소비자 12명에게")
    assert buttons(t) == [(f"retest-result:{uid}", "결과 보기")]
    # 옛 대화의 버튼(apply:, retest:)도 그대로 간다
    assert buttons(reply("apply", uid)) == [(f"retest:{uid}", "다시 테스트하기")]
    assert card(reply("retest", uid), "followup")["retest_run"]


def test_diff_text_follows_the_sample_words():
    survey = {"target": "20대", "n": {"raw": 200, "target": 90}, "removed": [{"label": "중복 응답", "count": 7}],
              "concept": {"name": "견본 음료", "price": 1800},
              "diffs": [{"id": "price", "virtual": 100, "actual": 40.4}, {"id": "worry", "virtual": 30, "actual": 12},
                        {"id": "hope", "virtual": None, "actual": 50}]}
    assert talk.diff_text(survey, 300) == (
        "조사 결과를 읽었어요. 200명 가운데 중복이거나 성의 없는 답 7명을 빼고, 20대 90명의 답을 봤어요.\n\n"
        "제 예상과 두 가지가 달랐어요.\n"
        "가격: 저는 모두 1,800원을 낼 거라고 봤는데, 실제로는 40%만 내겠다고 했어요.\n"
        "맛: 저는 30%가 맛을 걱정할 거라고 봤는데, 실제로는 12%였어요.\n\n"
        "실제 20대의 답에 맞춰 가상 소비자를 고치고, 같은 300명에게 다시 물어볼까요?")
    same = {**survey, "removed": [], "diffs": [{"id": "price", "virtual": 50, "actual": 52}]}
    assert "200명 가운데 20대 90명" in talk.diff_text(same, 300) and "제 예상과 거의 같았어요." in talk.diff_text(same, 300)
    p = {"n": 290, "before": 12, "after": 10, "lost": 4, "gained": 2, "clear": False}
    assert talk.retest_text(p, 300, survey) == (
        "다시 테스트가 끝났어요. 두 번 모두 답한 290명으로 보면, 실제 20대의 답에 맞추니 견본 음료를 고른 사람이 12명에서 10명으로 줄었어요.\n\n"
        "4명이 빠지고 2명이 새로 골랐어요. 이 차이는 우연일 수 있어요.\n\n"
        "빠진 사람을 다시 데려올 개선안을 조사에서 찾아볼까요?")


def test_http(tested):
    note, run_id = tested
    chats.save({"id": CHAT, "title": "", "created_at": "", "updated_at": "", "part": "test", "source": "live",
                "messages": [], "note": persist.to_dict(note), "turns": []})
    client = TestClient(main.app)

    def post(content, chat=CHAT, name="조사.xlsx"):
        return client.post("/api/followup/upload", json={
            "chat_id": chat, "filename": name, "content_base64": base64.b64encode(content).decode()})

    res = post(workbook())
    assert res.status_code == 200
    uid = res.json()["upload_id"]
    assert post(b"broken").status_code == 422 and post(b"broken").json()["detail"].endswith("요.")
    assert post(workbook(), name="a.pdf").status_code == 422
    assert post(workbook(), chat="no-such-chat-00").status_code == 404
    out = client.get(f"/api/followup/{uid}/people").json()
    assert out["status"] == "ready" and out["total"] == 12 and out["after"] == {"n": 0, "picked": 0}
    assert out["people"][0]["after"] is None and out["people"][0]["lines"] == []
    assert client.get(f"/api/followup/{uid}").json()["step"] == "diff"
    for bad in ("fu-000000000000", "..%2f..", "run-000000000000"):
        assert client.get(f"/api/followup/{bad}/people").status_code == 404


def test_survey_idea_is_shown_first_without_reordering():
    note = machine.Note()
    old, new = {"id": "A"}, {"id": "B", "followup": "up-1"}
    note.improve = {"base_run": "run-1", "items": [old, new]}
    assert machine._survey_focus(note) is None
    note.followup = {"upload_id": "up-1", "step": "ideas"}
    assert machine._survey_focus(note) == "B" and note.improve["items"] == [old, new]
    note.improve["adopted_item_id"] = "A"  # 예전 안을 채택했어도 새 조사의 안이 먼저다
    assert machine._survey_focus(note) == "B"
    note.improve["adopted_item_id"] = "B"
    assert machine._survey_focus(note) is None
