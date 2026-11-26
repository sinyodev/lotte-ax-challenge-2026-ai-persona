"""승인된 화면 시안이 읽는 컨셉 진단 집계."""

from fastapi import APIRouter, HTTPException

from agent.diagnose import prototype_diagnosis

router = APIRouter(prefix="/api/w7")

@router.get("/diagnosis")
def diagnosis(pack: str | None = None) -> dict:
    try:
        return prototype_diagnosis(pack)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
