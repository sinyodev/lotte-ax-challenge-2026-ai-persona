"""매대 실행별 인터뷰 기록. 기록은 통째로 바꿔 쓰고 세션을 진행하는 작업만 잠근다."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import BinaryIO

from shelftest import store

SESSION_ID = re.compile(r"group-[0-9a-f]{24}")


def session_id(run_id: str, question_id: str, mode: str, visitors: list[str]) -> str:
    key = json.dumps([run_id, question_id, mode, sorted(visitors)], ensure_ascii=False).encode()
    return "group-" + hashlib.sha256(key).hexdigest()[:24]


def _directory(run_id: str) -> Path:
    if not store.ID_RE.fullmatch(run_id):
        raise ValueError("테스트 ID가 맞지 않아요.")
    return store.RUNS_DIR / run_id / "group"


def _path(run_id: str, session_id: str) -> Path:
    if not SESSION_ID.fullmatch(session_id):
        raise ValueError("인터뷰 ID가 맞지 않아요.")
    return _directory(run_id) / f"{session_id}.json"


def read(run_id: str, session_id: str) -> dict | None:
    if not isinstance(run_id, str) or not isinstance(session_id, str):
        return None
    try:
        record = json.loads(_path(run_id, session_id).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("run_id") != run_id:
        return None
    session = record.get("session")
    if not isinstance(session, dict) or session.get("id") != session_id:
        return None
    return record


def save(record: dict) -> None:
    path = _path(record["run_id"], record["session"]["id"])
    fd, name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def claim(run_id: str, session_id: str) -> BinaryIO | None:
    """닫으면 운영체제가 잠금을 풀어 다른 요청에서 같은 기록을 이어갈 수 있다."""
    path = _path(run_id, session_id).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    except BaseException:
        handle.close()
        raise
    return handle


def completed(run_id: str) -> list[dict]:
    records = []
    for path in _directory(run_id).glob("group-*.json"):
        record = read(run_id, path.stem)
        if record and record["session"]["status"] == "done":
            records.append(record)
    return [r["session"] for r in sorted(records, key=lambda r: (r["finished_at"], r["session"]["id"]))]
