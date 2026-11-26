"""기획 노트를 파일에 담을 수 있는 값으로 바꾸고 되살린다 (지시서 11의 1절).

서버가 다시 떠서 메모리에 노트가 없으면 대화 파일의 노트로 이어 간다. 노트에는 대화의 글과 찾아본 것의 집계만 있다
(응답자 단위의 값, 사용자의 이름, 컴퓨터의 경로는 없다).
"""

from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any

from agent.note import Note, Slot
from events import event_adapter
from tools.consumer import Group, Start
from tools.occasion_display import show as show_occasion

VERSION = 1


def _slot(s: Slot) -> dict[str, Any]:
    return {"value": s.value, "by": s.by}


def _group(g: Group | None) -> dict[str, Any] | None:
    return None if g is None else {"age": g.age, "sex": g.sex, "label": g.label}


def to_dict(n: Note) -> dict[str, Any]:
    retry = None
    if n.retry:
        tasks, read = n.retry
        retry = {"tasks": [t.model_dump() for t in tasks], "read": read.model_dump()}
    return {
        "v": VERSION,
        "product": _slot(n.product), "target": _slot(n.target), "occasion": _slot(n.occasion), "need": _slot(n.need),
        "thoughts": list(n.thoughts),
        "ideas": copy.deepcopy(n.ideas),
        "concepts": copy.deepcopy(n.concepts),
        "stage": n.stage,
        "confirmed": n.confirmed,
        "evidence": copy.deepcopy(n.evidence),
        "kind": n.kind, "shelf_kind": n.shelf_kind, "shelf": n.shelf, "same_kind": n.same_kind,
        "group": _group(n.group), "occasion_code": n.occasion_code,
        "n": n.n, "idea_seq": n.idea_seq,
        "web_done": sorted(n.web_done), "said": sorted(n.said),
        "last_say": n.last_say,
        "said_before": list(n.said_before),
        "last_offer": n.last_offer.model_dump() if n.last_offer is not None else None,
        "retry": retry,
        "recs": [asdict(r) for r in n.recs],
        "runs": dict(n.runs),
        "last_run": n.last_run,
        "shelf_pending": n.shelf_pending,
        "interview": copy.deepcopy(n.interview),
        "interview_plan": copy.deepcopy(n.interview_plan),
        "improve": copy.deepcopy(n.improve),
        "interviewed": copy.deepcopy(n.interviewed),
        "followup": copy.deepcopy(n.followup),
    }


def upgrade_concept(c: dict[str, Any], ideas: list[dict[str, Any]]) -> dict[str, Any]:
    """옛 형식(v1.3까지)의 컨셉을 v1.4의 칸으로 옮긴다. 옛 칸 가운데 맞는 것만 살리고 없는 것은 비워 둔다(지시서 12)."""
    if "points" in c:
        return c
    idea = next((i for i in ideas if i.get("id") == c.get("id")), {})
    container = c.get("_container") or idea.get("_container") or ""
    volume = c.get("_volume") or idea.get("_volume") or 0
    return {
        "id": c.get("id", ""), "name": c.get("name", ""), "headline": c.get("headline", ""),
        "benefit": c.get("benefit", ""), "points": [], "price": c.get("price", ""),
        "pack": f"{volume}ml {container}".strip() if volume else c.get("volume", ""),
        "_flavor": idea.get("flavor", ""), "_container": container or "기타", "_volume": volume,
        "_price_by": c.get("_price_by", "shelf"),
    }


def from_dict(d: dict[str, Any]) -> Note:
    from agent.steps import Read, ReadTask  # 노트 → 찾기 → 노트로 도는 불러오기를 피한다

    def slot(key: str) -> Slot:
        s = d.get(key) or {}
        return Slot(s.get("value"), s.get("by"))

    g = d.get("group")
    occasion = slot("occasion")
    if occasion.value:  # 옛 대화의 노트에 남은 옛 이름은 다시 열 때 화면의 이름으로
        occasion = Slot(show_occasion(occasion.value), occasion.by)
    n = Note(product=slot("product"), target=slot("target"), occasion=occasion, need=slot("need"))
    n.thoughts = list(d.get("thoughts") or [])
    n.ideas = list(d.get("ideas") or [])
    n.concepts = [upgrade_concept(c, n.ideas) for c in d.get("concepts") or []]
    n.stage = d.get("stage") or "idea"
    n.confirmed = bool(d.get("confirmed"))
    n.evidence = list(d.get("evidence") or [])
    n.kind, n.shelf_kind = d.get("kind"), d.get("shelf_kind")
    n.shelf = d.get("shelf") or "음료"
    n.same_kind = d.get("same_kind", True)
    n.group = Group(age=g.get("age"), sex=g.get("sex"), label=g.get("label") or "") if g else None
    n.occasion_code = d.get("occasion_code")
    n.n, n.idea_seq = int(d.get("n") or 0), int(d.get("idea_seq") or 0)
    n.web_done, n.said = set(d.get("web_done") or []), set(d.get("said") or [])
    n.last_say = d.get("last_say") or ""
    n.said_before = list(d.get("said_before") or [])
    offer = d.get("last_offer")
    n.last_offer = event_adapter.validate_python(offer) if offer else None
    r = d.get("retry")
    n.retry = ([ReadTask.model_validate(t) for t in r["tasks"]], Read.model_validate(r["read"])) if r else None
    n.recs = [Start(**x) for x in d.get("recs") or []]
    n.runs = {str(k): str(v) for k, v in (d.get("runs") or {}).items()}
    n.last_run = d.get("last_run")
    n.shelf_pending = d.get("shelf_pending")
    n.interview_plan = d.get("interview_plan") if isinstance(d.get("interview_plan"), dict) else None
    n.interview = d.get("interview") if isinstance(d.get("interview"), dict) else None
    n.improve = d.get("improve") if isinstance(d.get("improve"), dict) else None
    n.followup = d.get("followup") if isinstance(d.get("followup"), dict) else None
    iv = d.get("interviewed")  # 옛 대화에는 없다
    n.interviewed = ({str(k): [str(x) for x in v] for k, v in iv.items() if isinstance(v, list)}
                     if isinstance(iv, dict) else {})
    # 옛 컨셉의 매대 제품(경쟁 제품에 자사 제품이 섞였던 때)은 지금 규칙으로 다시 고른다. 코드만 쓴다(지시서 14)
    from agent import machine

    for c in n.concepts:
        if c.get("_shelf_v") != machine.SHELF_V:
            machine.reselect_shelf(n, c)
    return n


def shelf_stale(d: dict[str, Any] | None) -> bool:
    """저장된 노트의 컨셉 가운데 매대 제품을 옛 규칙으로 고른 것이 있는가."""
    from agent import machine

    return any(c.get("_shelf_v") != machine.SHELF_V for c in (d or {}).get("concepts") or [])
