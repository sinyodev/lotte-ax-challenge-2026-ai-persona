"""아이디어 보드와 가져오기 API."""

import base64
import binascii
from pathlib import PurePath
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import Field

from ideas import board, similar, store
from ideas.documents import DocumentError
from ideas.importer import MAX_ROWS, PROMPT, Paste, Preview, Upload, preview
from ideas.models import BoardModel, IdeaPatch, IdeaRow, LaunchDate, now

router = APIRouter(prefix="/api/ideas")


class Items(BoardModel):
    items: list[IdeaRow]


class ImportCommit(BoardModel):
    items: list[IdeaRow] = Field(max_length=MAX_ROWS)


class NewIdea(BoardModel):
    key: UUID
    name: str = Field(min_length=1, max_length=300)
    concept: str | None = None
    launched_on: LaunchDate | None = None


class NewLog(BoardModel):
    key: UUID
    text: str = Field(default="", max_length=8000)
    filename: str | None = Field(default=None, min_length=1, max_length=255)
    content_base64: str | None = Field(default=None, max_length=4*((8*1024*1024+2)//3))


def require_idea(row_id):
    if not any(item.id == row_id for item in board.listing()):
        raise HTTPException(404, "아이디어를 찾지 못했어요.")


@router.post("", response_model=IdeaRow)
def add_idea(request: NewIdea):
    row = IdeaRow(id=f"manual-{request.key}", name=request.name, concept=request.concept,
                  launched_on=request.launched_on, status="출시" if request.launched_on else "기획 중",
                  source="manual", started=now())
    return store.commit([row])[0]


@router.get("/{row_id}/logs")
def idea_logs(row_id: str):
    items = board.work_logs(row_id)
    if items is None:
        raise HTTPException(404, "아이디어를 찾지 못했어요.")
    return {"items": items}


@router.post("/{row_id}/logs")
def add_log(row_id: str, request: NewLog):
    require_idea(row_id)
    if (request.content_base64 is None) != (request.filename is None) or not (request.text or request.filename):
        raise HTTPException(422, "진행 내용이나 첨부할 파일을 넣어 주세요.")
    content = None
    filename = None
    if request.filename:
        try:
            content = base64.b64decode(request.content_base64, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(422, "파일을 다시 선택해 주세요.")
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(422, "8MB 이하 파일을 골라 주세요.")
        filename = PurePath(request.filename.replace(chr(92), "/")).name or "attachment"
    store.write_log(row_id, str(request.key), request.text, filename, content)
    return {"items": store.logs(row_id, include_audit=False)}


@router.get("/{row_id}/logs/{key}/file")
def attachment(row_id: str, key: UUID):
    file = store.download(row_id, str(key))
    if file is None:
        raise HTTPException(404, "첨부 파일을 찾지 못했어요.")
    name, content = file
    return Response(content, media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
        "X-Content-Type-Options": "nosniff"})


@router.get("", response_model=Items)
def get_ideas():
    return {"items": board.listing()}


@router.get("/dashboard")
def get_dashboard():
    return board.dashboard()


@router.get("/cases", response_model=Items)
def get_cases(q: str = ""):
    from ideas.similarity import search_cases

    return {"items": search_cases(q)}


@router.get("/similar")
def get_similar(name: str = "", brand: str = "", category: str = "", pack: str = "", flavor: str = "", price: str = ""):
    return {"items": similar({"name": name, "brand": brand, "category": category, "pack": pack, "flavor": flavor,
                              "price": price})}


@router.get("/import/prompt")
def get_import_prompt():
    return {"prompt": PROMPT}


@router.post("/import/preview", response_model=Preview)
async def preview_import(request: Paste | Upload):
    try:
        return await preview(request)
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/import/commit", response_model=Items)
def commit_import(request: ImportCommit):
    return {"items": board.commit(request.items)}


@router.patch("/{row_id}", response_model=IdeaRow)
def update_idea(row_id: str, request: IdeaPatch):
    row = board.patch(row_id, request)
    if row is None:
        raise HTTPException(status_code=404, detail="아이디어를 찾지 못했어요.")
    return row
