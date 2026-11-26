"""재생 대본과 스트림이 약속(app/contract/README.md)에 맞는지 본다."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from events import REPLY_KINDS, event_adapter
from export_aisdk import to_ui_stream
from replay import REPLAY_DIR, ScriptActivity, Wait, load_script, play

SCRIPT = load_script("zero-soda")
SOURCE_MD = (REPLAY_DIR / "zero-soda.md").read_text(encoding="utf-8")


async def _no_sleep(_: float) -> None:
    return None


def _collect(events) -> list:
    async def run():
        return [e async for e in play(events, sleep=_no_sleep)]

    return asyncio.run(run())


def _stream_lines(turn_events) -> list[str]:
    async def run():
        out = []
        async for chunk in to_ui_stream(
            play(turn_events, sleep=_no_sleep),
            message_id="m-test",
            session={"source": "replay", "sample": True},
            sleep=_no_sleep,
        ):
            out.append(chunk)
        return out

    return asyncio.run(run())


def _parse_sse(chunks: list[str]) -> list:
    """SSE 조각을 data 줄 단위로 푼다. [DONE]은 문자열로 남긴다."""
    parts = []
    for raw in "".join(chunks).split("\n\n"):
        if not raw.strip():
            continue
        assert raw.startswith("data: "), raw
        payload = raw[len("data: ") :]
        parts.append(payload if payload == "[DONE]" else json.loads(payload))
    return parts


ALL_TURNS = [pytest.param(t, id=f"turn{i + 1}") for i, t in enumerate(SCRIPT.turns)] + [
    pytest.param(SCRIPT.after, id="after")
]


def test_script_has_six_turns():
    """대본 2판: 1부 컨셉 만들기만 다룬다(아이디어 회의 차례 1~4, 컨셉 보드 차례 5~6)."""
    assert SCRIPT.sample is True
    assert len(SCRIPT.turns) == 6


def test_stages_stay_in_part_one():
    stages = [e.current for turn in SCRIPT.turns for e in turn if e.t == "stage"]
    assert stages == ["idea", "concept"]
    cards = {e.kind for turn in SCRIPT.turns for e in turn if e.t == "card"}
    assert cards == {"brief", "ideas", "concepts"}


def test_multi_choice_picks_ideas():
    """차례 4: 아이디어를 여럿 고르는 칩. 덧말이 붙는다."""
    choices = next(e for e in SCRIPT.turns[3] if e.t == "choices")
    assert choices.kind == "multi"
    assert [o.id for o in choices.options] == ["a", "b", "c"]
    assert all(o.note for o in choices.options[:3])
    ideas = next(e for e in SCRIPT.turns[3] if e.t == "card" and e.kind == "ideas")
    assert [i["id"] for i in ideas.payload["items"]] == ["a", "b", "c"]
    assert all(isinstance(i["features"], list) and i["features"] for i in ideas.payload["items"])


def test_actions_carry_notes():
    """약속 v1.1: 버튼에 설명(note)이 붙는다. 주 버튼은 하나다."""
    for turn in SCRIPT.turns[4:]:
        actions = next(e for e in turn if e.t == "actions")
        assert all(a.note for a in actions.actions)
        assert sum(1 for a in actions.actions if a.primary) == 1


def test_concepts_follow_contract_v1_4():
    concepts = next(e for e in SCRIPT.turns[4] if e.t == "card" and e.kind == "concepts")
    keys = {"id", "name", "headline", "benefit", "points", "price", "pack", "spec"}
    assert [set(i) for i in concepts.payload["items"]] == [keys, keys]
    for it in concepts.payload["items"]:
        assert len(it["points"]) == 3
        spec = {r["key"]: r["value"] for r in it["spec"]}
        assert spec["price"] == it["price"] and spec["pack"] == it["pack"]
        assert len(spec["rivals"].split("\n")) == 2


@pytest.mark.parametrize("turn", ALL_TURNS)
def test_every_event_matches_contract(turn):
    for ev in _collect(turn):
        # 약속 2절의 여덟 가지 형식으로 다시 읽혀야 한다
        event_adapter.validate_python(ev.model_dump())


@pytest.mark.parametrize("turn", ALL_TURNS)
def test_one_reply_kind_per_turn_and_never_without_say(turn):
    kinds = [e.t for e in turn]
    replies = [k for k in kinds if k in REPLY_KINDS]
    assert len(replies) <= 1
    if replies:
        assert "say" in kinds


def test_each_scripted_turn_asks_for_exactly_one_reply():
    for turn in SCRIPT.turns:
        assert sum(1 for e in turn if e.t in REPLY_KINDS) == 1


def test_ids_unique_except_updates():
    """id가 같은 것은 activity와 card(앞의 것을 바꾸는 것)뿐이다."""
    seen: dict[str, str] = {}
    for turn in SCRIPT.turns:
        for ev in turn:
            ev_id = getattr(ev, "id", None)
            if ev_id is None:
                continue
            if ev_id in seen:
                assert ev.t == seen[ev_id] and ev.t in ("card", "activity"), ev_id
            seen[ev_id] = ev.t


def test_screen_text_is_copied_from_source_script():
    """화면에 나오는 글은 대본(zero-soda.md)에서 한 글자도 바꾸지 않고 옮겼다."""
    texts: list[str] = []
    for turn in [*SCRIPT.turns, SCRIPT.after]:
        for ev in turn:
            if ev.t == "say":
                texts.append(ev.text)
            elif isinstance(ev, ScriptActivity):
                texts.append(ev.label)
            elif ev.t == "choices":
                for o in ev.options:
                    texts.append(o.label)
                    if o.note:
                        texts.append(o.note)
            elif ev.t == "actions":
                for a in ev.actions:
                    texts.append(a.label)
                    if a.note:
                        texts.append(a.note)
            elif ev.t == "confirm":
                texts += [ev.title, ev.confirm.label, ev.cancel.label]
                texts += [ev.desc] if ev.desc else []
                texts += [f"{r.label}: {r.value}" for r in ev.rows]
                texts += [r.note for r in ev.rows if r.note]
            elif ev.t == "summary":
                texts += [ev.title, ev.value, ev.note or ""]
            elif ev.t == "card":
                texts.append(ev.title)
                texts += list(_payload_texts(ev.payload))
    for text in texts:
        assert text in SOURCE_MD, text


def _payload_texts(value):
    """카드 payload 안의 글(id와 key는 빼고)."""
    if isinstance(value, str):
        yield from value.split("\n")  # 값 안의 줄바꿈(제품 특징의 경쟁 제품)은 대본에 줄마다 적었다
    elif isinstance(value, list):
        for v in value:
            yield from _payload_texts(v)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in ("id", "key", "state"):
                continue
            yield from _payload_texts(v)


@pytest.mark.parametrize("turn", ALL_TURNS)
def test_stream_starts_with_start_and_ends_with_done(turn):
    parts = _parse_sse(_stream_lines(turn))
    assert parts[0]["type"] == "start"
    assert parts[1]["type"] == "start-step"
    assert parts[2] == {"type": "data-session", "id": "session", "data": {"source": "replay", "sample": True}}
    assert parts[-3]["type"] == "finish-step"
    assert parts[-2]["type"] == "finish"
    assert parts[-1] == "[DONE]"


def test_stream_parts_follow_contract_section_3():
    parts = _parse_sse(_stream_lines(SCRIPT.turns[0]))
    stage = next(p for p in parts if isinstance(p, dict) and p["type"] == "data-stage")
    assert stage == {"type": "data-stage", "id": "stage", "data": {"current": "idea"}}

    parts = _parse_sse(_stream_lines(SCRIPT.turns[1]))
    types = [p if isinstance(p, str) else p["type"] for p in parts]
    assert "data-activity" in types and "data-card" in types
    activities = [p for p in parts if isinstance(p, dict) and p["type"] == "data-activity"]
    assert [a["data"]["status"] for a in activities] == ["running", "done"]
    assert all(a["id"] == "look-shelf" and "t" not in a["data"] and "id" not in a["data"] for a in activities)
    # 말은 text-start, 여러 text-delta, text-end로 끊어 보낸다
    deltas = [p for p in parts if isinstance(p, dict) and p["type"] == "text-delta"]
    assert len(deltas) > 3
    assert "".join(d["delta"] for d in deltas) == next(e for e in SCRIPT.turns[1] if e.t == "say").text
    assert types.index("text-start") < types.index("text-delta") < types.index("text-end")


def test_wait_is_not_sent():
    for turn in SCRIPT.turns:
        for ev in _collect(turn):
            assert not isinstance(ev, Wait)


@pytest.fixture
def client(monkeypatch):
    async def fast_play(events, sleep=None):
        async for ev in play(events, sleep=_no_sleep):
            yield ev

    monkeypatch.setattr(main, "play", fast_play)
    return TestClient(main.app)


def _user(i: int) -> dict:
    return {"id": f"u{i}", "role": "user", "parts": [{"type": "text", "text": "다음"}]}


def _post(client, n_user: int):
    messages = []
    for i in range(n_user):
        messages.append(_user(i))
        if i < n_user - 1:
            messages.append({"id": f"a{i}", "role": "assistant", "parts": []})
    return client.post("/api/chat", json={"id": "chat", "messages": messages, "mode": "suggest", "trigger": "submit-message"})


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_chat_endpoint_streams_turn_by_user_count(client):
    res = _post(client, 1)
    assert res.status_code == 200
    assert res.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert res.headers["content-type"].startswith("text/event-stream")
    parts = _parse_sse([res.text])
    assert parts[0]["type"] == "start" and parts[-1] == "[DONE]"
    assert any(isinstance(p, dict) and p.get("id") == "ask-product" for p in parts)

    res6 = _post(client, 6)
    assert any(isinstance(p, dict) and p.get("type") == "data-summary" for p in _parse_sse([res6.text]))


def test_v1_1_notes_reach_the_stream(client):
    """버튼의 note와 브리프 칸의 note가 자료 파트에 그대로 실린다."""
    parts = _parse_sse([_post(client, 5).text])
    actions = next(p for p in parts if isinstance(p, dict) and p["type"] == "data-actions")
    assert actions["data"]["actions"][0] == {
        "id": "confirm-concepts",
        "label": "컨셉 확정하기",
        "note": "이 두 컨셉으로 정해요",
        "primary": True,
    }
    parts = _parse_sse([_post(client, 1).text])
    brief = next(p for p in parts if isinstance(p, dict) and p["type"] == "data-card")
    channel = next(f for f in brief["data"]["payload"]["fields"] if f["key"] == "channel")
    assert channel["note"] == "지금은 이 매대의 상품과 가격을 알고 있어요"


def test_after_script_ends(client):
    for n in (7, 8):
        parts = _parse_sse([_post(client, n).text])
        text = "".join(p["delta"] for p in parts if isinstance(p, dict) and p["type"] == "text-delta")
        assert text == SCRIPT.after[-1].text
        assert parts[-1] == "[DONE]"


def test_source_files_exist():
    assert Path(REPLAY_DIR / "zero-soda.json").exists()
