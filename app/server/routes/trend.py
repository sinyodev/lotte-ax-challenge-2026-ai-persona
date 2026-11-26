"""트렌드 피드와 아침 뉴스레터의 주소 및 발행 일정."""

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
import logging
import os
import sqlite3

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

import trend
from trend import publishing, sources
from trend.stories import PHOTOS, PHOTO_DIR

logger = logging.getLogger(__name__)


async def _publish_daily():
    while True:
        now = sources.now_seoul()
        try:
            await asyncio.to_thread(publishing.publish, now)
            next_at = publishing.publication_slot(now) + timedelta(days=1)
            delay = (next_at - sources.now_seoul()).total_seconds()
        except (sqlite3.Error, OSError):
            logger.exception("아침 뉴스레터 저장에 실패했어요")
            delay = 60
        await asyncio.sleep(max(0.1, delay))


@asynccontextmanager
async def lifespan(_app):
    if os.environ.get("AX_TREND_SCHEDULE") == "0":
        yield
        return
    task = asyncio.create_task(_publish_daily(), name="trend-newsletter")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


router = APIRouter(prefix="/api/trends", lifespan=lifespan)


@router.get("")
def get_feed(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return publishing.feed_packet()


@router.post("/refresh")
def refresh():
    return publishing.refresh()


@router.get("/tracking")
def get_tracking(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return publishing.tracking()


@router.get("/photos/{story_id}")
def photo(story_id: str):
    if story_id not in PHOTOS:
        raise HTTPException(status_code=404)
    name, media_type = PHOTOS[story_id]
    return FileResponse(PHOTO_DIR / name, media_type=media_type)


@router.get("/{keyword}")
def get_verdict(keyword: str):
    return trend.verdict(keyword)
