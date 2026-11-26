"""멈춘 매대 테스트를 이어서 돌린다(11-25). 저장된 답은 다시 묻지 않고 남은 손님만 묻는다(runner._run이 이미 그렇게 돈다)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str) -> dict[str, Any]:
    from shelftest import runner, store

    if not store.valid_id(run_id):
        raise HTTPException(status_code=404, detail="not found")
    ok = runner.resume(run_id)
    if ok is None:
        raise HTTPException(status_code=404, detail="not found")
    if not ok:
        raise HTTPException(status_code=409, detail="not stopped")
    return {"ok": True}
