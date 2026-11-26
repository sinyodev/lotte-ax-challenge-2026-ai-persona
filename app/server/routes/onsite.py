from datetime import UTC, datetime

from fastapi import APIRouter

import onsite
from onsite.purchase import outcomes
from onsite.schema import FILENAMES

router = APIRouter(prefix="/api/onsite")


@router.get("/status")
def status():
    if not onsite.available():
        return {"available": False, "built_at": None, "tables": []}
    stamp = (onsite.directory() / FILENAMES["cleaning_report"]).stat().st_mtime
    return {"available": True, "built_at": datetime.fromtimestamp(stamp, UTC).isoformat(),
            "tables": list(FILENAMES)}


@router.get("/cleaning-report")
def cleaning_report():
    return onsite.load_json("cleaning_report") if onsite.available() else []


@router.get("/concepts")
def concepts():
    return onsite.load_json("concepts") if onsite.available() else []


@router.get("/purchase-outcomes")
def purchase_outcomes():
    return outcomes()
