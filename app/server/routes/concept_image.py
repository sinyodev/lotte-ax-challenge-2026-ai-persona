"""컨셉의 예시 이미지(11-25). 기획자가 누를 때만 만든다(비용). 약속은 contract/README.md의 같은 이름 절."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

import chats
from imagegen import backends, prompt, store

router = APIRouter(prefix="/api/chats")
log = logging.getLogger("concept_image")

TIMEOUT = 150.0
WORKING: dict[tuple[str, str], asyncio.Task] = {}  # 지금 만드는 중인 것. 같은 컨셉은 두 번 만들지 않는다


class ImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    again: bool = False


def _url(chat_id: str, concept_id: str, version: int) -> str:
    return f"/api/chats/{chat_id}/concepts/{concept_id}/image?v={version}"


def _concept(chat_id: str, concept_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not (store.safe(chat_id) and store.safe(concept_id)):
        raise HTTPException(status_code=400, detail="id가 맞지 않아요")
    rec = chats.load(chat_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="대화가 없어요")
    note = rec.get("note") or {}
    c = next((c for c in note.get("concepts") or [] if c.get("id") == concept_id), None)
    if c is None:
        raise HTTPException(status_code=404, detail="컨셉이 없어요")
    return note, c


def _ready(chat_id: str, concept_id: str, m: dict[str, Any]) -> dict[str, Any]:
    version = int(m.get("version") or 1)
    return {"status": "ready", "url": _url(chat_id, concept_id, version), "version": version}


async def _make(chat_id: str, concept_id: str, text: str) -> dict[str, Any]:
    started = time.monotonic()
    data, backend = await backends.generate(text, timeout=TIMEOUT)
    sec = time.monotonic() - started
    m = store.save(chat_id, concept_id, data, prompt=text, backend=backend, sec=sec)
    # 시킨 글 전부나 키는 로그에 남기지 않는다.
    log.info("예시 이미지 %s/%s: %s, %.1f초, %d바이트", chat_id, concept_id, backend, sec, len(data))
    return _ready(chat_id, concept_id, m)


@router.post("/{chat_id}/concepts/{concept_id}/image")
async def make_image(chat_id: str, concept_id: str, req: ImageRequest | None = None) -> dict[str, Any]:
    note, c = _concept(chat_id, concept_id)
    key = (chat_id, concept_id)
    task = WORKING.get(key)
    if task is None or task.done():
        reason = backends.unavailable_reason()
        if reason:
            raise HTTPException(status_code=409, detail=reason)
        m = store.meta(chat_id, concept_id)
        if m and not (req and req.again):
            return _ready(chat_id, concept_id, m)
        task = asyncio.create_task(_make(chat_id, concept_id, prompt.build(c, note)))
        WORKING[key] = task
        task.add_done_callback(lambda t: WORKING.pop(key, None) if WORKING.get(key) is t else None)
    try:
        # 요청이 끊겨도 만드는 일은 끝까지 간다(다시 들어오면 그 결과를 쓴다).
        return await asyncio.wait_for(asyncio.shield(task), timeout=TIMEOUT + 5)
    except backends.Unavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except (TimeoutError, asyncio.TimeoutError):
        raise HTTPException(status_code=502, detail="이미지를 만드는 시간이 너무 오래 걸렸어요") from None
    except backends.ImageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except Exception as exc:  # 뒷단의 예상 못 한 오류. 까닭만 짧게
        log.warning("예시 이미지 실패 %s/%s: %s", chat_id, concept_id, type(exc).__name__)
        raise HTTPException(status_code=502, detail="이미지를 만들지 못했어요") from None


@router.get("/{chat_id}/concepts/{concept_id}/image/status")
def image_status(chat_id: str, concept_id: str) -> dict[str, Any]:
    _concept(chat_id, concept_id)
    task = WORKING.get((chat_id, concept_id))
    if task is not None and not task.done():
        return {"status": "working"}
    m = store.meta(chat_id, concept_id)
    if m:
        return _ready(chat_id, concept_id, m)
    if backends.unavailable_reason():
        return {"status": "unavailable"}
    return {"status": "none"}


@router.get("/{chat_id}/concepts/{concept_id}/image")
def get_image(chat_id: str, concept_id: str) -> FileResponse:
    if not (store.safe(chat_id) and store.safe(concept_id)):
        raise HTTPException(status_code=400, detail="id가 맞지 않아요")
    path = store.image_path(chat_id, concept_id)
    if path is None:
        raise HTTPException(status_code=404, detail="이미지가 없어요")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-cache"})
