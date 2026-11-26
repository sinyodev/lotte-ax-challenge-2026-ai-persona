"""확인한 가져오기, 수동 수정과 업무 기록을 저장한다."""

import base64
import csv
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from . import documents
from .models import LAUNCHED_STATUSES, IdeaRow, date_key, now

STORE_DIR = Path(__file__).resolve().parents[1] / "store" / "ideas"
TEXT_FILES = {".txt", ".md", ".csv", ".tsv"}
STOP_STATUSES = {"중단": "폐기", "폐기": "폐기", "단종": "단종", "보류": "보류"}
STOP = r"(?:(?:개발|출시|검토|판매)(?:을|를)?\s*)?(중단|폐기|단종|보류)"
PAST_STOP = r"했어요|했습니다|하였다|했다|합니다|한다|함|됐어요|되었습니다|됐다|됨|하기로\s*(?:최종\s*)?(?:결정했습니다|했습니다)|확정했습니다"
STOP_LABEL = re.compile(rf"^{STOP}\s*(?:사유|이유)(?:는|은)?\s*(?:[:：]|\t)\s*(.+)$")
STOP_STATE = re.compile(
    rf"^(?:(?:최종\s*)?(?:결정|상태|판정|결론|확정)\s*[:：]\s*)?"
    rf"{STOP}\s*(?:확정|결정|완료|{PAST_STOP})?[.!。]?$"
)
REASON_LABEL = re.compile(r"^(?:(?:판단|결정)\s*)?(?:사유|이유)\s*(?:[:：]|\t)\s*(.+)$")
STOP_SENTENCE = re.compile(
    rf"^(?:(.+?)(?:으로 인해|로 인해|때문에|으로|로)|"
    rf"(.+?(?:어서|아서|해서|라서|부족해|못해|낮아|높아|없어|어려워)))\s+"
    rf"{STOP}\s*(?:확정|결정|{PAST_STOP})[.!。]?$"
)
DRAFT_STOP = re.compile(
    r"(?:중단|폐기|단종|보류)(?:은|는|을|를|할)?\s*(?:예정|계획|우려|가능성|검토|권고|제안|여부|조건|하지|아님|필요)"
)
STARTED_PHASE = re.compile(
    r"^(?:오늘(?:부터)?\s+)?(?:실제\s+)?(정성\s*(?:조사|인터뷰)|정량\s*(?:조사|설문)|(?:가상|AI)\s*테스트)"
    r"(?:을|를)?\s*(?:시작|착수)(?:했어요|했습니다|했다|함)[.!。]?(?:\s+이번 조사는 제가 맡을게요[.!。]?)?$",
    re.IGNORECASE,
)
UNKNOWN_REASON = {"", "-", "–", "—", "없음", "미상", "미기재", "미확인", "기록없음", "사유없음", "사유기록없음", "미정", "n/a", "null"}
AUDIT_FIELDS = {"status": "단계", "verdict": "판정", "reason": "판단 사유", "concept": "기획 설명", "launched_on": "출시일"}
AUDIT_CHECKS = {"virtual_test": "가상 테스트", "qual": "정성 조사", "quant": "정량 조사", "launched": "출시"}


@dataclass
class Activity:
    files: int
    at: str
    text: str | None
    decision: tuple[str, str | None, str] | None = None


def latest_activity(stored: Activity | None, conversation: Activity | None) -> Activity | None:
    if stored is None or conversation is None:
        return stored or conversation
    latest = max((stored, conversation), key=lambda log: date_key(log.at))
    decision = max((stored.decision, conversation.decision), key=lambda item: date_key(item[2] if item else None))
    return Activity(stored.files, latest.at, latest.text, decision)


@contextmanager
def _connect(*, write: bool = False) -> Iterator[sqlite3.Connection | None]:
    path = STORE_DIR / "board.sqlite3"
    if not write and not path.exists():
        yield None
        return
    conn = sqlite3.connect(path, timeout=10)
    try:
        if write:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, row TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS edits (id TEXT PRIMARY KEY, changes TEXT NOT NULL, updated TEXT NOT NULL)")
            conn.execute("""CREATE TABLE IF NOT EXISTS worklog (
                idea TEXT NOT NULL, id TEXT NOT NULL, at TEXT NOT NULL, body TEXT NOT NULL,
                filename TEXT, content BLOB, PRIMARY KEY (idea, id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS log_decisions (
                idea TEXT NOT NULL, id TEXT NOT NULL, status TEXT, reason TEXT, PRIMARY KEY (idea, id))""")
        else:
            conn.execute("BEGIN")
            # 첫 저장의 트랜잭션이 열려 있을 때는 아직 보드가 없던 시점으로 읽는다.
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'imports'").fetchone():
                yield None
                return
        with conn:
            yield conn
    finally:
        conn.close()


def _read_edit(conn: sqlite3.Connection, row_id: str) -> tuple[dict, str | None]:
    record = conn.execute("SELECT changes, updated FROM edits WHERE id = ?", (row_id,)).fetchone()
    return (json.loads(record[0]), record[1]) if record else ({}, None)


def apply_edit(row: IdeaRow, changes: dict, updated: str | None) -> IdeaRow:
    if not changes:
        return row
    values = row.model_dump()
    values.update({key: value for key, value in changes.items() if key != "_decision_at"})
    values["checks"] = {**row.checks.model_dump(), **changes.get("checks", {})}
    values["updated"] = max((row.updated, updated), key=date_key)
    return IdeaRow.model_validate(values)


def project(row: IdeaRow, changes: dict, updated: str | None, activity: Activity | None,
            status_at: str | None = None, owner_at: str | None = None) -> IdeaRow:
    effective = apply_edit(row, changes, updated)
    launch_recorded = effective.was_launched or row.status in LAUNCHED_STATUSES
    stamps = changes.get("_decision_at", {})
    if owner_at and date_key(owner_at) > date_key(stamps.get("owner", updated if "owner" in changes else None)):
        effective = effective.model_copy(update={"owner": row.owner})
    edit_dates = {key: date_key(stamps.get(key, updated if key in changes else None)) for key in ("status", "reason")}
    source_date = date_key(status_at)
    if status_at:
        effective = effective.model_copy(update={key: getattr(row, key) for key in edit_dates if source_date > edit_dates[key]})
    if activity and activity.decision:
        status, reason, at = activity.decision
        decision = {key: value for key, value in {"status": status, "reason": reason}.items()
                    if date_key(at) > max(source_date, edit_dates[key])}
        effective = effective.model_copy(update=decision)
    if launch_recorded and not effective.checks.launched:
        effective = effective.model_copy(update={"checks": effective.checks.model_copy(update={"launched": True})})
    if activity:
        newest_work = date_key(activity.at) >= date_key(effective.work_date)
        effective = effective.model_copy(update={
            "last_work": activity.text if newest_work else effective.last_work,
            "work_date": activity.at if newest_work else effective.work_date,
            "attachment_count": activity.files,
            "updated": max((effective.updated, activity.at), key=date_key),
        })
    return effective


def read() -> tuple[list[IdeaRow], dict[str, tuple[dict, str]], dict[str, Activity]]:
    with _connect() as conn:
        if conn is None:
            return [], {}, {}
        imports = [IdeaRow.model_validate_json(row) for (row,) in conn.execute("SELECT row FROM imports")]
        edits = {row_id: (json.loads(changes), updated)
                 for row_id, changes, updated in conn.execute("SELECT id, changes, updated FROM edits")}
        return imports, edits, _activities(conn)


def _manual_activity(before: IdeaRow, after: IdeaRow) -> str:
    lines = [f"{label}: {getattr(after, field) or '기록 지움'}" for field, label in AUDIT_FIELDS.items()
             if getattr(after, field) != getattr(before, field)]
    lines.extend(f"{label}: {'확인' if getattr(after.checks, field) else '확인 해제'}"
                 for field, label in AUDIT_CHECKS.items()
                 if getattr(after.checks, field) != getattr(before.checks, field))
    return "\n".join(lines)


def _append_log(conn, idea, key, at, body, filename=None, content=None) -> bool:
    return bool(conn.execute("INSERT OR IGNORE INTO worklog VALUES (?, ?, ?, ?, ?, ?)",
                             (idea, key, at, body, filename, content)).rowcount)


def patch(row_id: str, original: IdeaRow | None, changes: dict, conversation: Activity | None = None,
          status_at: str | None = None, owner_at: str | None = None) -> IdeaRow | None:
    if original is None and not row_id.startswith(("import-", "manual-")):
        return None
    if original is None and not (STORE_DIR / "board.sqlite3").exists():
        return None
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    with _connect(write=True) as conn:
        assert conn is not None
        if original is None:
            record = conn.execute("SELECT row FROM imports WHERE id = ?", (row_id,)).fetchone()
            if record is None:
                return None
            original = IdeaRow.model_validate_json(record[0])
        saved, before_stamp = _read_edit(conn, row_id)
        activity = latest_activity(_activities(conn, row_id).get(row_id), conversation)
        before = project(original, saved, before_stamp, activity, status_at, owner_at)
        fields = {key: value for key, value in changes.items() if key != "checks" and getattr(before, key) != value}
        checks = {key: value for key, value in changes.get("checks", {}).items() if getattr(before.checks, key) != value}
        if not fields and not checks:
            return before
        updated = now()
        after = {**saved, **fields}
        if {"status", "reason", "owner"}.intersection(after):
            after["_decision_at"] = {key: updated if key in fields else saved.get("_decision_at", {}).get(key, before_stamp)
                                     for key in ("status", "reason", "owner") if key in after}
        if fields.get("status") in LAUNCHED_STATUSES or (before.was_launched and "status" in fields):
            checks.setdefault("launched", True)
        if checks:
            after["checks"] = {**saved.get("checks", {}), **checks}
        revised = project(original, after, updated, activity, status_at, owner_at)
        conn.execute(
            "INSERT INTO edits VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET changes = excluded.changes, updated = excluded.updated",
            (row_id, json.dumps(after, ensure_ascii=False), updated),
        )
        if body := _manual_activity(before, revised):
            _append_log(conn, row_id, f"edit-{uuid4()}", updated, body)
            activity = Activity(revised.attachment_count, updated, body, activity.decision if activity else None)
        return project(original, after, updated, activity, status_at, owner_at)


def commit(rows: list[IdeaRow]) -> list[IdeaRow]:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    with _connect(write=True) as conn:
        assert conn is not None
        saved = {}
        for row in rows:
            record = conn.execute("SELECT row FROM imports WHERE id = ?", (row.id,)).fetchone()
            if record is None:
                stored = row.model_copy(update={"updated": row.updated or now()})
                conn.execute("INSERT INTO imports VALUES (?, ?)", (row.id, stored.model_dump_json()))
            else:
                stored = IdeaRow.model_validate_json(record[0])
                if row.source == "import":
                    # 확인한 정보가 추가된 재가져오기만 보강하고, 수동 편집은 위에 그대로 겹친다.
                    dates = [date for date in (stored.launched_on, row.launched_on) if date]
                    merged = stored.model_copy(update={"concept": stored.concept or row.concept,
                                                       "launched_on": min(dates, default=None),
                                                       "chat_id": stored.chat_id or row.chat_id})
                    if merged != stored:
                        stored = merged
                        conn.execute("UPDATE imports SET row=? WHERE id=?", (stored.model_dump_json(), row.id))
            saved[row.id] = stored
        return [project(row, *_read_edit(conn, row.id), _activities(conn, row.id).get(row.id)) for row in saved.values()]


def _has_logs(conn):
    return conn is not None and conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='worklog'").fetchone()


def stop_decision(text: str) -> tuple[str, str] | None:
    parts = re.split(r"\n|(?<=[.!。])\s+(?=(?:판단\s*|결정\s*)?(?:사유|이유)\s*[:：])", text)
    lines = [line.strip().lstrip("#*- ") for line in parts if line.strip()]
    if not lines or DRAFT_STOP.search(lines[0].split(":", 1)[0]):
        return None
    found: set[tuple[str, str]] = set()
    status = None
    headers = {}
    for line in lines:
        if DRAFT_STOP.search(line):
            continue
        if "\t" in line:
            cells = [cell.strip() for cell in line.split("\t")]
            labels = {cell: index for index, cell in enumerate(cells)}
            decision_index = next((labels[name] for name in ("상태", "결정", "판정") if name in labels), None)
            reason_index = next((labels[name] for name in ("판단 사유", "중단 사유", "폐기 사유", "단종 사유", "사유", "이유")
                                 if name in labels), None)
            if decision_index is not None and reason_index is not None:
                headers = {"status": decision_index, "reason": reason_index}
                continue
            if headers and max(headers.values()) < len(cells) and (match := STOP_STATE.fullmatch(cells[headers["status"]])):
                reason = cells[headers["reason"]]
                if _has_reason(reason):
                    found.add((STOP_STATUSES[match[1]], reason))
                continue
        else:
            headers = {}
        if match := STOP_LABEL.fullmatch(line):
            status, reason = STOP_STATUSES[match[1]], match[2]
        elif match := STOP_SENTENCE.fullmatch(line):
            status, reason = STOP_STATUSES[match[3]], match[1] or match[2]
        elif match := STOP_STATE.fullmatch(line):
            status = STOP_STATUSES[match[1]]
            continue
        elif status and (match := REASON_LABEL.fullmatch(line)):
            reason = match[1]
        else:
            continue
        if _has_reason(reason):
            found.add((status, reason))
    return found.pop() if len(found) == 1 else None


def recorded_decision(text: str) -> tuple[str, str | None] | None:
    if started := STARTED_PHASE.fullmatch(text.strip()):
        phase = started[1][:2]
        return {"정성": "정성 조사 중", "정량": "정량 조사 중"}.get(phase, "가상 테스트 중"), None
    return stop_decision(text)


def _has_reason(reason: str) -> bool:
    return "".join(reason.strip().rstrip(".!。").casefold().split()) not in UNKNOWN_REASON


def _attachment_decision(filename: str | None, content: bytes | None) -> tuple[str, str | None] | None:
    if not filename or not content:
        return None
    extension = Path(filename).suffix.casefold()
    try:
        if extension in documents.OFFICE_PARTS:
            return recorded_decision(documents.extract(filename, base64.b64encode(content).decode("ascii")))
        if extension in TEXT_FILES and len(content) <= documents.MAX_TEXT_CHARS * 4:
            text = content.decode("utf-8-sig")
            if extension == ".csv":
                text = "\n".join("\t".join(row) for row in csv.reader(text.splitlines()))
            return recorded_decision(text)
    except (documents.DocumentError, UnicodeError, csv.Error):
        return None
    return None


def _activities(conn: sqlite3.Connection, idea: str | None = None) -> dict[str, Activity]:
    if not _has_logs(conn):
        return {}
    scope = " WHERE idea=?" if idea is not None else ""
    params = (idea,) if idea is not None else ()
    activity = {row_id: Activity(files, at, body or name) for row_id, files, at, body, name in conn.execute(f"""
        SELECT idea, files, at, body, filename FROM (
            SELECT idea, at, body, filename, COUNT(filename) OVER (PARTITION BY idea) AS files,
                ROW_NUMBER() OVER (PARTITION BY idea ORDER BY at DESC, id) AS recent
            FROM worklog{scope}
        ) WHERE recent=1
    """, params)}
    if not activity:
        return activity
    reviewed = conn.execute("SELECT 1 FROM sqlite_master WHERE name='log_decisions'").fetchone()
    join = "LEFT JOIN log_decisions d ON w.idea=d.idea AND w.id=d.id" if reviewed else ""
    recorded = "d.id, d.status, d.reason" if reviewed else "NULL, NULL, NULL"
    where = "AND (d.id IS NULL OR d.status IS NOT NULL)" if reviewed else ""
    if idea is not None:
        where += " AND w.idea=?"
    for row_id, key, at, body, filename, known, status, reason in conn.execute(f"""
        SELECT w.idea, w.id, w.at, w.body, w.filename, {recorded}
        FROM worklog w {join} WHERE w.id NOT LIKE 'edit-%' {where} ORDER BY w.at DESC, w.id
    """, params):
        if activity[row_id].decision:
            continue
        decision = (status, reason) if known else recorded_decision(body)
        if not known and not decision and filename and Path(filename).suffix.casefold() in TEXT_FILES | documents.OFFICE_PARTS.keys():
            file = conn.execute("SELECT content FROM worklog WHERE idea=? AND id=?", (row_id, key)).fetchone()
            decision = _attachment_decision(filename, file[0])
        if decision:
            activity[row_id].decision = (*decision, at)
    return activity


def logs(idea: str, *, include_audit: bool = True) -> list[dict]:
    with _connect() as conn:
        if not _has_logs(conn):
            return []
        scope = "" if include_audit else " AND id NOT LIKE 'edit-%'"
        return [dict(id=i, at=at, text=body, filename=name) for i, at, body, name in conn.execute(
            f"SELECT id, at, body, filename FROM worklog WHERE idea=?{scope} ORDER BY at DESC, id", (idea,))]


def case_log_text(idea_ids: list[str]) -> dict[str, list[str]]:
    """과거 사례의 검색용 텍스트만 한 번에 읽고 파일 본문은 열지 않는다."""
    result: dict[str, list[str]] = {}
    if not idea_ids:
        return result
    with _connect() as conn:
        if _has_logs(conn):
            for idea, text, filename in conn.execute(
                "SELECT idea, body, filename FROM worklog WHERE idea IN (SELECT value FROM json_each(?))",
                (json.dumps(idea_ids),),
            ):
                result.setdefault(idea, []).extend(value for value in (text, filename) if value)
    return result


def write_log(idea: str, key: str, body: str, filename: str | None, content: bytes | None):
    decision = recorded_decision(body) or _attachment_decision(filename, content)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    with _connect(write=True) as conn:
        if _append_log(conn, idea, key, now(), body, filename, content):
            conn.execute("INSERT INTO log_decisions VALUES (?, ?, ?, ?)", (idea, key, *(decision or (None, None))))


def download(idea: str, key: str):
    with _connect() as conn:
        if _has_logs(conn):
            return conn.execute("SELECT filename, content FROM worklog WHERE idea=? AND id=? AND filename IS NOT NULL",
                                (idea, key)).fetchone()
