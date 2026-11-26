"""결과 보고서의 기획자 의견(지시서 32의 B-1). 대화 파일의 report_opinion({컨셉 id: 글})에 함께 둔다."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import chats

router = APIRouter(prefix="/api/chats")

OPINION_MAX = 2000


class OpinionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concept_id: str = Field(min_length=1, max_length=64)
    text: str = Field(max_length=OPINION_MAX)


@router.put("/{chat_id}/proposal/opinion")
def put_opinion(chat_id: str, req: OpinionRequest) -> dict[str, Any]:
    """기획자 의견을 저장한다. 고친 때(updated_at)는 바꾸지 않는다(최근 대화의 차례가 바뀌지 않게)."""
    rec = chats.load(chat_id) if chats.valid_id(chat_id) else None
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    concepts = ((rec.get("note") or {}).get("concepts")) or []
    if not any(c.get("id") == req.concept_id for c in concepts):
        raise HTTPException(status_code=404, detail="no concept")
    ops = rec.get("report_opinion") if isinstance(rec.get("report_opinion"), dict) else {}
    ops[req.concept_id] = req.text.strip()
    rec["report_opinion"] = ops
    chats.save(rec)
    return {"concept_id": req.concept_id, "text": ops[req.concept_id]}
