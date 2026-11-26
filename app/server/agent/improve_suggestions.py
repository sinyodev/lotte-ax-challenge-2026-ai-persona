"""선택 기록과 매대 가격으로 비교할 조건과 가설을 정한다."""

from __future__ import annotations

from statistics import median
from typing import Any

from agent import improve
from tools import shelf
from tools.shelf_items import carbonation

TASTE = "맛이 끌리지 않음"
SITUATION = "지금 상황에 안 맞음"
UNCLEAR = "어떤 제품인지 모르겠음"
BARRIERS = {
    "price": improve.PRICEY, "pack": improve.PACK, "volume": improve.PACK, "container": improve.PACK,
    "promo": improve.FIRST_SEEN, "name": UNCLEAR, "appeal": UNCLEAR, "flavor": TASTE, "form": SITUATION,
}
HYPOTHESES = {
    "price": "가격이 달라지면 구매를 망설인 손님의 선택이 달라질까요?",
    "pack": "고르기 편한 포장으로 바꾸면 이 제품을 고르는 손님이 늘까요?",
    "container": "용기만 바꾸면 같은 상황에서 더 많이 고를까요?",
    "volume": "용량만 바꾸면 같은 상황에서 더 많이 고를까요?",
    "name": "제품명을 바꾸면 어떤 제품인지 알아보고 더 많이 고를까요?",
    "promo": "행사 조건을 바꾸면 처음 보는 제품에 망설인 손님도 고를까요?",
    "appeal": "매대에서 제품의 특징을 더 쉽게 읽으면 선택이 늘까요?",
    "flavor": "맛 표기를 바꾸면 맛이 끌리지 않았던 손님도 고를까요?",
    "form": "같은 음용 상황에서 제형을 바꾸면 선택이 달라질까요?",
}


def hypothesis(values: dict[str, Any]) -> str:
    return HYPOTHESES[improve.kind_of(values)]


def barrier_evidence(res: dict[str, Any], kind: str) -> list[dict[str, str]]:
    label = BARRIERS[kind]
    return [{"origin": "record",
             "text": f"원래 안 매대 테스트에서 응답한 {res['n']:,}명 중 {b['count']:,}명이 ‘{label}’을 골랐어요."}
            for b in res.get("barriers", []) if b["label"] == label and b["count"]]


def item(base: improve.Base, res: dict[str, Any], values: dict[str, Any], reason: str) -> dict[str, Any]:
    kind = improve.kind_of(values)
    evidence = barrier_evidence(res, kind) or [{
        "origin": "record",
        "text": f"원래 안 매대 테스트에서 응답한 {res['n']:,}명 중 {res['picked']:,}명이 이 제품을 골랐어요.",
    }]
    return {"values": values, **improve.describe(base, values), "reason": reason,
            "hypothesis": hypothesis(values), "evidence": evidence}


def _price_options(base: improve.Base, res: dict[str, Any], kind: str | None) -> list[dict[str, Any]]:
    if not kind:
        return []
    rivals = [p for p in shelf.products() if p.kind == kind and p.shelf == "음료" and not p.ours and p.price > 0]
    near = [p for p in rivals if 0.7 * base.volume <= p.volume <= 1.3 * base.volume]
    matched = [p for p in near if p.container == base.container]
    # 같은 용기와 가까운 용량을 우선하고, 가격 간격을 낼 수 없으면 가까운 용량까지 넓힌다.
    pool = matched if len({p.price for p in matched}) >= 2 else near
    prices = sorted({p.price for p in pool})
    if len(prices) < 2:
        return []
    gap = median(high - low for low, high in zip(prices, prices[1:]))
    step = max(100, int((gap + 50) // 100) * 100)
    ends = [base.price - step, base.price + step]
    if any(improve.check_values(base, {"price": p}, price_step=True) for p in ends):
        return []
    low, high = improve.won(prices[0]), improve.won(prices[-1])
    reason = f"다른 회사의 비슷한 용량 제품에서 본 가격 간격으로 {improve.won(step)}씩 바꿔 봐요."
    scope = "같은 용기·비슷한 용량" if pool is matched else "비슷한 용량"
    evidence = [{
        "origin": "shelf",
        "text": (f"현재 편의점 매대의 {scope}인 타사 단품 {len(pool):,}종은 {low}~{high}이에요. "
                 f"서로 다른 가격 {len(prices):,}개의 이웃 간격 중앙값을 100원 단위로 맞춰 "
                 f"{improve.won(step)} 차이로 비교해요."),
    }, *barrier_evidence(res, "price")]
    return [{**item(base, res, {"price": p}, reason), "evidence": evidence, "price_sweep": True} for p in ends]


def grounded(base: improve.Base, res: dict[str, Any], shelf_kind: str | None) -> list[dict[str, Any]]:
    suggestions = _price_options(base, res, shelf_kind)
    flavor = base.features.get("flavor")
    if flavor and barrier_evidence(res, "flavor"):
        values = {"flavor": f"향을 줄인 {flavor}"}
        if not improve.check_values(base, values):
            suggestions.append(item(base, res, values, "맛이 끌리지 않았다는 응답을 바탕으로 향의 강도를 바꿔 봐요."))
    if carbonation(base.features.get("form", "")) is True and barrier_evidence(res, "form"):
        suggestions.append(item(base, res, {"form": "무탄산"},
                                "지금 상황에 어울리지 않았다는 응답을 바탕으로 탄산을 빼고 비교해요."))
    return suggestions
