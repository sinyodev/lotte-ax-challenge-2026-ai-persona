"""결과 보고서의 "실제 자료와 대조"(evidence.compare): 가상 매출, 구매 의향과 실제 구매의 차이, 유사 제품의 판매.

모든 값은 제공 자료(data/onsite)와 테스트 결과에서 코드가 센다. 자료가 없는 구역은 싣지 않는다.
실제 판매(POS에서 읽은 값)는 가상 매출과 다른 구역에 둔다.
"""

from __future__ import annotations

import logging
from collections import Counter
from functools import lru_cache
from typing import Any

import onsite
from calibrate import sales
from agent.note import Note
from shelftest import result as shelf_result, store

SALES = "가상 매출"
GAP = "구매 의향과 실제 구매의 차이"
SIMILAR = "유사 제품의 판매"
FOLLOWUP = "소비자 조사 반영"
SIMILAR_MAX = 3
PAST_MAX = 2
_LOG = logging.getLogger(__name__)


def _run(note: Note, concept: dict[str, Any], test: dict[str, Any]) -> dict[str, Any] | None:
    """이 대화에서 이 컨셉을 올린 타깃 테스트(proposal_group과 같은 확인)."""
    from shelftest import group_flow

    run_id = note.runs.get(concept.get("id"))
    return group_flow.owned_target(note, test.get("chat_id"), run_id) if run_id else None


def _tested(note: Note, concept: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """매대에 올린 스냅숏에 종류와 보관을 더한 것."""
    out = dict(meta["concept"])
    if note.shelf_kind:
        out.setdefault("kind", note.shelf_kind)
    for key in ("season", "launch", "storage"):
        value = concept.get(f"_{key}") or concept.get(key)
        if value and not out.get(key):
            out[key] = value
    return out


def _won_range(values: list[int]) -> str:
    return f"{sales.won(values[0])}~{sales.won(values[2])} (중앙 {sales.won(values[1])})"


def sales_lines(tested: dict[str, Any], result: dict[str, Any], run_id: str) -> list[str]:
    found = sales.report(tested, {**result, "run_id": run_id})
    if not found:
        return []
    value, notes = found
    months, total, net = value["monthly"], value["season_total"], value["net"]
    units = [sales.man(v) for v in total["units"]]
    span = months[0]["month"] + (f"~{months[-1]['month']}" if len(months) > 1 else "")
    lines = [
        f"기간 {span}, 편의점 기준",
        f"가상 매출 {_won_range(total['amount'])}",
        f"가상 판매수량 {units[0]}~{units[2]} (중앙 {units[1]})",
    ]
    if net:
        lines.append(f"순증 가상 매출 {_won_range(net['amount'])}")
        if net["lost_own"]:
            worst = sorted(net["lost_own"], key=lambda r: -r["amount"])[:3]
            more = len(net["lost_own"]) - len(worst)
            lines.append("옮겨 온 자사 제품의 가상 매출 감소: " + ", ".join(
                f"{r['name']} {sales.won(r['amount'])}" for r in worst) + (f" 외 {more}개" if more else ""))
    return lines + [f"가정 · {n}" for n in notes]


def gap_lines(kind: str | None) -> list[str]:
    """과거 컨셉테스트의 구매 의향과 실제 구매경험률. 같은 종류가 있으면 그 예, 없으면 전체의 범위만."""
    rows = [r for r in onsite.load("past_tests") if r.get("intent_top2") is not None and r.get("trial_12m") is not None]
    if not rows:
        return []
    pairs = [(r, sales.kind_of({"category": r.get("category"), "name": r.get("product")})) for r in rows]
    same = [r for r, k in pairs if kind and k == kind]
    lines = [f"{r['product']}({r['year']}): 구매 의향 TOP2 {100 * r['intent_top2']:.0f}% → 출시 12개월 실제 구매경험률 "
             f"{100 * r['trial_12m']:.1f}%" + (f", 의향 대비 실제 {r['ratio']:.2f}" if r.get("ratio") is not None else "")
             for r in same]

    def span(label: str, items: list[dict[str, Any]]) -> None:
        ratios = [r["ratio"] for r in items if r.get("ratio") is not None]
        if ratios:
            lines.append(f"{label} {len(ratios)}건의 의향 대비 실제 구매 비율 {min(ratios):.2f}~{max(ratios):.2f}")

    if len(same) > 1:
        span(f"같은 종류({kind})", same)
    if not same:
        lines.append("같은 종류의 과거 컨셉테스트 없음")
    span("과거 컨셉테스트 전체", rows)
    lines.append("가상 매대의 선택률은 구매 의향과 다른 값으로, 위 비율을 가상 매출에 곱하지 않음")
    return lines


@lru_cache(maxsize=4)
def _history(stamp: tuple) -> dict[str, dict[str, Any]]:
    """제품(이름)마다 판매한 달, 채널별 수량, 달별 수량."""
    out: dict[str, dict[str, Any]] = {}
    for r in onsite.load("pos_clean"):
        if not r["name"] or not r["month"] or r.get("after_end") or not r["is_own"] or not r["units"]:
            continue
        p = out.setdefault(r["name"], {"brand": r["brand"] or "", "kind": sales.kind_of(r), "sku": r["sku"],
                                       "months": Counter(), "channels": Counter()})
        p["months"][r["month"]] += r["units"]
        p["channels"][r["channel"]] += r["units"]
    return out


def similar_lines(tested: dict[str, Any], kind: str | None) -> list[str]:
    """같은 브랜드를 먼저, 다음은 같은 종류. 판매 기간에 나왔거나 접은 제품이 앞에 온다."""
    from onsite.concepts import match

    name = str(tested.get("name") or "")
    brand = str(tested.get("brand") or (match(name) or {}).get("brand") or "")
    history = _history(sales._stamp("pos_clean"))
    every = {m for p in history.values() for m in p["months"]}

    def is_brand(value: str | None) -> bool:
        return bool(value) and (value == brand or value in name)

    ranked = sorted(((not is_brand(p["brand"]), p["kind"] != kind, len(p["months"]) == len(every), product)
                     for product, p in history.items() if is_brand(p["brand"]) or (kind and p["kind"] == kind)))
    lines = []
    for *_, product in ranked[:SIMILAR_MAX]:
        p = history[product]
        months, total = sorted(p["months"]), sum(p["months"].values())
        if total <= 0:
            continue
        peak = max(months, key=lambda m: p["months"][m])
        when = f"{months[0]}~{months[-1]}" if len(months) > 1 else months[0]
        lines.append(f"{product}: 판매 {when}({len(months)}개월), 편의점 비중 {100 * p['channels'][sales.CVS] / total:.0f}%, "
                     f"정점 {peak}(월 {sales.man(p['months'][peak])})")
    if lines:
        lines.append(f"판매 자료의 기간 {min(every)}~{max(every)}, 전 채널 실제 판매수량 기준")
    past = [a for a in onsite.load("assets") if a.get("status") in ("단종", "개발중단") and a.get("name") not in history
            and (is_brand(a.get("brand")) or (kind and sales.kind_of(a) == kind))]
    past.sort(key=lambda a: (not is_brand(a.get("brand")), a.get("launched") or ""))
    for a in past[:PAST_MAX]:
        bits = [a["status"]]
        if a.get("launched"):
            bits.insert(0, f"{a['launched'][:7]} 출시")
        if a.get("peak_sales_100m") is not None:
            bits.append(f"최고 연매출 {a['peak_sales_100m']:g}억 원")
        bits.append(f"사유 {a['reason']}" if a.get("reason") else "사유 기록 없음")
        lines.append(f"판매 자료에 없는 과거 제품 · {a['name']}: " + ", ".join(bits))
    return lines


def followup_lines(note: Note, concept: dict[str, Any]) -> list[str]:
    try:
        from calibrate import followup

        return list(followup.report_lines(note, concept) or [])
    except (ImportError, AttributeError):
        return []


def _part(title: str, make) -> list[str]:
    try:
        return make()
    except Exception as err:  # noqa: BLE001 — 한 구역이 안 되어도 보고서는 나온다
        _LOG.warning("보고서의 %s 구역을 만들지 못했어요: %s", title, type(err).__name__)
        return []


def add(note: Note, concept: dict[str, Any], test: dict[str, Any]) -> None:
    evidence = test.get("evidence")
    meta = _run(note, concept, test)
    if meta is None or not isinstance(evidence, dict):
        return
    parts = []
    if onsite.available():
        tested = _tested(note, concept, meta)
        kind = sales.concept_kind(tested, meta)

        def virtual() -> list[str]:
            res = shelf_result.summarize(meta, store.answers(meta["id"]), {})
            return sales_lines(tested, res, meta["id"]) if res else []

        parts = [(SALES, virtual), (GAP, lambda: gap_lines(kind)), (SIMILAR, lambda: similar_lines(tested, kind))]
    parts.append((FOLLOWUP, lambda: followup_lines(note, concept)))
    compare = evidence.setdefault("compare", [])
    have = {c.get("title") for c in compare}
    for title, make in parts:
        if title not in have and (lines := _part(title, make)):
            compare.append({"title": title, "lines": lines})
