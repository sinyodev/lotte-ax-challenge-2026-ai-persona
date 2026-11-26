"""예시 이미지 저장: store/images/{대화 id}/{컨셉 id}.png 와 옆의 {컨셉 id}.json(만든 시각, 시킨 글, 뒷단, 판).

store/는 저장소에 올리지 않는다(.gitignore).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IMAGES_DIR = Path(__file__).resolve().parents[1] / "store" / "images"
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def safe(value: Any) -> bool:
    return isinstance(value, str) and bool(SAFE_ID.match(value))


def _paths(chat_id: str, concept_id: str) -> tuple[Path, Path]:
    if not (safe(chat_id) and safe(concept_id)):
        raise ValueError("id가 맞지 않아요")
    folder = IMAGES_DIR / chat_id
    return folder / f"{concept_id}.png", folder / f"{concept_id}.json"


def meta(chat_id: str, concept_id: str) -> dict[str, Any] | None:
    png, info = _paths(chat_id, concept_id)
    if not png.exists():
        return None
    try:
        return json.loads(info.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"version": 1}


def image_path(chat_id: str, concept_id: str) -> Path | None:
    png, _ = _paths(chat_id, concept_id)
    return png if png.exists() else None


def _atomic(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save(chat_id: str, concept_id: str, data: bytes, *, prompt: str, backend: str, sec: float) -> dict[str, Any]:
    png, info = _paths(chat_id, concept_id)
    png.parent.mkdir(parents=True, exist_ok=True)
    old = meta(chat_id, concept_id) or {}
    record = {
        "version": int(old.get("version") or 0) + 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backend": backend,
        "sec": round(sec, 1),
        "prompt": prompt,
    }
    _atomic(png, data)
    _atomic(info, json.dumps(record, ensure_ascii=False, indent=1).encode("utf-8"))
    return record
