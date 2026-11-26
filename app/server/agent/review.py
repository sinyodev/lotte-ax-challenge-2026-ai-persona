"""결과 보고서의 판정과 고르기(지시서 22, 32의 B). 매대 테스트를 한 컨셉의 종이에 들어가는 칸을 규칙과 글틀로 만든다.

- 모델을 부르지 않는다. 숫자는 테스트 결과(shelftest.result.summarize)와 변경안의 결과에서만 가져온다. 없는 값은 그 줄을 뺀다.
- 글틀은 agent/phrases.py의 report_*·reason_*·decide_*·key_*·next_*에 있다. 여기는 무엇을 쓸지 고르기만 한다.
- 권고의 문턱값은 agent/result_brief.py의 상수(RESEARCH_TOP, RETEST_TOP, CANNIBAL_*)다. 부록에 그 규칙을 그대로 적는다.
- 종이의 구성(약속 README의 "결과 화면과 보고서 (지시서 32)"): 첫 장(head, recommend, decisions, key, limits, opinion,
  disclaimer) → 근거(evidence) → 다음 실제 조사의 조건(next) → 부록(appendix).
- 이름 붙은 자리 evidence.voices(W7이 FGI·FGD 기록을 더한다)와 evidence.compare(W6이 실제 자료와의 대조를 더한다).
  더하는 법은 agent/proposal.py의 REPORT_EXTRAS.
- 변경안의 판정: improve.verdict의 more/less/unclear를 종이에서는 better/worse/same으로 부른다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent import improve
from agent import phrases as P
from agent import proposal_group
from agent import result_brief as RB

KIND = "result-report"  # 화면이 새 모양을 알아보는 표시
VERDICTS = {"more": "better", "less": "worse", "unclear": "same"}
MAX_REASONS = 3
MAX_DECISIONS = 3
TOP_FROM = 3
MAX_QUESTIONS = 3


@dataclass
class Variant:
    """돌린 변경안 하나: 이름("가격 변경안"), 바꾼 값("1,700원"), 결과."""
    name: str
    value: str
    result: dict[str, Any]
    pair: dict[str, Any] | None = None


@dataclass
class Inputs:
    """종이 한 장을 만드는 데 드는 것(proposal.test_section이 모은다)."""
    result: dict[str, Any]
    group: str  # 테스트한 타깃("40대 남자")
    name: str  # 제품명
    pack: str
    price: str
    shelf: str
    asked: int
    total: int
    variants: list[Variant] = field(default_factory=list)
    barriers_of: dict[str, list[str]] = field(default_factory=dict)
    board_target: str | None = None  # 컨셉 보드의 타깃
    target_basis: str | None = None
    explore_cells: list[dict[str, Any]] = field(default_factory=list)
    records: list[str] = field(default_factory=list)  # 실행 기록(걸린 시간, 호출 수)
    flavor: str | None = None
    opinion: str = ""


inflow = RB.inflow


# ---------- 변경안 비교 ----------


def _rate(res: dict[str, Any]) -> float:
    return 100 * res["picked"] / res["n"] if res.get("n") else 0.0


def _diff(base: dict[str, Any], res: dict[str, Any]) -> str:
    """기존안과의 차이. 답한 수가 같으면 명, 다르면 선택률의 %p."""
    if base["n"] == res["n"]:
        return f"{abs(res['picked'] - base['picked']):,}명"
    return f"{abs(_rate(res) - _rate(base)):.1f}%p"


def compare_rows(base: dict[str, Any], variants: list[Variant]) -> list[dict[str, Any]]:
    """막대 그림의 줄: 기존안과 돌린 변경안마다. 변경안이 없으면 빈 목록."""
    if not variants:
        return []
    rows = [{"name": improve.BASE_NAME, "change": "", "n": base["picked"], "rank": base.get("rank"),
             "rate": round(_rate(base), 1), "value": P.compare_value(base["picked"], base.get("rank")),
             "verdict": "base", "best": False, "line": None}]
    for v in variants:
        verdict = VERDICTS[improve.verdict(base, {**v.result, "paired": v.pair})]
        diff = f"{abs(v.pair['delta_pp']):.1f}%p" if v.pair else _diff(base, v.result)
        line = P.compare_line(v.name, v.value, v.result["picked"], verdict, diff)
        if v.pair:
            line = "\n".join([line, *proposal_group.comparison_lines(v.pair)])
        rows.append({"name": v.name, "change": v.value, "n": v.result["picked"], "rank": v.result.get("rank"),
                     "rate": round(_rate(v.result), 1), "value": P.compare_value(v.result["picked"], v.result.get("rank")),
                     "verdict": verdict, "best": False,
                     "line": line, **({"pair": v.pair} if v.pair else {})})
    better = [x for x in rows if x["verdict"] == "better"]
    if better:
        max(better, key=lambda x: x["rate"])["best"] = True
    return rows


def best_variant(variants: list[Variant], rows: list[dict[str, Any]]) -> Variant | None:
    for row in rows:
        if row["best"]:
            return next(v for v in variants if v.name == row["name"])
    return None


# ---------- 첫 장 ----------


def verdict(r: dict[str, Any]) -> str:
    """research(위 10% 안), retest(10~50%), hold(아래 절반이거나 0명). 문턱값은 result_brief."""
    share = RB.ahead_share(r)
    if share is None or share >= RB.RETEST_TOP:
        return "hold"
    return "research" if share < RB.RESEARCH_TOP else "retest"


def cannibal(r: dict[str, Any]) -> bool:
    f = inflow(r)
    return r["picked"] >= RB.CANNIBAL_MIN and bool(f["known"]) and f["own"] >= RB.CANNIBAL_SHARE * f["known"]


def recommend(x: Inputs, rows: list[dict[str, Any]]) -> dict[str, Any]:
    r = x.result
    v = verdict(r)
    best = best_variant(x.variants, rows)
    adopt = P.plan_label(best.name, best.value) if best and v != "hold" else None
    a = RB.ahead(r)
    reasons = [P.reason_select(x.group, r["n"], r["picked"], r.get("rank"), r["products"], a[0] if a else 0)]
    if best:
        label = P.plan_label(best.name, best.value)
        reasons.append(P.reason_better_pair(label, best.pair) if best.pair else P.reason_better(label, _diff(r, best.result)))
    elif any(row["verdict"] == "worse" for row in rows):
        reasons.append(P.reason_lower(sum(row["verdict"] == "worse" for row in rows), len(x.variants)))
    elif x.variants:
        reasons.append(P.reason_no_gain(len(x.variants)))
    if cannibal(r):
        f = inflow(r)
        reasons.append(P.reason_own(r["picked"], f["own"]))
    bars = r.get("barriers") or []
    if len(reasons) < 2 and bars:
        reasons.append(P.reason_barrier(P.barrier_name(bars[0]["label"]), bars[0]["count"]))
    return {"verdict": v, "text": P.report_verdict(v, adopt), "reasons": reasons[:MAX_REASONS]}


def decisions(x: Inputs, rows: list[dict[str, Any]], v: str) -> list[str]:
    best = best_variant(x.variants, rows)
    bars = x.result.get("barriers") or []
    top = P.barrier_name(bars[0]["label"]) if bars else None
    if v == "research":
        if best and best.name.startswith(improve.KIND_NAMES["price"]):
            spec = P.report_spec(x.pack, best.value)  # 가격 변경안이면 규격과 그 가격
        elif best:
            spec = P.plan_label(best.name, best.value)
        else:
            spec = P.report_spec(x.pack, x.price)
        out = [P.DECIDE_RESEARCH, P.decide_plan(spec)]
    elif v == "retest":
        out = [P.DECIDE_RETEST, P.decide_fix(top)]
    else:
        out = [P.DECIDE_HOLD, P.DECIDE_RETHINK]
    out.append(P.decide_target(x.board_target, x.group))
    return out[:MAX_DECISIONS]


def key_numbers(r: dict[str, Any]) -> list[dict[str, Any]]:
    """핵심 수치 네 칸: 선택한 소비자, 매대 내 선택 순위, 평소 선택하던 제품, 가장 많은 비선택 사유."""
    lo, hi = RB.people_range(r)
    f = inflow(r)
    bars = r.get("barriers") or []
    L = P.KEY_LABELS
    return [
        {"key": "picked", "label": L["picked"], "value": P.key_picked(r["n"], r["picked"]), "note": P.brief_range(lo, hi)},
        {"key": "rank", "label": L["rank"], "value": P.key_rank(r.get("rank"), r["products"]), "note": None},
        {"key": "from", "label": L["from"],
         "value": P.key_from(f["rival"], f["own"], f["none"]) if r["picked"] and f["known"] else P.KEY_NONE,
         "note": P.from_pending(f["pending"]) if f["pending"] else None},
        {"key": "barrier", "label": L["barrier"],
         "value": P.key_barrier(P.barrier_name(bars[0]["label"]), bars[0]["count"]) if bars else P.KEY_NONE, "note": None},
    ]


def limits(x: Inputs, rows: list[dict[str, Any]]) -> list[str]:
    out = [P.LIMIT_VIRTUAL, P.LIMIT_SCOPE]
    if x.variants and all(row["verdict"] in ("base", "same") for row in rows):
        out.append(P.limit_no_gain(len(x.variants)))
    return out


# ---------- 근거 ----------


def _who(group: str, who: str) -> str:
    """인용 뒤의 나이대. 패널이 나이대 하나("20대", 19~29세)면 그 이름을, 아니면 가상 소비자의 나이에서."""
    return group if group.endswith("대") else P.age_band(who)


# 가상 소비자의 말에서 걸린 점을 짐작하는 실마리(요인마다 서너 개). 다른 요인의 실마리가 든 말은 인용에서 뒤로 미룬다.
BARRIER_CLUES = {
    "지금 상황에 안 맞음": ("지금은", "상황", "때가 아"),
    "맛이 끌리지 않음": ("맛이", "밍밍", "달아서", "단맛"),
    "가격이 비쌈": ("비싸", "비쌉", "가격"),
    "처음 보는 제품이라 망설여짐": ("처음 보", "낯설", "모르는 브랜드"),
    "용량이나 용기가 안 맞음": ("용량", "양이", "크기"),
    "늘 마시는 것이 있음": ("물만", "원래 마시던", "늘 마시", "평소"),
    "어떤 제품인지 모르겠음": ("뭔지", "무슨 맛", "어떤 제품"),
}


def _has_clue(said: str, labels: list[str]) -> bool:
    return any(w in said for label in labels for w in BARRIER_CLUES.get(label, ()))


def _top_quote(top: str, others: list[str], quotes: list[dict[str, Any]],
               barriers_of: dict[str, list[str]]) -> dict[str, Any] | None:
    """요인 하나의 인용: 그 요인을 고른 가상 소비자의 말 가운데, 다른 요인의 실마리가 없는 것을 먼저,
    그다음 고른 요인의 수가 적은 것(그 요인만 고른 사람이 맨 앞). 없으면 None."""
    cands = [(i, x) for i, x in enumerate(quotes) if top in barriers_of.get(x.get("visitor", ""), [])]
    if not cands:
        return None
    cands.sort(key=lambda ix: (_has_clue(ix[1].get("said", ""), [o for o in others if o != top]),
                               len(barriers_of.get(ix[1].get("visitor", ""), [])), ix[0]))
    return cands[0][1]


def voices(r: dict[str, Any], barriers_of: dict[str, list[str]], group: str = "") -> list[dict[str, Any]]:
    """대표 발언 두세 개: 선택한 소비자 하나, 비선택 사유 1·2위마다 그 요인을 고른 소비자의 말(있을 때만).
    인용은 결과의 quotes에서만, 누구인지는 나이대만."""
    q = r.get("quotes") or {}
    out = []
    if r["picked"] and q.get("picked"):
        x = q["picked"][0]
        out.append({"factor": P.VOICE_PICKED, "quote": x["said"], "who": _who(group, x.get("who", ""))})
    bars = r.get("barriers") or []
    labels = [b["label"] for b in bars[:3]]
    used: set[str] = set()
    for b in bars[:2]:
        pool = [x for x in q.get("passed") or [] if x.get("visitor") not in used and x.get("said") not in used]
        x = _top_quote(b["label"], labels, pool, barriers_of)
        if x:
            used |= {x.get("visitor", ""), x.get("said", "")}  # 같은 사람, 같은 말을 두 번 싣지 않는다
            out.append({"factor": P.voice_passed(P.barrier_name(b["label"]), b["count"]), "quote": x["said"],
                        "who": _who(group, x.get("who", ""))})
    return out


def from_rows(r: dict[str, Any]) -> list[dict[str, Any]]:
    """평소 무엇을 고르던 사람인가: 경쟁사, 자사, 고르지 않음의 인원과 위 세 제품씩. 선택이 없으면 빈 목록."""
    f = inflow(r)
    if not r["picked"] or not f["known"]:
        return []
    src = r.get("from") or {}
    return [{"key": k, "label": P.FROM_LABELS[k], "n": f[k], "top": (src.get(k) or [])[:TOP_FROM] if k != "none" else []}
            for k in ("rival", "own", "none")]


def evidence(x: Inputs, rows: list[dict[str, Any]]) -> dict[str, Any]:
    r = x.result
    who = [P.who_tested(x.group, x.asked)]
    if x.board_target:
        who.insert(0, P.who_board(x.board_target))
    if x.target_basis:
        who.append(x.target_basis)
    f = inflow(r)
    return {
        "who": {"lines": who, "cells": x.explore_cells},
        "from": {"rows": from_rows(r), "note": P.from_pending(f["pending"]) if f["pending"] else None},
        "barriers": [{"label": P.barrier_name(b["label"]), "n": b["count"]} for b in r.get("barriers") or []],
        "variants": rows,  # 돌렸을 때만(없으면 빈 목록, 그리지 않는다)
        "voices": voices(r, x.barriers_of, x.group),  # 이름 붙은 자리: W7이 더한다
        "compare": [],  # 이름 붙은 자리: W6이 실제 자료와의 대조와 가상 매출을 더한다. 비어 있으면 그리지 않는다
    }


def next_research(x: Inputs) -> dict[str, Any]:
    r = x.result
    questions = []
    for b in r.get("barriers") or []:
        q = P.next_question(b["label"], x.name, x.flavor)
        if q and q not in questions:
            questions.append(q)
        if len(questions) >= MAX_QUESTIONS:
            break
    return {"target": P.next_target(x.group, max(r["n"], x.asked), x.board_target), "questions": questions,
            "conditions": list(P.NEXT_CONDITIONS), "unknowns": list(P.NEXT_UNKNOWNS)}


def appendix(x: Inputs) -> dict[str, Any]:
    r = x.result
    return {
        "method": [P.method_shelf(x.shelf, r["products"] - 1), P.method_people(x.group, x.asked, x.total),
                   P.METHOD_SAMPLE, P.METHOD_COMPARE],
        "records": list(x.records),
        "rules": P.rule_lines(RB.RESEARCH_TOP, RB.RETEST_TOP, RB.CANNIBAL_SHARE, RB.CANNIBAL_MIN,
                              paired=[v.name for v in x.variants if v.pair],
                              unpaired=[v.name for v in x.variants if not v.pair]),
    }


def usage_line(label: str, usage: dict[str, Any]) -> str:
    seconds = float(usage["elapsed_s"])
    time = f"{seconds:.1f}초" if seconds < 60 else f"{int(seconds // 60)}분 {int(seconds % 60)}초"
    line = f"{label} 소요 시간 {time}, 호출 {usage['calls']:,}회"
    if usage.get("est_cost_krw") is not None:
        line += f", API 추정 비용 {usage['est_cost_krw']:,.0f}원"
    elif usage.get("est_cost_usd") is not None:
        line += f", API 추정 비용 {usage['est_cost_usd']:.4f}달러"
    return line


def build(x: Inputs) -> dict[str, Any]:
    """종이의 test 칸 전부(약속 README의 "결과 화면과 보고서 (지시서 32)")."""
    rows = compare_rows(x.result, x.variants)
    rec = recommend(x, rows)
    return {
        "kind": KIND,
        "head": {"title": P.REPORT_TITLE, "product": x.name, "spec": P.report_spec(x.pack, x.price)},
        "recommend": rec,
        "decisions": decisions(x, rows, rec["verdict"]),
        "key": key_numbers(x.result),
        "limits": limits(x, rows),
        "opinion": x.opinion,
        "disclaimer": P.REPORT_DISCLAIMER,
        "evidence": evidence(x, rows),
        "next": next_research(x),
        "appendix": appendix(x),
    }
