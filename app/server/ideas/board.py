"""대화, 매대 테스트, 현장 자산에서 보드 행을 읽고 수동 수정을 겹친다."""

import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from zoneinfo import ZoneInfo

import chats
import onsite
from agent.persist import upgrade_concept
from shelftest import result, store as runs

from . import store
from .models import LAUNCHED_STATUSES, STATUSES, Checks, IdeaPatch, IdeaRow, LastTest, date_key, launch_date
from onsite.concepts import CONCEPTS

ASSET_STATUS = {"운영": "출시", "단종": "단종", "개발중단": "폐기", "아이디어": "기획 중"}
RESEARCH_MAX_WON = 20_000_000
RECENT_LIMIT = 5
VOLUME = re.compile(r"\d+(?:[.,]\d+)?\s*(?:ml|cl|dl|l|cc|밀리리터|리터)(?![a-z])")
UNCERTAIN_CHAT = re.compile(
    r"[?？]|만약|가정하|가령|예를\s*들어|예시로|(?:과거|유사|타사|다른)\s*사례|"
    r"(?:다면|라면|으면|되면|줄면|늘면|오르면|떨어지면|바뀌면|할\s*경우|하는\s*경우)\b|"
    r"(?:과거|이전|지난|타사|경쟁사)\s*(?:제품|컨셉|콘셉트|아이디어|기획)|"
    r"중단했을\s*때|중단한다면|중단할까|사유를\s*(?:알려|찾아)|했는지|했나요|할까요"
)
IMPLICIT_SUBJECT = re.compile(r"^(?:이|이번|해당)\s*(?:컨셉|콘셉트|제품|아이디어|기획안?)(?:은|는|이|가|을|를|의)?\s+")
OWNER_NAME = r"(?P<name>[가-힣]{2,10}?|[A-Za-z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*){0,2}?)"
OWNER_CHANGE = (r"(?:(?:지정|배정|변경|교체)(?:해\s*줘(?:요)?|해\s*주세요|합니다|했습니다|한다|함|할게요)?"
                r"|(?:바꿔|해)\s*(?:주세요|줘(?:요)?)|할게(?:요)?)")
OWNER_STATEMENTS = (
    re.compile(rf"담당자\s*[:：]\s*{OWNER_NAME}(?:\s*님)?"),
    re.compile(rf"담당자(?:는|가)\s+{OWNER_NAME}(?:\s*님)?(?:입니다|이에요|예요|이야|야)"),
    re.compile(rf"담당자(?:를|는)?\s+{OWNER_NAME}(?:\s*님)?(?:으로|로)\s*{OWNER_CHANGE}"),
    re.compile(rf"{OWNER_NAME}(?:\s*님)?(?:을|를)\s*담당자로\s*{OWNER_CHANGE}"),
    re.compile(rf"{OWNER_NAME}(?:\s*님)?(?:이|가)\s*(?:담당(?:합니다|한다|해요)|맡(?:습니다|아요|기로\s*했습니다))"),
)
UNKNOWN_OWNER = {"누구", "누군가", "제가", "저희", "본인", "미정", "미확정", "미확인", "미상", "후보", "검토중", "tbd"}


@dataclass(frozen=True)
class ChatRecord:
    id: str
    at: str
    text: str


@dataclass(frozen=True)
class ChatDecision(ChatRecord):
    status: str
    reason: str | None


@dataclass(frozen=True)
class ChatAssignment(ChatRecord):
    owner: str | None


@dataclass(frozen=True)
class Entry:
    row: IdeaRow
    description: str = ""
    tested_at: str | None = None
    chat_records: tuple[ChatDecision | ChatAssignment, ...] = ()
    status_at: str | None = None
    owner_at: str | None = None

    def conversation_activity(self) -> store.Activity | None:
        if not self.chat_records:
            return None
        latest = self.chat_records[0]
        decision = next(((r.status, r.reason, r.at) for r in self.chat_records if isinstance(r, ChatDecision)), None)
        return store.Activity(0, latest.at, latest.text, decision)


def identity(*parts: str | None) -> str:
    keys = ["".join(unicodedata.normalize("NFKC", part or "").casefold().split()) for part in parts]
    return hashlib.sha256(json.dumps(keys, ensure_ascii=False).encode()).hexdigest()[:32]


def _concept_runs() -> dict[tuple[str, str], list[dict]]:
    by_concept: dict[tuple[str, str], list[dict]] = {}
    for meta in runs.all_meta():
        if meta.get("chat_id") and meta.get("concept_id"):
            by_concept.setdefault((meta["chat_id"], meta["concept_id"]), []).append(meta)
    for completed in by_concept.values():
        completed.sort(key=lambda meta: (date_key(meta.get("updated_at") or meta.get("started_at")), meta["id"]),
                       reverse=True)
    return by_concept


def _last_result(attempts: list[dict]) -> tuple[LastTest | None, dict]:
    for meta in attempts:
        if meta.get("status") != "done" or not meta.get("line") or not (meta.get("concept") or {}).get("name"):
            continue
        report = result.summarize(meta, runs.answers(meta["id"]), {})
        if report is None:
            continue
        origins = report["from"]
        known = report["picked"] - origins["pending"]
        own = sum(row["count"] for row in origins["own"])
        return LastTest(selection_rate=report["picked"] / report["n"], own_share=own / known if known else None,
                        virtual_sales=meta.get("virtual_sales")), meta
    return None, {}


def _chat_stamp(value: str | None) -> str | None:
    if not isinstance(value, str) or len(value) <= 10:
        return None
    try:
        return datetime.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _user_messages(rec: dict) -> Iterator[tuple[dict, str]]:
    turns = rec.get("turns") or []
    by_reply = {turn.get("message_id"): turn for turn in turns if turn.get("message_id")}
    pending = None
    ordinal = 0
    for message in rec.get("messages") or []:
        if message.get("role") == "user":
            if pending and (at := _chat_stamp(pending.get("created_at") or pending.get("at"))):
                yield pending, at
            pending = message
            ordinal += 1
        elif pending and message.get("role") == "assistant":
            turn = by_reply.get(message.get("id"), {})
            if at := _chat_stamp(turn.get("started_at") or pending.get("created_at") or pending.get("at")):
                yield pending, at
            pending = None
    if pending:
        turn = turns[-1] if turns and turns[-1].get("n") == ordinal else {}
        if at := _chat_stamp(turn.get("started_at") or pending.get("created_at") or pending.get("at")):
            yield pending, at


def _targeted_statement(text: str, subjects: list[tuple[str, re.Pattern]]) -> tuple[str, str] | None:
    statement = text.strip()
    matches = [(key, match.end()) for key, pattern in subjects if (match := pattern.match(statement))]
    if matches:
        cutoff = max(end for _, end in matches)
        matched_ids = [key for key, end in matches if end == cutoff]
        if len(matched_ids) == 1:
            return matched_ids[0], statement[cutoff:]
    elif len(subjects) == 1:
        return subjects[0][0], IMPLICIT_SUBJECT.sub("", statement)
    return None


def _chat_records(rec: dict, concepts: list[dict]) -> dict[str, list[ChatDecision | ChatAssignment]]:
    subjects = []
    for concept in concepts:
        name = concept["name"]
        subject = r"\s*".join(re.escape(char) for char in name if not char.isspace())
        pattern = re.compile(rf"^(?:이번\s+)?[\"'‘“]?{subject}[\"'’”]?(?:은|는|이|가|을|를|의)?(?:\s*[:：,]\s*|\s+|$)", re.I)
        subjects.append((concept["id"], pattern))
    records: dict[str, list[ChatDecision | ChatAssignment]] = {}
    for message, at in _user_messages(rec):
        text = message.get("text")
        message_id = message.get("id")
        if not isinstance(text, str) or not message_id or UNCERTAIN_CHAT.search(text):
            continue
        if target := _targeted_statement(text, subjects):
            concept_id, statement = target
            if evidence := store.recorded_decision(statement):
                key = f"chat-{identity(rec['id'], concept_id, str(message_id))}"
                records.setdefault(concept_id, []).append(ChatDecision(key, at, text, *evidence))
        if "담당" not in text and "맡" not in text:
            continue
        for index, sentence in enumerate(re.split(r"\n+|(?<=[.!。])\s+", text)):
            target = _targeted_statement(sentence, subjects)
            if not target:
                continue
            concept_id, statement = target
            statement = statement.rstrip(".!。").strip()
            match = next((m for pattern in OWNER_STATEMENTS if (m := pattern.fullmatch(statement))), None)
            if not match or match["name"].casefold() in UNKNOWN_OWNER:
                continue
            key = f"chat-owner-{identity(rec['id'], concept_id, str(message_id), str(index))}"
            owner = None if match["name"] in {"미지정", "미배정", "없음"} else match["name"]
            records.setdefault(concept_id, []).append(ChatAssignment(key, at, sentence.strip(), owner))
    return records


def _chat_entries() -> Iterator[Entry]:
    attempts = _concept_runs()
    for path in chats.STORE_DIR.glob("*.json"):
        rec = chats.load(path.stem)
        if not isinstance(rec, dict) or rec.get("id") != path.stem:
            continue
        note = rec.get("note")
        if not isinstance(note, dict) or not note.get("confirmed"):
            continue
        trend = next((e.get("text") for e in reversed(note.get("evidence") or [])
                      if e.get("origin") in ("internal", "web") and e.get("text")), None)
        concepts = [concept for concept in note.get("concepts") or [] if concept.get("id") and concept.get("name", "").strip()]
        records = _chat_records(rec, concepts)
        for concept in concepts:
            c = upgrade_concept(concept, note.get("ideas") or [])
            chat_id = rec["id"]
            concept_runs = attempts.get((chat_id, c["id"]), [])
            latest = concept_runs[0] if concept_runs else {}
            running = latest.get("status") in ("pending", "running")
            last_test, meta = _last_result(concept_runs)
            tested_at = meta.get("updated_at") or meta.get("started_at")
            running_at = (latest.get("updated_at") or latest.get("started_at")) if running else None
            status = "가상 테스트 중" if running else "가상 테스트 완료" if last_test else "기획 중"
            status_at = running_at or tested_at
            note_status = concept.get("status")
            note_at = _chat_stamp(concept.get("status_updated_at") or concept.get("updated_at")) or rec.get("updated_at")
            if note_status in STATUSES and date_key(note_at) >= date_key(status_at):
                status, status_at = note_status, note_at
            updated = max((rec.get("updated_at"), tested_at, status_at), key=date_key)
            description = concept.get("concept") or " ".join(filter(None, (
                c.get("_flavor"), c.get("headline"), c.get("benefit"), concept.get("summary"), *(c.get("points") or []))))
            history = tuple(sorted(reversed(records.get(c["id"], [])), key=lambda item: date_key(item.at), reverse=True))
            assignment = next((item for item in history if isinstance(item, ChatAssignment)), None)
            owner, owner_at = concept.get("owner"), _chat_stamp(concept.get("owner_updated_at"))
            if assignment and date_key(assignment.at) >= date_key(owner_at):
                owner, owner_at = assignment.owner, assignment.at
            row = IdeaRow(
                id=f"chat-{identity(chat_id, c['id'])}", name=c["name"], brand=concept.get("brand"),
                category=concept.get("category") or note.get("shelf_kind") or note.get("kind"),
                pack=c.get("pack"), price=c.get("price"), owner=owner, concept=description,
                launched_on=_source_launch_date(concept.get("launched_on")),
                status=status,
                last_work=status if status_at else None, work_date=status_at,
                checks=Checks(virtual_test=last_test is not None), last_test=last_test,
                verdict=meta.get("verdict") or concept.get("verdict"), reason=meta.get("reason") or concept.get("reason"),
                trend=concept.get("trend") or trend, started=rec.get("created_at"), updated=updated,
                source="chat", chat_id=chat_id,
            )
            yield Entry(row, description, tested_at, history, status_at, owner_at)


def _source_launch_date(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return launch_date(value.strip())
    except ValueError:
        return None


def _asset_entries() -> Iterator[Entry]:
    try:
        assets = onsite.load("assets")
    except onsite.NoData:
        return
    for a in assets:
        if not a.get("asset_id") or not a.get("name"):
            continue
        status = ASSET_STATUS.get((a.get("status") or "").replace(" ", ""), "기획 중")
        row = IdeaRow(
            id=f"assets-{a['asset_id']}", name=a["name"], brand=a.get("brand"), category=a.get("category"),
            pack=a.get("pack"), concept=a.get("concept"),
            launched_on=_source_launch_date(a.get("launched")) if status in LAUNCHED_STATUSES else None,
            status=status, checks=Checks(launched=status in LAUNCHED_STATUSES),
            reason=a.get("reason"), started=a.get("launched"), updated=a.get("ended") or a.get("launched"),
            source="assets",
        )
        yield Entry(row, row.concept or "")


def _sources() -> Iterator[Entry]:
    if onsite.available():
        for concept in CONCEPTS:
            yield Entry(IdeaRow(id=concept["id"], name=concept["name"], brand=concept.get("brand"), concept=concept.get("summary"),
                                category=concept.get("kind"), status="소비자 조사 진행",
                                checks=Checks(qual=True, quant=True), source="concept"),
                        concept.get("summary", ""))
    yield from _chat_entries()
    yield from _asset_entries()


def entries() -> list[Entry]:
    imports, edits, activity = store.read()
    rows = [*_sources(), *(Entry(row, tested_at=row.updated or row.started) for row in imports)]
    current = []
    for entry in rows:
        row_id = entry.row.id
        latest = store.latest_activity(activity.get(row_id), entry.conversation_activity())
        row = store.project(entry.row, *edits.get(row_id, ({}, None)), latest, entry.status_at, entry.owner_at)
        current.append(replace(entry, row=row, description=row.concept or ""))
    return sorted(current, key=lambda entry: (date_key(entry.row.updated), entry.row.id), reverse=True)


def listing() -> list[IdeaRow]:
    return [entry.row for entry in entries()]


def patch(row_id: str, update: IdeaPatch) -> IdeaRow | None:
    original = None if row_id.startswith(("import-", "manual-")) else next(
        (entry for entry in _sources() if entry.row.id == row_id), None,
    )
    return store.patch(row_id, original.row if original else None, update.changes(),
                       original.conversation_activity() if original else None,
                       original.status_at if original else None, original.owner_at if original else None)


def work_logs(row_id: str) -> list[dict] | None:
    entry = next((entry for entry in entries() if entry.row.id == row_id), None)
    if entry is None:
        return None
    history = [dict(id=log.id, at=log.at, text=log.text, filename=None) for log in entry.chat_records]
    return sorted([*store.logs(row_id), *history], key=lambda log: date_key(log["at"]), reverse=True)


def imported(row: IdeaRow) -> IdeaRow:
    key = identity(row.name, row.brand, row.category, row.pack, row.price, row.started)
    chat_id = None
    if chats.valid_id(row.chat_id):
        chat = chats.load(row.chat_id) or {}
        note = chat.get("note") or {}
        for concept in note.get("concepts") or []:
            if note.get("confirmed") and _product_key(concept.get("brand"), concept.get("name")) == _product_key(row.brand, row.name):
                chat_id = row.chat_id
                break
    return row.model_copy(update={"id": f"import-{key}", "source": "import", "chat_id": chat_id,
                                  "last_work": None, "work_date": None, "attachment_count": 0})


def commit(rows: list[IdeaRow]) -> list[IdeaRow]:
    return store.commit([imported(row) for row in rows]) if rows else []


def _reason_group(reason: str | None) -> str:
    if not reason:
        return "사유 기록 없음"
    for label, words in (
        ("계획된 종료", ("한정", "계획된 종료")),
        ("사업성 부족", ("사업성", "손익", "원가", "수익")),
        ("유통 조건", ("유통", "폐기율", "취급 점포", "냉장", "냉동")),
        ("수요 부족", ("수요", "회전", "판매 부진")),
    ):
        if any(word in reason for word in words):
            return label
    return "기타"


def _product_key(brand: str | None, name: str | None) -> tuple[str, str]:
    def key(text: str) -> str:
        return re.sub(r"[\W_]+", "", text)

    normalized_name = unicodedata.normalize("NFKC", name or "").casefold()
    normalized_brand = unicodedata.normalize("NFKC", brand or "").casefold()
    return key(normalized_brand), key(VOLUME.sub("", normalized_name)) or key(normalized_name)


def _launches(rows: list[IdeaRow]) -> tuple[list[dict], int]:
    products: dict[tuple[str, str], IdeaRow] = {}
    today = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    for row in rows:
        if not row.was_launched or (row.launched_on and row.launched_on > today):
            continue
        key = _product_key(row.brand, row.name)
        first = products.get(key)
        if first is None or (row.launched_on and (not first.launched_on or
                                                 (row.launched_on, row.id) < (first.launched_on, first.id))):
            products[key] = row
    dates = sorted((row.launched_on, row.id, row.name) for row in products.values() if row.launched_on)
    return [dict(name=name, row_id=row_id, launched_on=day) for day, row_id, name in dates], len(products) - len(dates)


def dashboard() -> dict:
    all_entries = entries()
    rows = [entry.row for entry in all_entries]

    def researched(row: IdeaRow) -> bool:
        return row.checks.qual or row.checks.quant or row.status in ("소비자 조사 진행", "정성 조사 중", "정량 조사 중")

    skipped = sum(row.checks.virtual_test and not researched(row) and not row.was_launched
                  and row.status in ("보류", "폐기") for row in rows)
    launches, undated = _launches(rows)
    status = Counter(row.status for row in rows)
    recent = sorted((entry for entry in all_entries if entry.row.last_test),
                    key=lambda entry: (date_key(entry.tested_at), entry.row.id), reverse=True)
    return {
        "status_counts": {key: status[key] for key in STATUSES},
        "funnel": {"ideas": len(rows), "virtual_test": sum(row.checks.virtual_test for row in rows),
                   "research": sum(researched(row) for row in rows), "launched": len(launches) + undated},
        "launches": launches,
        "undated_launches": undated,
        "skipped_research_count": skipped,
        "max_saved_won": skipped * RESEARCH_MAX_WON,
        "reason_counts": dict(Counter(_reason_group(row.reason) for row in rows if row.status in ("폐기", "단종"))),
        "brand_counts": dict(Counter(row.brand for row in rows if row.brand)),
        "category_counts": dict(Counter(row.category for row in rows if row.category)),
        "recent": [entry.row for entry in recent[:RECENT_LIMIT]],
    }
