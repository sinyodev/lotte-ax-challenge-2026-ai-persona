"""칠성이의 이벤트 → AI SDK UI 메시지 스트림 (약속 3절).

스트림 형식을 아는 곳은 이 파일 하나다. 원문: app/web/node_modules/ai/docs/04-ai-sdk-ui/50-stream-protocol.mdx
나중에 AG-UI로 바꿀 때는 이 파일만 바꿔 끼운다.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import BaseModel

from events import Say, Stage
from replay import Sleep

HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
MEDIA_TYPE = "text/event-stream"


def sse(part: dict[str, Any]) -> str:
    return f"data: {json.dumps(part, ensure_ascii=False)}\n\n"


DONE = "data: [DONE]\n\n"


def data_part(event: BaseModel) -> dict[str, Any]:
    """say가 아닌 일곱 가지: {type: data-<t>, id, data: t와 id를 뺀 나머지}."""
    body = event.model_dump(exclude_none=True)
    t = body.pop("t")
    part_id = "stage" if isinstance(event, Stage) else body.pop("id")
    return {"type": f"data-{t}", "id": part_id, "data": body}


def ui_parts(events: list[dict[str, Any]], session: dict[str, Any] | None) -> list[dict[str, Any]]:
    """저장한 칠성이의 이벤트 → useChat이 처음 메시지로 쓰는 UI 메시지의 파트(지시서 11).

    스트림을 받았을 때 화면이 만드는 것과 같게: step-start, data-session, 글 파트(say마다 하나),
    자료 파트. 같은 종류와 id의 자료 파트는 처음 자리에서 뒤의 것으로 바뀐다(AI SDK의 reconciliation).
    """
    parts: list[dict[str, Any]] = [{"type": "step-start"}]
    if session is not None:
        parts.append({"type": "data-session", "id": "session", "data": session})
    where: dict[tuple[str, str], int] = {}
    for ev in events:
        body = dict(ev)
        t = body.pop("t")
        if t == "say":
            part = {"type": "text", "text": body.get("text", ""), "state": "done"}
            if body.get("speaker"):
                part["providerMetadata"] = speaker_meta(body["speaker"])
            parts.append(part)
            continue
        part_id = "stage" if t == "stage" else str(body.pop("id"))
        part = {"type": f"data-{t}", "id": part_id, "data": body}
        key = (part["type"], part_id)
        if key in where:
            parts[where[key]] = part
        else:
            where[key] = len(parts)
            parts.append(part)
    return parts


SPEAKER_KEY = "chilseong"


def speaker_meta(speaker: dict[str, Any]) -> dict[str, Any]:
    """칠성이가 아닌 화자(약속 v1.7 say.speaker)는 글 파트의 providerMetadata로 싣는다: {"chilseong": {"speaker": …}}.
    AI SDK가 text-start의 providerMetadata를 글 파트에 그대로 옮긴다."""
    return {SPEAKER_KEY: {"speaker": dict(speaker)}}


def chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


async def to_ui_stream(
    events: AsyncIterator[BaseModel],
    *,
    message_id: str,
    session: dict[str, Any] | None = None,
    stopped: Callable[[], bool] | None = None,
    chunk_size: int = 3,
    chunk_ms: int = 28,
    sleep: Sleep = asyncio.sleep,
) -> AsyncIterator[str]:
    yield sse({"type": "start", "messageId": message_id})
    yield sse({"type": "start-step"})
    if session is not None:
        yield sse({"type": "data-session", "id": "session", "data": session})
    n_text = 0
    try:
        async for ev in events:
            if isinstance(ev, Say):
                n_text += 1
                text_id = f"{message_id}-text-{n_text}"
                start: dict[str, Any] = {"type": "text-start", "id": text_id}
                if ev.speaker is not None:
                    start["providerMetadata"] = speaker_meta(ev.speaker.model_dump())
                yield sse(start)
                for piece in chunks(ev.text, chunk_size):
                    yield sse({"type": "text-delta", "id": text_id, "delta": piece})
                    await sleep(chunk_ms / 1000)
                yield sse({"type": "text-end", "id": text_id})
            else:
                yield sse(data_part(ev))
    except Exception as e:  # noqa: BLE001 — 하다가 막히면 스트림을 끊지 않고 오류 파트로 알린다(원문의 error 파트)
        print(f"[stream] {message_id} 오류: {e!r}", file=sys.stderr, flush=True)
        yield sse({"type": "error", "errorText": "stream failed"})
        yield DONE
        return
    yield sse({"type": "finish-step"})
    finish: dict[str, Any] = {"type": "finish"}
    if stopped and stopped():
        finish["messageMetadata"] = {"stopped": True}
    yield sse(finish)
    yield DONE
