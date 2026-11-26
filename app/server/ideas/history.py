"""기획 대화에 필요한 사례 카드와 출처만 만든다."""

import re
from collections.abc import Mapping
from urllib.parse import quote

from agent.find import Found

from .board import Entry
from .documents import AUTHOR, EMAIL, LOCAL_PATH
from .similarity import CaseHit, case_status, matching_cases, normalized
from .store import UNKNOWN_REASON

TITLE = "비슷한 과거 사례"
SOURCE = "아이디어 보드"
CASE_LIMIT = 3
NO_RECORD = {normalized(value) for value in UNKNOWN_REASON} | {"원문기록없음", "기획원문기록없음"}


def _excerpt(value: str | None, owner: str | None, limit: int) -> str | None:
    if not value:
        return None
    value = AUTHOR.sub(r"\1[이름 생략]", value)
    value = EMAIL.sub("[이메일 생략]", LOCAL_PATH.sub("[경로 생략]", value))
    if owner and len(owner) >= 2:
        value = value.replace(owner, "[이름 생략]")
    text = " ".join(value.split())
    return (text[:limit - 1].rstrip() + "…" if len(text) > limit else text) or None


def _card_item(hit: CaseHit) -> dict:
    entry = hit.entry
    row = entry.row
    original = row.concept or (entry.description if row.source == "assets" else None)
    reason = _excerpt(row.reason, row.owner, 180)
    return {
        "id": row.id,
        "name": _excerpt(row.name, row.owner, 120) or "기획명 기록 없음",
        "status": case_status(row),
        "reason": reason if normalized(reason) not in NO_RECORD else None,
        "has_original": normalized(original) not in NO_RECORD,
        "concept_excerpt": _excerpt(original, row.owner, 160) if normalized(original) not in NO_RECORD else None,
        "conditions": [text for term in hit.conditions[:3] if (text := _excerpt(term, row.owner, 50))],
    }


def _evidence(item: dict, entry: Entry) -> Found:
    reason = item["reason"]
    status = {"출시": "출시", "폐기": "개발 중단", "단종": "단종"}[item["status"]]
    record = f"‘{item['name']}’에는 {status} 이력이 있어요."
    if concept := item["concept_excerpt"]:
        first_sentence = re.split(r"(?<=[.!?。])\s+", concept, maxsplit=1)[0]
        record += f" 당시 기획에는 ‘{first_sentence}’라고 적혀 있어요."
    if item["conditions"]:
        record += f" 이번 기획과 겹치는 조건은 {', '.join(item['conditions'])}예요."
    if reason:
        record += f" 남은 사유는 ‘{reason}’이에요."
    else:
        record += " 사유 기록은 없어요."
        verdict = _excerpt(entry.row.verdict, entry.row.owner, 180)
        if normalized(verdict) not in NO_RECORD:
            record += f" 당시 판단 기록은 ‘{verdict}’이에요."
    return Found(key=f"history:{item['id']}", tool="history", origin="internal", text=record,
                 source=SOURCE, said_source=SOURCE, fact=record, sentence=f"{SOURCE}에서 비슷한 사례를 찾았어요. {record}",
                 url="/ideas?idea=" + quote(item["id"], safe=""))


def lookup(query: str, message: str, *, concept: Mapping | None = None) -> tuple[list[dict], list[Found]]:
    # 트렌드 피드에서 넘긴 소식과 주소는 과거 기획의 검색어로 쓰지 않는다.
    request = message.split("\n읽은 소식:", 1)[0]
    terms = f"{query}\n{request}" if query not in request else request
    hits = matching_cases(terms, concept=concept)[:CASE_LIMIT]
    items = [_card_item(hit) for hit in hits]
    return items, [_evidence(item, hit.entry) for item, hit in zip(items, hits, strict=True)]
