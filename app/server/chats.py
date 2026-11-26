"""대화 저장 (지시서 11의 1절).

대화마다 파일 하나: store/chats/<대화 id>.json (저장소에 올리지 않는다. 맨 위의 .gitignore).
담는 것: id, 제목, 만든 때와 고친 때, 부분, 단계, 화면의 메시지 전부(기획자의 말과 칠성이의 차례마다 내보낸 약속의 이벤트),
기획 노트 전체, 차례마다 읽기가 고른 일과 모델을 부른 기록과 걸린 시간.

- 도는 차례는 메모리에 두고, 끝나거나 명시적으로 멈출 때 쓴다. 임시 파일에 쓰고 바꿔치기해 쓰다가 끊겨도 깨지지 않는다.
- 차례가 중간에 멈추면(화면에서 멈춤을 누름) 그때까지 내보낸 것과 "멈춤"을 적고, 노트는 차례를 시작할 때의 것을 둔다.
- 화면의 메시지 목록은 화면이 보낸 것(useChat의 messages)을 따른다. 칠성이의 차례는 서버가 적어 둔 이벤트로 채운다.
  그래서 "다시 하기"(regenerate)로 화면에서 빠진 멈춘 차례는 메시지에서도 빠진다(차례의 기록 turns에는 남는다).
- 파일에 사용자의 이름이나 컴퓨터의 경로를 넣지 않는다.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from export_aisdk import ui_parts

if TYPE_CHECKING:
    from turns import Turn

STORE_DIR = Path(__file__).parent / "store" / "chats"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TITLE_CHARS = 20
REPLY_WAIT = ("choices", "confirm")  # 이것으로 끝난 차례는 "답을 기다림"

ACTIVE: dict[str, Turn] = {}  # 지금 칠성이가 일하는 대화
DELETED: set[str] = set()  # 일하는 중에 지운 대화(끝나도 다시 쓰지 않는다)


def valid_id(chat_id: Any) -> bool:
    return isinstance(chat_id, str) and bool(ID_RE.match(chat_id))


def _path(chat_id: str) -> Path:
    if not valid_id(chat_id):
        raise ValueError("대화 id가 맞지 않아요")
    return STORE_DIR / f"{chat_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(chat_id: str) -> dict[str, Any] | None:
    try:
        return json.loads(_path(chat_id).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def save(rec: dict[str, Any]) -> None:
    """임시 파일에 쓰고 바꿔치기한다."""
    if rec["id"] in DELETED:
        return
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{rec['id']}-", suffix=".tmp", dir=STORE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _path(rec["id"]))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def delete(chat_id: str) -> bool:
    path = _path(chat_id)
    if chat_id in ACTIVE:
        DELETED.add(chat_id)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


# ---------- 목록과 화면의 메시지 ----------


def stage_of(rec: dict[str, Any]) -> str:
    stage = "idea"
    for m in rec.get("messages", []):
        if m.get("role") != "assistant" or m.get("stopped"):
            continue
        for ev in m.get("events", []):
            if ev.get("t") == "stage":
                stage = ev["current"]
    return stage


def status_of(rec: dict[str, Any]) -> str:
    if rec["id"] in ACTIVE:
        return "working"
    msgs = rec.get("messages", [])
    last = msgs[-1] if msgs else None
    if last and last.get("role") == "assistant" and not last.get("stopped"):
        if any(ev.get("t") in REPLY_WAIT for ev in last.get("events", [])):
            return "waiting"
    return "idle"


TEST_STAGES = ("shelf", "result", "improve", "report", "followup")


def confirmed_concepts(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """확정한 컨셉(첫 화면의 매대 테스트 쪽, 지시서 15). 확정하지 않았으면 빈 목록."""
    note = rec.get("note")
    if not isinstance(note, dict) or not note.get("confirmed"):
        return []
    out = []
    for c in note.get("concepts") or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        out.append({"id": c["id"], "name": c.get("name") or "", "container": c.get("_container") or "",
                    "pack": c.get("pack") or "", "price": c.get("price") or ""})
    return out


def summary(rec: dict[str, Any]) -> dict[str, Any]:
    stage = stage_of(rec)
    # 매대 테스트까지 간 대화는 2부의 대화로 보인다(주소 /test/<id>, 2부의 단계 표시줄)
    part = "test" if stage in TEST_STAGES else rec.get("part", "concept")
    return {"id": rec["id"], "title": rec.get("title") or "", "updated_at": rec.get("updated_at"),
            "part": part, "stage": stage, "status": status_of(rec), "concepts": confirmed_concepts(rec)}


def listing() -> list[dict[str, Any]]:
    out = [summary(turn.record.rec) for chat_id, turn in ACTIVE.items() if chat_id not in DELETED]
    if STORE_DIR.exists():
        for p in STORE_DIR.glob("*.json"):
            if p.stem in ACTIVE:
                continue
            rec = load(p.stem)
            if rec and rec.get("id") == p.stem:
                out.append(summary(rec))
    out.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return out


def ui_messages(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """useChat이 그대로 처음 메시지로 쓰는 UI 메시지 목록."""
    out = []
    for m in rec.get("messages", []):
        if m.get("role") == "user":
            msg: dict[str, Any] = {"id": m["id"], "role": "user", "parts": [{"type": "text", "text": m.get("text", "")}]}
            if m.get("metadata"):
                msg["metadata"] = m["metadata"]
        else:
            msg = assistant_message(m)
        out.append(msg)
    return out


def assistant_message(entry: dict[str, Any]) -> dict[str, Any]:
    msg = {"id": entry["id"], "role": "assistant", "parts": ui_parts(entry.get("events", []), entry.get("session"))}
    if entry.get("stopped"):
        msg["metadata"] = {"stopped": True}
    return msg


def detail(rec: dict[str, Any]) -> dict[str, Any]:
    return {**summary(rec), "messages": ui_messages(rec)}


# ---------- 한 차례를 적는다 ----------


def _user_text(m: dict[str, Any]) -> str:
    text = "".join(p.get("text", "") for p in m.get("parts") or [] if p.get("type") == "text")
    if not text and isinstance(m.get("content"), str):
        text = m["content"]
    return text


def _sync(stored: list[dict[str, Any]], sent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """화면이 보낸 메시지 목록을 따른다. 칠성이의 차례는 적어 둔 이벤트로 채운다."""
    by_id = {m["id"]: m for m in stored if m.get("role") == "assistant"}
    out = []
    for m in sent:
        role, mid = m.get("role"), str(m.get("id") or "")
        if role == "user":
            entry: dict[str, Any] = {"role": "user", "id": mid, "text": _user_text(m)}
            if m.get("metadata"):
                entry["metadata"] = m["metadata"]
            out.append(entry)
        elif role == "assistant":
            out.append(by_id.get(mid) or {"role": "assistant", "id": mid, "events": [], "session": None,
                                          "stopped": bool((m.get("metadata") or {}).get("stopped"))})
    return out


class TurnRecord:
    """칠성이의 한 차례: 처음에 기획자의 말을 적고, 내보낸 이벤트를 모으고, 끝나거나 멈추면 쓴다."""

    def __init__(self, chat_id: str, sent: list[dict[str, Any]], *, message_id: str, source: str,
                 session: dict[str, Any] | None, planner: str, n_user: int) -> None:
        now = _now()
        self.rec = load(chat_id) or {"id": chat_id, "title": "", "created_at": now, "updated_at": now,
                                      "part": "concept", "source": source, "messages": [], "note": None, "turns": []}
        self.rec["messages"] = _sync(self.rec.get("messages", []), sent)
        self.entry: dict[str, Any] = {"role": "assistant", "id": message_id, "events": [], "session": session,
                                      "stopped": False}
        self.turn: dict[str, Any] = {"n": n_user, "message_id": message_id, "planner": planner, "started_at": now,
                                     "sec": None, "read": None, "calls": [], "stopped": False}
        self.rec.setdefault("turns", []).append(self.turn)
        self.rec["updated_at"] = now
        if not self.rec.get("title"):
            self.rec["title"] = self._first_words()
        self.started = time.monotonic()

    @property
    def id(self) -> str:
        return self.rec["id"]

    @property
    def stored_note(self) -> dict[str, Any] | None:
        return self.rec.get("note")

    def _first_words(self) -> str:
        first = next((m.get("text", "") for m in self.rec["messages"] if m.get("role") == "user"), "")
        return " ".join(first.split())[:TITLE_CHARS].strip()

    def add(self, ev: BaseModel) -> None:
        self.entry["events"].append(ev.model_dump(exclude_none=True))

    def finish(self, *, note: dict[str, Any] | None, stopped: bool, trace: dict[str, Any], calls: list[dict[str, Any]],
               error: str | None = None) -> None:
        self.entry["stopped"] = stopped
        self.rec["messages"].append(self.entry)
        self.turn.update({"sec": round(time.monotonic() - self.started, 1), "stopped": stopped,
                          "read": trace.get("read"), "calls": list(calls)})
        if error:
            self.turn["error"] = error
        if note is not None:
            self.rec["note"] = note
        product = ((note or {}).get("product") or {}).get("value")
        self.rec["title"] = product or self.rec.get("title") or self._first_words()
        self.rec["updated_at"] = _now()
        save(self.rec)
