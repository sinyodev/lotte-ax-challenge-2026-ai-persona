"""지시서 11: 대화 저장과 최근 대화, 멈춤, 넓은 출발점, 추천받기의 세 길. fake 어댑터만 쓴다(모델을 부르지 않는다)."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import chats
import main
from agent import machine
from agent import phrases as P
from agent.machine import add_thought
from export_aisdk import ui_parts
from llm.base import set_llm
from llm.fake import FakeLLM


def task(do, slot="", value="", ids=None, text=""):
    return {"do": do, "slot": slot, "value": value, "ids": ids or [], "text": text}


def read_ans(*tasks, lookups=(), **kw):
    out = {"tasks": list(tasks), "lookups": [{"tool": t, "arg": a} for t, a in lookups], "product_kind": "없음",
           "shelf_kind": "없음", "target_age": "없음", "target_sex": "없음", "occasion_code": "없음"}
    out.update(kw)
    return out


ZERO = dict(product_kind="탄산음료(저칼로리)", shelf_kind="탄산")


@pytest.fixture
def fake():
    f = FakeLLM()
    set_llm(f)
    return f


@pytest.fixture
def live(monkeypatch, fake):
    monkeypatch.setenv("AX_AGENT", "live")
    return TestClient(main.app)


def _parse(text: str) -> list:
    out = []
    for raw in text.split("\n\n"):
        if raw.strip():
            payload = raw[len("data: "):]
            out.append(payload if payload == "[DONE]" else json.loads(payload))
    return out


class Screen:
    """useChat처럼: 보낸 말과 받은 칠성이의 차례를 메시지로 쌓아 다음 요청에 함께 보낸다."""

    def __init__(self, client: TestClient, chat_id: str) -> None:
        self.client = client
        self.id = chat_id
        self.messages: list[dict] = []
        self.k = 0

    def send(self, text: str, reply: dict | None = None) -> list:
        self.k += 1
        msg = {"id": f"u{self.k}", "role": "user", "parts": [{"type": "text", "text": text}]}
        if reply:
            msg["metadata"] = {"reply": reply}
        self.messages.append(msg)
        parts = _parse(self.client.post("/api/chat", json={"id": self.id, "messages": self.messages}).text)
        start = parts[0]
        self.messages.append({"id": start["messageId"], "role": "assistant", "parts": []})
        return parts


def data(parts, kind):
    return [p for p in parts if isinstance(p, dict) and p.get("type") == f"data-{kind}"]


def said(parts) -> str:
    return "".join(p["delta"] for p in parts if isinstance(p, dict) and p.get("type") == "text-delta")


# ---------- 1. 저장과 목록 ----------


def test_two_turns_are_saved_listed_and_reopened(live, fake):
    fake.answers["read"] = [read_ans(task("note", "product", "제로 탄산"), lookups=[("who", "")], **ZERO),
                            read_ans(task("ideas"))]
    s = Screen(live, "chat-a1")
    t1 = s.send("제로 탄산 신제품 하나 검토해 보고 싶어")
    actions = data(t1, "actions")[0]
    s.send("아이디어 내기", {"to": actions["id"], "ids": ["ideas"]})

    rows = live.get("/api/chats").json()
    assert [r["id"] for r in rows] == ["chat-a1"]
    row = rows[0]
    assert row["title"] == "제로 탄산" and row["part"] == "concept" and row["stage"] == "idea"
    assert row["status"] == "idle" and row["updated_at"]

    got = live.get("/api/chats/chat-a1").json()
    msgs = got["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[2]["metadata"] == {"reply": {"to": actions["id"], "ids": ["ideas"]}}
    a2 = msgs[3]["parts"]
    assert a2[0] == {"type": "step-start"} and a2[1]["type"] == "data-session"
    cards = [p for p in a2 if p["type"] == "data-card"]
    assert len({p["id"] for p in cards}) == len(cards)  # 같은 id의 카드는 하나로 합쳐진다(뒤의 것이 이긴다)
    ideas = next(p for p in cards if p["id"] == "ideas")
    assert ideas["data"]["status"] == "ready" and len(ideas["data"]["payload"]["items"]) == 3
    assert any(p["type"] == "text" and p["state"] == "done" for p in a2)

    # 파일: 노트 전체, 차례마다 읽기가 고른 일과 걸린 시간
    rec = chats.load("chat-a1")
    assert rec["note"]["product"]["value"] == "제로 탄산" and len(rec["note"]["ideas"]) == 3
    assert [t["read"]["tasks"][0]["do"] for t in rec["turns"]] == ["note", "ideas"]
    assert all(t["sec"] is not None and not t["stopped"] for t in rec["turns"])
    assert "/Users" not in json.dumps(rec, ensure_ascii=False)


def test_title_falls_back_to_first_words_and_waiting_status(live, fake):
    fake.answers["read"] = [read_ans(task("answer", text="안녕하세요 반가워요 오늘 처음 써 봐요 잘 부탁해요"))]
    s = Screen(live, "chat-b1")
    s.send("안녕하세요 반가워요 오늘 처음 써 봐요 잘 부탁해요")
    row = live.get("/api/chats").json()[0]
    assert row["title"] == "안녕하세요 반가워요 오늘 처음 써 봐요 잘 부탁해요"[:20] and len(row["title"]) <= 20
    assert row["status"] == "waiting"  # 무엇을 생각하는지 묻고 추천받기 칩을 내밀었다


def test_server_restart_continues_from_file(live, fake):
    fake.answers["read"] = [read_ans(task("note", "product", "제로 탄산"), lookups=[("who", "")], **ZERO),
                            read_ans(task("ideas"))]
    s = Screen(live, "chat-c1")
    s.send("제로 탄산 신제품")
    machine.reset()  # 서버가 다시 뜬 것처럼
    t2 = s.send("아이디어 줘")
    assert said(t2) != P.SESSION_LOST
    assert len(data(t2, "card")[-1]["data"]["payload"]["items"]) >= 1
    assert machine.CONVS["chat-c1"].product.value == "제로 탄산"


def test_delete_and_not_found(live, fake):
    fake.answers["read"] = [read_ans(task("note", "product", "제로 탄산"), **ZERO)]
    Screen(live, "chat-d1").send("제로 탄산")
    assert live.delete("/api/chats/chat-d1").json() == {"ok": True}
    assert live.get("/api/chats").json() == []
    assert live.get("/api/chats/chat-d1").status_code == 404
    assert live.delete("/api/chats/chat-d1").status_code == 404
    assert live.get("/api/chats/..%2Fx").status_code == 404


def test_replay_chats_are_saved_too(monkeypatch, fake):
    from replay import play

    async def fast_play(events, sleep=None):
        async def no_sleep(_):
            return None

        async for ev in play(events, sleep=no_sleep):
            yield ev

    monkeypatch.setattr(main, "play", fast_play)
    client = TestClient(main.app)
    Screen(client, "chat-r1").send("제로 탄산")
    got = client.get("/api/chats/chat-r1").json()
    assert got["messages"][1]["parts"][1] == {"type": "data-session", "id": "session",
                                              "data": {"source": "replay", "sample": True}}
    assert chats.load("chat-r1")["source"] == "replay"


def test_ui_parts_merge_same_id_in_first_place():
    events = [{"t": "activity", "id": "w-1", "label": "찾아보는 중", "status": "running"},
              {"t": "card", "id": "brief", "stage": "idea", "kind": "brief", "title": "기획 브리프", "status": "loading"},
              {"t": "say", "text": "안녕하세요."},
              {"t": "activity", "id": "w-1", "label": "찾아보는 중", "status": "done"},
              {"t": "stage", "current": "concept"}]
    parts = ui_parts(events, None)
    assert [p["type"] for p in parts] == ["step-start", "data-activity", "data-card", "text", "data-stage"]
    assert parts[1]["data"]["status"] == "done" and parts[4] == {"type": "data-stage", "id": "stage",
                                                                   "data": {"current": "concept"}}


# ---------- 2. 멈춤 ----------


async def _drain(req) -> list[str]:
    res = await main.chat(req)
    out = []
    async for chunk in res.body_iterator:
        out.append(chunk)
    return out


def test_stopped_turn_rolls_back_note_and_is_saved(monkeypatch, fake):
    monkeypatch.setenv("AX_AGENT", "live")
    fake.answers["read"] = [read_ans(task("note", "product", "제로 탄산"), lookups=[("who", "")], **ZERO),
                            read_ans(task("thought", text="아침용"), task("ideas"))]
    fake.answers["ideas"] = asyncio.CancelledError  # 아이디어를 내는 중에 화면이 멈춘 것처럼
    msgs = [{"id": "u1", "role": "user", "parts": [{"type": "text", "text": "제로 탄산"}]}]
    first = asyncio.run(_drain(main.ChatRequest(id="chat-s1", messages=msgs)))
    a1 = json.loads(first[0][len("data: "):])["messageId"]
    before = machine.snapshot("chat-s1")
    msgs += [{"id": a1, "role": "assistant", "parts": []},
             {"id": "u2", "role": "user", "parts": [{"type": "text", "text": "아침용으로 아이디어 줘"}]}]
    stopped = asyncio.run(_drain(main.ChatRequest(id="chat-s1", messages=msgs)))
    assert _parse("".join(stopped))[-2]["messageMetadata"]["stopped"] is True
    note = machine.CONVS["chat-s1"]
    assert note.thoughts == [] and note.ideas == [] and note.n == before.n  # 차례를 시작할 때의 노트
    rec = chats.load("chat-s1")
    last = rec["messages"][-1]
    assert last["role"] == "assistant" and last["stopped"] is True
    assert any(e["t"] == "activity" and e["status"] == "running" for e in last["events"])  # 그때까지 내보낸 것
    assert rec["turns"][-1]["stopped"] is True and rec["note"]["thoughts"] == []
    assert "chat-s1" not in chats.ACTIVE
    got = chats.detail(rec)
    assert got["messages"][-1]["metadata"] == {"stopped": True}
    # 다시 하기(regenerate): 멈춘 차례가 빠진 목록으로 같은 말을 다시 보낸다
    fake.answers.pop("ideas")
    fake.answers["read"] = [read_ans(task("thought", text="아침용"), task("ideas"))]
    regen = list(msgs)  # 화면은 멈춘 차례(u2 뒤의 칠성이)를 빼고 보낸다
    asyncio.run(_drain(main.ChatRequest(id="chat-s1", messages=regen)))
    rec = chats.load("chat-s1")
    assert [m["role"] for m in rec["messages"]] == ["user", "assistant", "user", "assistant"]
    assert not rec["messages"][-1]["stopped"] and machine.CONVS["chat-s1"].thoughts == ["아침용"]
    assert [t["stopped"] for t in rec["turns"]] == [False, True, False]  # 멈춘 차례는 기록에 남는다


def test_stream_error_becomes_error_part(monkeypatch, fake):
    monkeypatch.setenv("AX_AGENT", "live")

    async def broken(*a, **k):
        yield machine.Stage(current="idea")
        raise RuntimeError("boom")

    monkeypatch.setattr(machine, "turn", broken)
    client = TestClient(main.app)
    parts = Screen(client, "chat-e1").send("제로 탄산")
    assert {"type": "error", "errorText": "stream failed"} in parts and parts[-1] == "[DONE]"
    assert chats.load("chat-e1")["turns"][-1]["error"]


# ---------- 2. 추천받기의 세 길 ----------


def _is_recommend(parts) -> bool:
    ev = [p for p in data(parts, "card") if p["data"]["kind"] == "evidence"]
    choices = data(parts, "choices")
    return bool(ev) and bool(choices) and choices[0]["id"].startswith("pick-start")


def test_recommend_three_ways(live, fake):
    # 1) 첫 화면의 칩(글로 온다): 읽기를 거치지 않는다
    t = Screen(live, "chat-r-home").send("칠성이에게 추천받기")
    assert _is_recommend(t) and not [c for c in fake.calls if c["task"] == "read"]
    # 2) 글로 "추천받기"
    s = Screen(live, "chat-r-text")
    fake.answers["read"] = [read_ans(task("answer", text="안녕"))]
    t = s.send("안녕")
    t = s.send("추천받기")
    assert _is_recommend(t)
    # 3) 대화 안의 칩
    s = Screen(live, "chat-r-chip")
    fake.answers["read"] = [read_ans(task("answer", text="안녕"))]
    t1 = s.send("안녕")
    chip = data(t1, "choices")[0]
    assert chip["data"]["options"][0]["id"] == "recommend"
    t = s.send("추천받기", {"to": chip["id"], "ids": ["recommend"]})
    assert _is_recommend(t)
    # 읽기가 recommend를 고른 경우("요즘 뜨는 걸로")
    fake.answers["read"] = [read_ans(task("recommend"))]
    t = Screen(live, "chat-r-read").send("요즘 뜨는 걸로")
    assert _is_recommend(t)
    # 모두 활동 표시가 끝난다
    for cid in ("chat-r-home", "chat-r-text", "chat-r-chip", "chat-r-read"):
        last = chats.load(cid)["messages"][-1]["events"]
        running = {e["id"] for e in last if e["t"] == "activity" and e["status"] == "running"}
        done = {e["id"] for e in last if e["t"] == "activity" and e["status"] == "done"}
        assert running <= done, cid


# ---------- 3. 넓은 출발점 ----------


def test_broad_product_is_not_blocked(live, fake):
    fake.answers["read"] = [read_ans(task("note", "product", "건강음료"), lookups=[("who", "")])]
    t = Screen(live, "chat-h1").send("음 건강음료쪽?")
    assert "제품부터" not in said(t)
    actions = data(t, "actions")[0]["data"]["actions"]
    assert actions[0]["id"] == "ideas"
    assert not [c for c in fake.calls if c["task"] == "trend"]  # 가까운 종류가 없으면 찾지 않는다
    brief = [p for p in data(t, "card") if p["data"]["kind"] == "brief"][-1]
    assert brief["data"]["payload"]["fields"][0]["value"] == "건강음료"


def test_broad_thought_without_product_offers_ideas(live, fake):
    fake.answers["read"] = [read_ans(task("thought", text="아침에 마시는 것")), read_ans(task("ideas"))]
    s = Screen(live, "chat-h2")
    t = s.send("아침에 마시는 거")
    assert data(t, "actions")[0]["data"]["actions"][0]["label"] == P.BTN_IDEAS_THOUGHT
    t = s.send("이 방향으로 아이디어 내기")
    ideas = [p for p in data(t, "card") if p["data"]["kind"] == "ideas" and p["data"]["status"] == "ready"]
    assert ideas and len(ideas[-1]["data"]["payload"]["items"]) == 3


def test_no_clue_asks_and_offers_recommend(live, fake):
    fake.answers["read"] = [read_ans(task("answer", text="글쎄 잘 모르겠어"))]
    t = Screen(live, "chat-h3").send("글쎄 잘 모르겠어")  # "뭐 할 수 있어?"는 이제 칠성이 소개로 간다(test_about.py)
    assert data(t, "choices")[0]["data"]["options"][0]["id"] == "recommend"
    voice = [c for c in fake.calls if c["task"] == "voice"][-1]["user"]
    assert "(3) 물을 것: 어떤 제품이나 방향을 생각하는지 묻는다" in voice


# ---------- 4. 작은 것 ----------


def test_thoughts_merge_and_requests_are_not_thoughts():
    t: list[str] = []
    assert add_thought(t, "아침용") and t == ["아침용"]
    assert not add_thought(t, "아침용")
    assert not add_thought(t, "아침 용")
    assert add_thought(t, "아침용 탄산") and t == ["아침용 탄산"]  # 더 자세히 말한 것으로 하나
    assert add_thought(t, "유자 맛") and t == ["아침용 탄산", "유자 맛"]


def test_received_only_new_and_said_before_is_passed(live, fake):
    fake.answers["read"] = [read_ans(task("note", "product", "제로 탄산"), **ZERO),
                            read_ans(task("thought", text="아침용")),
                            read_ans(task("thought", text="아침용"), task("ideas", text="아침 컨셉을 더 강하게"))]
    s = Screen(live, "chat-m1")
    s.send("제로 탄산")
    s.send("아침용")
    s.send("아침 컨셉이 더 강한 아이디어를 줘")
    v = [c for c in fake.calls if c["task"] == "voice"][-1]["user"]
    assert "기획자의 생각 '아침용'을 받아 적었다" not in v  # 이미 받은 방향은 다시 받아 주지 않는다
    assert "칠성이가 앞에서 이미 한 말" in v
    assert machine.CONVS["chat-m1"].thoughts == ["아침용"]
