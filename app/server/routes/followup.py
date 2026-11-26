"""후속 개선: 조사 파일 올리기와 가상 소비자의 목록 (약속 v1.20)."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import chats
from calibrate import followup

router = APIRouter(prefix="/api/followup")

MAX_BYTES = 8 * 1024 * 1024
TOO_BIG = "파일이 너무 커요. 8MB까지 올릴 수 있어요."


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: str = Field(min_length=1, max_length=64)
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str


def _note(chat_id: str) -> Any:
    from agent import machine, persist

    if not chats.valid_id(chat_id) or chat_id in chats.DELETED:
        raise HTTPException(status_code=404, detail="not found")
    note = machine.CONVS.get(chat_id)
    if note is not None:
        return note
    rec = chats.load(chat_id)
    if rec is None or not isinstance(rec.get("note"), dict):
        raise HTTPException(status_code=404, detail="not found")
    return persist.from_dict(rec["note"])


@router.post("/upload")
def upload(req: UploadRequest) -> dict[str, str]:
    note = _note(req.chat_id)
    if len(req.content_base64) > MAX_BYTES * 4 // 3 + 4:
        raise HTTPException(status_code=422, detail=TOO_BIG)
    try:
        content = base64.b64decode(req.content_base64, validate=True)
    except (binascii.Error, ValueError) as err:
        raise HTTPException(status_code=422, detail="파일을 읽지 못했어요. 다시 올려 주세요.") from err
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=422, detail=TOO_BIG)
    try:
        return {"upload_id": followup.create(note, req.chat_id, req.filename, content)}
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


def _survey(upload_id: str) -> dict[str, Any]:
    survey = followup.load(upload_id) if followup.valid_id(upload_id) else None
    if survey is None:
        raise HTTPException(status_code=404, detail="not found")
    return survey


@router.get("/{upload_id}")
def current(upload_id: str) -> dict[str, Any]:
    """카드 payload의 지금 값(다시 테스트와 개선안이 끝난 뒤의 track을 읽는 데 쓴다)."""
    survey = _survey(upload_id)
    try:
        note = _note(survey["chat_id"])
    except HTTPException:
        note = None
    step = followup.state(upload_id)["step"]
    from agent import followup as talk

    return talk.view(survey, step, getattr(note, "improve", None))


@router.get("/{upload_id}/people")
def people(upload_id: str) -> dict[str, Any]:
    _survey(upload_id)
    out = followup.people_view(upload_id)
    if out is None:
        raise HTTPException(status_code=404, detail="not found")
    return out
