"""지시서 14: 신제품 제안서와 경쟁 제품·자사 유사 제품 가르기. fake 어댑터만 쓴다(모델을 부르지 않는다)."""

from __future__ import annotations

import asyncio
import copy
import json
import re

import pytest
from fastapi.testclient import TestClient

import chats
import main
import onsite
from agent import machine, persist, proposal
from agent import phrases as P
from llm.base import LLMTimeout, set_llm
from llm.fake import FakeLLM
from tools import shelf

ZERO = dict(product_kind="탄산음료(저칼로리)", shelf_kind="탄산")
BANNED = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])|에이전트|페르소나|시뮬레이션|프롬프트|모델|욕구|실험")


def task(do, slot="", value="", ids=None, text=""):
    return {"do": do, "slot": slot, "value": value, "ids": ids or [], "text": text}


def read_ans(*tasks, lookups=(), **kw):
    out = {"tasks": list(tasks), "lookups": [{"tool": t, "arg": a} for t, a in lookups], "product_kind": "없음",
           "shelf_kind": "없음", "target_age": "없음", "target_sex": "없음", "occasion_code": "없음"}
    out.update(kw)
    return out


@pytest.fixture
def fake():
    f = FakeLLM()
    set_llm(f)
    return f


@pytest.fixture
def client():
    return TestClient(main.app)


def calls(fake, name):
    return [c for c in fake.calls if c["task"] == name]


def _turn(fake, conv, text, n, read):
    fake.answers["read"] = [read]

    async def run():
        return [e async for e in machine.turn(conv, text, [], n)]

    out = asyncio.run(run())
    fake.answers.pop("read", None)
    return out


def make_chat(fake, conv="chat-test1", ideas=("a", "b")) -> dict:
    """제로 탄산 → 아이디어 → 컨셉 둘(청귤 페트 500ml, 보리 캔 355ml)까지 돌려 대화 파일로 남긴다."""
    _turn(fake, conv, "제로 탄산 신제품", 1,
          read_ans(task("note", "product", "제로 탄산"), lookups=[("who", "")], **ZERO))
    _turn(fake, conv, "아이디어 줘", 2, read_ans(task("ideas")))
    _turn(fake, conv, "A랑 B로 컨셉 만들자", 3, read_ans(task("concepts", ids=list(ideas))))
    rec = {"id": conv, "title": "제로 탄산", "created_at": "2026-11-21T00:00:00+00:00",
           "updated_at": "2026-11-21T00:00:00+00:00", "part": "concept", "source": "live", "messages": [],
           "note": persist.to_dict(machine.CONVS[conv]), "turns": []}
    chats.save(rec)
    fake.calls.clear()
    return rec


def get(client, conv="chat-test1"):
    return client.get(f"/api/chats/{conv}/proposal")


# ---------- 경쟁 제품과 자사 유사 제품 ----------


def test_rivals_are_never_ours_and_own_is_ours():
    for kind in shelf.shelf_kinds():
        for container in ("캔", "페트", "병"):
            for volume in (250, 355, 500, 1000):
                assert not any(p.ours for p in shelf.rivals(kind, container, volume, True))
                own = shelf.own_similar(kind, container, volume, True)
                assert own is None or own.ours
    assert shelf.own_similar("없는 종류", "캔", 355) is None


def test_old_chat_with_ours_in_rivals_is_redrawn_without_model(fake, client):
    """옛 대화(경쟁 제품에 자사 제품이 섞이고 own 줄이 없던 때)를 열면 지금 규칙으로 다시 그린다. 모델을 부르지 않는다."""
    rec = make_chat(fake)
    note = rec["note"]
    for c in note["concepts"]:
        for k in ("_rival_names", "_own", "_own_name", "_shelf_v"):
            c.pop(k, None)
    note["concepts"][1]["_rivals"] = ["칠성사이다 캔 355ml 2,100원 2+1", "펩시콜라 캔 355ml 2,100원 1+1"]
    old_card = machine.concepts_card(persist.from_dict(copy.deepcopy(note))).model_dump(exclude_none=True)
    old_card["payload"]["items"][1]["spec"] = [r for r in old_card["payload"]["items"][1]["spec"] if r["key"] != "own"]
    for r in old_card["payload"]["items"][1]["spec"]:
        if r["key"] == "rivals":
            r["value"] = "칠성사이다 캔 355ml 2,100원 2+1\n펩시콜라 캔 355ml 2,100원 1+1"
    rec["messages"] = [{"role": "assistant", "id": "m1", "session": {"source": "live", "sample": False},
                        "stopped": False, "events": [{k: v for k, v in old_card.items()}]}]
    rec["note"] = note
    chats.save(rec)
    assert persist.shelf_stale(note)
    out = client.get(f"/api/chats/{rec['id']}").json()
    card = [p["data"] for m in out["messages"] for p in m["parts"] if p["type"] == "data-card"][-1]
    spec = {r["key"]: r["value"] for r in card["payload"]["items"][1]["spec"]}
    assert spec["rivals"] == "코카콜라 제로 페트 500ml 2,600원 1+1\n스프라이트 제로 페트 500ml 2,400원 1+1"
    assert spec["own"] == "칠성사이다 제로 페트 500ml 2,500원 1+1"
    assert not fake.calls


# ---------- 제안서 ----------


def test_no_concepts_is_404(fake, client):
    assert get(client, "chat-none").status_code == 404
    _turn(fake, "chat-idea", "제로 탄산 신제품", 1,
          read_ans(task("note", "product", "제로 탄산"), lookups=[("who", "")], **ZERO))
    chats.save({"id": "chat-idea", "title": "", "messages": [], "source": "live", "turns": [],
                "note": persist.to_dict(machine.CONVS["chat-idea"])})
    assert get(client, "chat-idea").status_code == 404


def test_shape(fake, client):
    make_chat(fake)
    r = get(client)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"date", "dept", "pages"} and body["dept"] == "상품기획팀"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", body["date"])
    assert len(body["pages"]) == 2
    p = body["pages"][0]
    assert set(p) == {"concept_id", "title", "gist", "background", "overview", "sketch", "compare", "plan", "sources",
                      "notice", "test", "notices", "image"}  # test, notices: 지시서 17
    assert p["image"] is None or isinstance(p["image"], str)  # 예시 이미지 주소
    assert p["test"] is None and p["notices"] == [P.PROPOSAL_NOTICE]
    assert p["title"].endswith(" (가칭)") and p["notice"] == P.PROPOSAL_NOTICE
    assert [o["label"] for o in p["overview"]] == [l for l, _ in P.OVERVIEW_ROWS if l in {o["label"] for o in p["overview"]}]
    ov = {o["label"]: o["value"] for o in p["overview"]}
    assert ov["용기와 용량"] == "500ml 페트" and ov["판매 채널"] == "편의점, 대형마트·SSM"
    assert set(p["sketch"]) == {"headline", "name", "benefit", "points", "price", "pack"}
    rows = p["compare"]["rows"]
    assert rows[0] == {"role": "proposal", "name": p["sketch"]["name"], "pack": "500ml 페트", "price": p["sketch"]["price"],
                       "promo": "-"}
    assert rows[1] == {"role": "rival", "name": "코카콜라 제로", "pack": "500ml 페트", "price": "2,600원",
                       "promo": "1+1"}
    assert re.fullmatch(r"동일 용량대 판매가 [\d,]+(~[\d,]+)?원", p["compare"]["range"])
    assert p["compare"]["pod"]
    assert p["plan"] == P.proposal_plan("음료", True) and "가상 소비자 300명" in p["plan"][0]
    # 배경(fake): "배 자주 마셔요"인 찾아본 것 하나를 보고서체로. 각주는 출처의 이름(건수는 뺀다)
    assert len(p["background"]) == 1 and p["background"][0]["refs"] == [1]
    assert p["background"][0]["text"].endswith("배 자주 마심")
    assert p["sources"] == [{"n": 1, "text": "2024 국민건강영양조사 식품섭취조사"}]
    assert p["gist"].endswith("제안함") and "500ml 페트" in p["gist"]
    # 모델에게 넘긴 글: 컨셉의 값과 찾아본 것뿐(대화 원문, 경로 없음). 웹 검색 없음
    c = calls(fake, "proposal")
    assert len(c) == 1 and not c[0]["web"]
    assert "A랑 B로 컨셉 만들자" not in c[0]["user"] and "/Users" not in c[0]["user"]
    assert "id ev-1:" in c[0]["user"]


def test_own_product_only_in_own_row(fake, client):
    make_chat(fake)
    for p in get(client).json()["pages"]:
        rows = p["compare"]["rows"]
        assert [r["role"] for r in rows] == ["proposal", "rival", "rival", "own"]
        for r in rows[1:]:
            product = next((q for q in shelf.products()
                            if proposal.short_name(q.name) == r["name"] and proposal.P.pack(q.container, q.volume) == r["pack"]), None)
            assert product is not None and product.ours == (r["role"] == "own")
    second = get(client).json()["pages"][1]["compare"]["rows"]
    assert second[3] == {"role": "own", "name": "칠성사이다 제로", "pack": "500ml 페트", "price": "2,500원",
                         "promo": "1+1"}
    assert proposal._row("rival", shelf.by_name("스프라이트 캔 355ml"))["promo"] == "-"  # 행사가 없으면 "-"


BAD_LINES = [
    {"text": "제로 탄산은 20대가 다른 음료보다 4.5배 자주 마셔요", "evidence_ids": ["ev-1"]},  # (1) 해요체
    {"text": "제로 탄산은 20대가 다른 음료보다 5배 자주 마심", "evidence_ids": ["ev-1"]},  # (2) 받지 않은 숫자
    {"text": "AI 분석상 20대가 4.5배 자주 마심", "evidence_ids": ["ev-1"]},  # (3) 쓰지 않는 말
    {"text": "20대가 4.5배 자주 마심", "evidence_ids": ["ev-99"]},  # (4) 없는 근거 항목
    {"text": "20대가 4.5배 자주 마셔 공략이 필요함", "evidence_ids": ["ev-1"]},  # (5) 해석의 말
    {"text": "국민건강영양조사에서 20대가 4.5배 자주 마심", "evidence_ids": ["ev-1"]},  # 출처의 이름
]
GOOD_LINE = {"text": "20대가 다른 음료보다 4.5배 자주 마심", "evidence_ids": ["ev-1"]}


def _answer(gist: str, lines: list[dict]):
    def ans(system, user, schema):
        ids = schema["properties"]["pages"]["items"]["properties"]["concept_id"]["enum"]
        return {"pages": [{"concept_id": i, "gist": gist, "background": lines[:4]} for i in ids]}

    return ans


def test_checks_drop_bad_lines_after_one_rewrite(fake, client):
    make_chat(fake)
    for k in range(0, len(BAD_LINES), 3):
        fake.answers["proposal"] = _answer("20대를 겨냥해 9,999원 제로 탄산을 제안해요", [*BAD_LINES[k:k + 3], GOOD_LINE])
        chats.save({**chats.load("chat-test1"), "proposal": None})
        fake.calls.clear()
        p = get(client).json()["pages"][0]
        c = calls(fake, "proposal")
        assert len(c) == 2 and "앞의 답이 검사에 걸렸다" in c[1]["user"]  # 틀린 것을 알려 한 번 다시 쓰게 한다
        assert [b["text"] for b in p["background"]] == [GOOD_LINE["text"]]  # 또 틀린 줄은 뺀다
        assert p["gist"] == proposal.fallback_gist(persist.from_dict(chats.load("chat-test1")["note"]),
                                                   persist.from_dict(chats.load("chat-test1")["note"]).concepts[0])
    note = persist.from_dict(chats.load("chat-test1")["note"])
    for line in BAD_LINES:
        assert proposal.check_line(line["text"], line["evidence_ids"], note, background=True, blob="")
    assert not proposal.check_line(GOOD_LINE["text"], GOOD_LINE["evidence_ids"], note, background=True, blob="")


def test_rewrite_is_used_when_fixed(fake, client):
    make_chat(fake)
    good = "식사에 곁들이는 20대를 겨냥해 청귤 향 제로 탄산(500ml 페트, 1,800원)을 제안함"
    fake.answers["proposal"] = [_answer("좋은 탄산을 제안해요", [BAD_LINES[0]]), _answer(good, [GOOD_LINE])]
    p = get(client).json()["pages"][0]
    assert p["gist"] == good and p["background"][0]["text"] == GOOD_LINE["text"]
    assert "보고서체가 아님" in calls(fake, "proposal")[1]["user"]


def test_model_failure_uses_template(fake, client):
    make_chat(fake)
    fake.answers["proposal"] = LLMTimeout("시간이 넘었어요")
    r = get(client)
    assert r.status_code == 200
    pages = r.json()["pages"]
    assert [p["background"] for p in pages] == [[], []]
    assert pages[0]["gist"] == "20대를 겨냥해 제로 탄산(500ml 페트, 1,800원)을 제안함"
    assert pages[0]["sources"] == []


def test_template_without_target():
    assert P.proposal_gist(None, "제로 탄산", "500ml 페트", "2,300원") == "제로 탄산(500ml 페트, 2,300원) 신제품을 제안함"


def test_second_request_does_not_call_model(fake, client):
    make_chat(fake)
    first = get(client).json()
    stored = chats.load("chat-test1")["proposal"]
    assert set(stored) == {"fp", "date", "written"} and set(stored["written"]) == {"a", "b"}
    assert chats.load("chat-test1")["updated_at"] == "2026-11-21T00:00:00+00:00"  # 최근 대화의 차례는 그대로
    fake.calls.clear()
    assert get(client).json() == first and not calls(fake, "proposal")


def test_edited_concept_calls_again(fake, client):
    make_chat(fake)
    get(client)
    rec = chats.load("chat-test1")
    rec["note"]["concepts"][0]["name"] = "새 이름"
    chats.save(rec)
    fake.calls.clear()
    pages = get(client).json()["pages"]
    assert len(calls(fake, "proposal")) == 1 and pages[0]["title"] == "새 이름 (가칭)"


def test_paper_has_no_banned_words(fake, client):
    make_chat(fake)
    body = get(client).json()

    def walk(v):
        if isinstance(v, str):
            assert not BANNED.search(v), v
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(body)


def test_short_name_and_concept_line():
    assert proposal.short_name("코카콜라 제로 페트 500ml") == "코카콜라 제로"
    assert proposal.short_name("제주삼다수 생수 2L") == "제주삼다수"
    assert proposal.short_name("테이크핏 프로틴 초코 단백질음료") == "테이크핏 프로틴 초코 단백질음료"


# ---------- 결과 보고서: 제안서에 매대 테스트 결과(지시서 17의 C) ----------


def _with_run(fake, monkeypatch, total=20, improve_items=True):
    """대화의 첫 컨셉을 total명으로 끝까지 돌리고(fake), 고친 안 하나도 돌린 뒤 노트를 대화 파일에 남긴다."""
    from shelftest import runner

    monkeypatch.setenv("AX_REPORT_MIN", str(total))
    rec = make_chat(fake)
    n = persist.from_dict(rec["note"])
    from tools.consumer import Group

    n.group, n.occasion_code, n.target = Group(age="19-29", label="20대"), "D7", machine.Slot("20대", "planner")
    c = n.concepts[0]
    spec = machine.shelf_spec(rec["id"], n, c)
    spec.total = total

    async def go(s):
        run_id = runner.create(s)
        await runner.TASKS[run_id]
        return run_id

    base = asyncio.run(go(spec))
    n.runs[c["id"]], n.last_run = base, base
    if improve_items:
        s2 = machine.shelf_spec(rec["id"], n, c)
        s2.total = total
        runner.apply_change(s2, {"price": spec.price - 200})
        other = asyncio.run(go(s2))
        n.improve = {"base_run": base, "concept_id": c["id"], "items": [
            {"id": "A", "change": f"가격 {spec.price:,}원 → {spec.price - 200:,}원", "reason": "r",
             "values": {"price": spec.price - 200}, "run_id": other},
            {"id": "B", "change": "행사 없음 → 1+1", "reason": "r", "values": {"promo": "1+1"}}]}
    rec["note"] = persist.to_dict(n)
    chats.save(rec)
    return rec, base


def test_report_section_with_result(fake, client, monkeypatch):
    rec, base = _with_run(fake, monkeypatch)
    body = get(client).json()
    first, second = body["pages"]
    test = first["test"]
    assert test["kind"] == "result-report"
    assert set(test) >= {"head", "recommend", "decisions", "key", "limits", "opinion", "disclaimer", "evidence", "next",
                         "appendix"}
    assert test["recommend"]["verdict"] in ("research", "retest", "hold") and 2 <= len(test["recommend"]["reasons"]) <= 3
    assert 1 <= len(test["decisions"]) <= 3 and len(test["key"]) == 4
    assert test["appendix"]["method"][0] == "매대: 편의점 음료 매대 기존 55개 제품에 본 제품을 더해 56개 제품"
    assert test["appendix"]["method"][1] == "인원: 19~29세 가상 소비자 20명"
    assert re.fullmatch(r"20명 중 \d+명", test["key"][0]["value"])
    rows = test["evidence"]["variants"]
    assert [r["name"] for r in rows] == ["기존안", "가격 변경안"]  # 돌리지 않은 안은 그림에 없다
    assert rows[0]["verdict"] == "base" and rows[1]["verdict"] in ("better", "same", "worse")
    assert rows[1]["change"].endswith("원") and rows[1]["line"].startswith("가격 변경안(")
    pair = rows[1]["pair"]
    assert pair["n"] == sum(pair[k] for k in ("both", "gained", "lost", "neither")) == 20
    assert rows[1]["verdict"] == {"more": "better", "less": "worse", "unclear": "same"}[pair["verdict"]]
    assert any("같은 방문의 선택률 차이" in line for line in test["appendix"]["rules"])
    assert test["evidence"]["compare"] == [] and test["opinion"] == ""
    assert first["plan"] == [] and first["notices"] == [P.PROPOSAL_NOTICE]
    assert second["test"] is None and second["plan"] == P.proposal_plan("음료", True)  # 둘째 컨셉은 테스트하지 않았다
    text = str({k: v for k, v in test.items() if k != "appendix"})
    assert not BANNED.search(text)
    for w in ("점유율", "판매량", "매출", "구매", "전환", "유입", "신규 수요", "오차 범위", "손님"):
        assert w not in text, w


def test_report_includes_survey_and_distinguishes_missing_purchase(fake, client, monkeypatch):
    rec, _ = _with_run(fake, monkeypatch, improve_items=False)
    name = rec["note"]["concepts"][0]["name"]
    root = onsite.directory()
    root.mkdir(exist_ok=True)
    (root / "survey_summary.json").write_text(json.dumps({"concepts": {
        name: {"top2": {"order_adjusted": .5}, "leading": False}}}))
    report = get(client).json()["pages"][0]["test"]
    section, = report["evidence"]["compare"]
    assert section["title"] == "구매의향과 실제 구매"
    assert "50.0%" in section["lines"][0] and "실제 구매경험률 미측정" in section["lines"][1]
    assert "다음에 살 수도 있다" in section["lines"][2] and "가상 매대" in section["lines"][3]


def test_report_opinion_is_saved_and_shown(fake, client, monkeypatch):
    rec, base = _with_run(fake, monkeypatch, improve_items=False)
    cid = rec["note"]["concepts"][0]["id"]
    r = client.put(f"/api/chats/{rec['id']}/proposal/opinion", json={"concept_id": cid, "text": " 정량 조사로 가자 "})
    assert r.status_code == 200 and r.json()["text"] == "정량 조사로 가자"
    assert get(client).json()["pages"][0]["test"]["opinion"] == "정량 조사로 가자"
    assert chats.load(rec["id"])["updated_at"] == rec["updated_at"]
    assert client.put(f"/api/chats/{rec['id']}/proposal/opinion", json={"concept_id": "zz", "text": "x"}).status_code == 404
    assert client.put("/api/chats/nope/proposal/opinion", json={"concept_id": cid, "text": "x"}).status_code == 404


def test_report_section_threshold_and_fingerprint(fake, client, monkeypatch):
    rec, base = _with_run(fake, monkeypatch, improve_items=False)
    fp_before = proposal.fingerprint(proposal.user_prompt(persist.from_dict(rec["note"])))
    assert get(client).json()["pages"][0]["test"]["evidence"]["variants"] == []
    # 지문에는 테스트 결과를 넣지 않는다: 모델이 쓴 요지와 배경은 그대로 다시 쓴다
    stored = chats.load(rec["id"])["proposal"]
    assert stored["fp"] == fp_before and "test" not in str(stored["written"])
    n_calls = len(calls(fake, "proposal"))
    get(client)
    assert len(calls(fake, "proposal")) == n_calls
    monkeypatch.setenv("AX_REPORT_MIN", "100")  # 문턱보다 적게 다녀갔으면 결과 칸이 없고 계획은 예전 그대로
    page = get(client).json()["pages"][0]
    assert page["test"] is None and page["plan"] == P.proposal_plan("음료", True) and page["notices"] == [P.PROPOSAL_NOTICE]


def test_report_phrases_and_unclear(fake, monkeypatch):
    from agent import improve

    assert P.report_verdict("research", "가격 변경안(1,000원)") == "가격 변경안(1,000원)으로 실제 소비자 조사 진행을 권고"
    assert P.report_verdict("retest", None) == "수정 후 재테스트를 권고"
    assert P.age_band("24세 여자, 대학생") == "20대" and P.age_band("") == ""
    assert improve.verdict({"picked": 1, "n": 20, "low": 0.9, "high": 23.6}, {"picked": 2, "n": 20, "low": 2.8, "high": 30.1}) == "unclear"
