"""AX편의점 서버.

띄우기: app/server에서 `uv run uvicorn main:app --port 8787`
칠성이를 고르는 것은 AX_AGENT 하나다.
- live(기본): 자료를 읽고 판단하는 칠성이(agent/machine.py). 모델 어댑터는 AX_LLM=cli|fake.
- replay: 대본을 흘려보낸다(모델을 부르지 않는다). 화면 개발과 시연의 폴백.

대화는 차례마다 파일로 남는다(chats.py, 지시서 11). 화면을 떠나도 차례는 계속되고 멈춤 요청이 오면 노트를 차례 앞으로 되돌린다.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

import chats
import turns
from agent import machine, persist
from export_aisdk import HEADERS, MEDIA_TYPE, to_ui_stream
from replay import load_script, play, turn_for

SCRIPT_NAME = "zero-soda"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        await turns.shutdown()


app = FastAPI(title="seven-eleven-ax", lifespan=lifespan)
app.include_router(__import__("routes.onsite", fromlist=["router"]).router)
app.include_router(__import__("routes.trend", fromlist=["router"]).router)
app.include_router(__import__("routes.ideas", fromlist=["router"]).router)
app.include_router(__import__("routes.report", fromlist=["router"]).router)
app.include_router(__import__("routes.w7", fromlist=["router"]).router)
app.include_router(__import__("routes.followup", fromlist=["router"]).router)
app.include_router(__import__("routes.concept_image", fromlist=["router"]).router)
app.include_router(__import__("routes.run_resume", fromlist=["router"]).router)


class ChatRequest(BaseModel):
    """useChat의 기본 전송이 보내는 본문. 약속 4절의 mode를 더한다."""

    model_config = ConfigDict(extra="allow")
    id: str | None = None
    messages: list[dict[str, Any]] = []
    mode: Literal["manual", "suggest", "delegate"] | None = None


def count_user_turns(messages: list[dict[str, Any]]) -> int:
    return sum(1 for m in messages if m.get("role") == "user")


def agent_source() -> str:
    source = os.environ.get("AX_AGENT", "live")
    if source not in ("live", "replay"):
        raise ValueError(f"AX_AGENT는 live 또는 replay: {source}")
    return source


def last_user(messages: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """기획자의 마지막 말: (글, 고른 것의 id들). 약속 4절: 칩과 버튼의 답은 metadata.reply에 실린다."""
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        text = "".join(p.get("text", "") for p in m.get("parts") or [] if p.get("type") == "text")
        if not text and isinstance(m.get("content"), str):
            text = m["content"]
        reply = (m.get("metadata") or {}).get("reply") or {}
        ids = [str(i) for i in reply.get("ids") or []]
        return text.strip(), ids
    return "", []


def last_reply_to(messages: list[dict[str, Any]]) -> str | None:
    """기획자의 마지막 말이 칩이나 버튼의 답이면 그 묶음의 id(metadata.reply.to). 결과 카드의 "이 손님에게 묻기"는 "visitor"."""
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        to = ((m.get("metadata") or {}).get("reply") or {}).get("to")
        return str(to) if to else None
    return None


@app.get("/api/health")
async def health() -> dict[str, Any]:
    if agent_source() == "live":
        return {"ok": True, "source": "live", "llm": os.environ.get("AX_LLM", "openai")}
    return {"ok": True, "source": "replay", "script": SCRIPT_NAME}


@app.get("/api/chats")
async def list_chats() -> list[dict[str, Any]]:
    return chats.listing()


def _record_or_404(chat_id: str) -> dict[str, Any]:
    turn = chats.ACTIVE.get(chat_id)
    if turn and chat_id not in chats.DELETED:
        return turn.record.rec
    rec = chats.load(chat_id) if chats.valid_id(chat_id) else None
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    return rec


@app.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str) -> dict[str, Any]:
    rec = _record_or_404(chat_id)
    out = chats.detail(rec)
    _refresh_concepts(rec, out)
    turn = chats.ACTIVE.get(chat_id)
    out["working"] = turn is not None
    if not turn:
        _refresh_improve_prompt(rec, out)
    if turn:
        out["messages"].append(chats.assistant_message(turn.record.entry))
    return out


@app.post("/api/chats/{chat_id}/stop")
async def stop_chat(chat_id: str) -> dict[str, bool]:
    turn = chats.ACTIVE.get(chat_id)
    if turn:
        await turn.stop()
    return {"ok": True}


def _refresh_improve_prompt(rec: dict[str, Any], out: dict[str, Any]) -> None:
    """예전 비교 안내는 그 차례의 후보와 매대 결과로 그린다. 저장 파일에는 쓰지 않는다."""
    from agent import improve_review

    if not rec.get("note"):
        return
    note = None
    views = {}
    messages = out["messages"]
    for message in messages:
        if message["role"] != "assistant":
            continue
        parts = message.get("parts", [])
        buttons = next((p for p in parts if p.get("type") == "data-actions"
                        and p.get("id", "").startswith("compare-plans-")), None)
        if not buttons:
            continue
        card = next((p["data"] for p in parts if p.get("type") == "data-card" and p["data"].get("kind") == "improve"), None)
        text = next((p for p in parts if p.get("type") == "text"), None)
        if not card or not text:
            continue
        payload = card.get("payload") or {}
        items = payload.get("items") or []
        if not items:
            continue
        saved = text["text"]
        if saved.startswith("지금은 ‘") and "’ 안을 펼쳤어요." in saved:
            item = next((it for it in items if it["id"] == payload.get("focus_id")), None)
            if item:
                text["text"] = improve_review.selection_text(item, item.get("paired"))
            continue
        if saved != improve_review.OLD_PROMPT and "같은 손님에게 비교해 볼 후보예요.\n• " not in saved:
            continue
        run = payload.get("base_run")
        if note is None:
            note = persist.from_dict(rec["note"])
        if run not in views:
            views[run] = machine._ready_view(run) if machine._owned_improve_run(note, rec["id"], run) else None
        view = views[run]
        if not view:
            continue
        if message is messages[-1] and note.improve and note.improve.get("base_run") == run and note.improve.get("items"):
            say, offer = improve_review.overview(note, view)
            text["text"] = say.text
            buttons["data"]["actions"] = [a.model_dump(exclude_none=True) for a in offer.actions]
            card["payload"] = machine.improve_card(note).payload
        else:
            chosen = improve_review.first_candidate(items, view["result"], payload.get("focus_id"))
            text["text"] = improve_review.brief(view["result"], chosen)


def _refresh_concepts(rec: dict[str, Any], out: dict[str, Any]) -> None:
    """옛 형식으로 저장된 컨셉 카드를 지금의 노트로 다시 만든다. 제품 특징의 줄이 없던 때의 대화(지시서 12),
    경쟁 제품에 자사 제품이 섞이고 자사 유사 제품의 줄이 없던 때의 대화(지시서 14). 모델을 부르지 않는다.

    마지막 컨셉 카드만 바꾼다. 화면은 같은 id의 카드 가운데 마지막 것을 그린다.
    """
    note = rec.get("note")
    if rec.get("source") != "live" or not isinstance(note, dict) or not note.get("concepts"):
        return
    last = None
    for m in out.get("messages", []):
        for part in m.get("parts", []):
            data = part.get("data") if isinstance(part, dict) else None
            if part.get("type") == "data-card" and isinstance(data, dict) and data.get("kind") == "concepts" \
                    and data.get("status") == "ready":
                last = data
    if last is None:
        return
    items = (last.get("payload") or {}).get("items") or []
    if items and all(i.get("spec") for i in items) and not persist.shelf_stale(note):
        return
    try:
        card = machine.concepts_card(persist.from_dict(note))
        last["payload"] = card.model_dump(exclude_none=True)["payload"]
    except Exception:  # 옛 노트를 되살리지 못하면 저장된 그대로 둔다
        return


@app.get("/api/chats/{chat_id}/proposal")
async def get_proposal(chat_id: str) -> dict[str, Any]:
    """컨셉 보드를 신제품 제안서 한 장(컨셉마다)으로(지시서 14). 컨셉이 없으면 404."""
    from agent import proposal

    rec = _record_or_404(chat_id)
    out = await proposal.build(rec)
    if out is None:
        raise HTTPException(status_code=404, detail="no concepts")
    # 컨셉 보드에서 만든 예시 이미지가 있으면 제안서의 제품 그림 자리에 넣는다
    from imagegen import store as images

    for page in out.get("pages") or []:
        m = images.meta(chat_id, page["concept_id"])
        page["image"] = (f"/api/chats/{chat_id}/concepts/{page['concept_id']}/image?v={int(m.get('version') or 1)}"
                         if m else None)
    return out


@app.get("/api/shelf")
async def get_shelf(shelf: str = "음료") -> dict[str, Any]:
    """입체 매장의 매대에 올릴 제품(지시서 13). shelf는 음료 또는 주류."""
    from tools import shelf_items

    if shelf not in shelf_items.shelves():
        raise HTTPException(status_code=404, detail="unknown shelf")
    return {"shelf": shelf, "items": shelf_items.shelf_items(shelf)}


# ---------- 매대 테스트(지시서 15) ----------


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: str
    concept_id: str
    total: int = 300
    change: dict[str, Any] | None = None


@app.post("/api/runs")
async def create_run(req: RunRequest) -> dict[str, Any]:
    """컨셉 하나를 매대에 올려 테스트를 시작한다. 같은 것이 이미 있으면 그 테스트를 준다. 컨셉이나 대화가 없으면 404."""
    from shelftest import runner

    rec = _record_or_404(req.chat_id)
    note = rec.get("note")
    if not isinstance(note, dict) or not note.get("concepts"):
        raise HTTPException(status_code=404, detail="no concepts")
    n = persist.from_dict(note)
    c = n.concept(req.concept_id)
    if c is None:
        raise HTTPException(status_code=404, detail="no such concept")
    spec = machine.shelf_spec(req.chat_id, n, c)
    spec.total = max(1, min(req.total, runner.DEFAULT_TOTAL))
    if req.change:
        spec.base_run_id = n.runs.get(c["id"])
    try:
        runner.apply_change(spec, req.change, require_original=True)
        return {"run_id": runner.create(spec)}
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    from shelftest import runner, store

    out = runner.view(run_id) if store.valid_id(run_id) else None
    if out is None:
        raise HTTPException(status_code=404, detail="not found")
    return out


@app.post("/api/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict[str, Any]:
    from shelftest import runner, store

    if not store.valid_id(run_id) or not runner.stop(run_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str) -> dict[str, Any]:
    _record_or_404(chat_id)
    chats.delete(chat_id)
    machine.forget(chat_id)
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    chat_id = req.id if chats.valid_id(req.id) else f"chat-{uuid.uuid4().hex[:12]}"
    if chat_id in chats.ACTIVE:
        raise HTTPException(status_code=409, detail="chat is working")
    text, ids = last_user(req.messages)
    n_user = count_user_turns(req.messages)
    message_id = f"chilseong-{uuid.uuid4().hex[:12]}"
    source = agent_source()
    trace: dict[str, Any] = {}

    if source == "live":
        session = {"source": "live", "sample": False}
        rec = chats.TurnRecord(chat_id, req.messages, message_id=message_id, source=source, session=session,
                               planner=text, n_user=n_user)
        # 서버가 다시 떠서 메모리에 노트가 없으면 파일의 노트로 이어 간다
        if not machine.has(chat_id) and rec.stored_note:
            machine.adopt(chat_id, persist.from_dict(rec.stored_note))
        before = machine.snapshot(chat_id)

        def finish_note(stopped: bool) -> dict[str, Any] | None:
            if stopped:
                machine.restore(chat_id, before)
            note = machine.CONVS.get(chat_id)
            return persist.to_dict(note) if note is not None else None

        events = machine.turn(chat_id, text, ids, n_user, trace=trace, reply_to=last_reply_to(req.messages))
    else:
        script = load_script(SCRIPT_NAME)
        session = {"source": "replay", "sample": script.sample}
        rec = chats.TurnRecord(chat_id, req.messages, message_id=message_id, source=source, session=session,
                               planner=text, n_user=n_user)

        def finish_note(stopped: bool) -> dict[str, Any] | None:
            return None

        events = play(turn_for(script, n_user))

    turn = turns.Turn(rec, events, finish_note, trace)
    stream = to_ui_stream(turn.stream(), message_id=message_id, session=session, stopped=lambda: turn.stopping)
    return StreamingResponse(stream, media_type=MEDIA_TYPE, headers=HEADERS)
