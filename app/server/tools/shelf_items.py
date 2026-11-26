"""입체 매장의 매대에 올릴 제품 목록(지시서 13). 모델을 부르지 않는다.

자료: 공개 매대와 현장 편의점 판매 집계(shelftest.catalog).
화면용 이름, 종류, 용기, 용량, 가격, 행사, 우리 제품인지를 준다. 묶음 상품도 그대로 준다(묶음 수량을 함께).
"""

from __future__ import annotations

import os
from typing import Any

from shelftest import catalog
from shelftest.catalog import container_of as container_of

FEATURE_LABELS = {"flavor": "맛", "form": "제형", "appeal": "소구점"}


def concept_features(concept: dict[str, Any], kind: str | None = None) -> dict[str, str]:
    """보드의 제품 특징을 실행에 저장할 문자열로 옮긴다."""
    values = {
        "flavor": concept.get("flavor") or concept.get("_flavor"),
        "form": concept.get("form") or concept.get("_form") or concept.get("_carb"),
        "appeal": concept.get("appeal") or concept.get("_appeal") or concept.get("headline"),
        "kind": kind or concept.get("kind") or concept.get("_shelf_kind"),
        "sugar_caffeine": concept.get("sugar_caffeine") or concept.get("_sugar"),
    }
    return {key: " ".join(value.split()) for key, value in values.items()
            if isinstance(value, str) and value.strip() not in ("", "해당 없음", "없음", "none")}


def carbonation(form: str) -> bool | None:
    if any(word in form for word in ("무탄산", "비탄산", "탄산 없음", "탄산을 뺀")):
        return False
    if "탄산" in form or form in ("약함", "보통", "강함"):
        return True
    return None


CONCEPT_NOVELTY = ("well", "partly", "none")
CONCEPT_NOVELTY_DEFAULT = "none"  # docs/reliability.md의 측정으로 정했다(strict와 함께)


def concept_novelty() -> str:
    """신제품 컨셉이 새로움 욕구(N08)를 채우는 정도: well(잘), partly(조금), none(관계에서 뺌)."""
    value = os.getenv("AX_CONCEPT_NOVELTY", CONCEPT_NOVELTY_DEFAULT).strip() or CONCEPT_NOVELTY_DEFAULT
    if value not in CONCEPT_NOVELTY:
        raise ValueError(f"AX_CONCEPT_NOVELTY는 {', '.join(CONCEPT_NOVELTY)} 중 하나여야 합니다.")
    return value


def enrich_concept(plan: Any, concept: dict[str, Any]) -> Any:
    """실제 제품과 같은 매대 규칙을 신제품에 적용한다. 이전 실행의 매대 표시는 그대로 재현한다."""
    from build_shelves import NONE, SOME, WELL, beverage_rules

    features = concept_features(concept)
    ctx = plan.with_concept
    row = next((p for p in ctx.get("products", []) if p["상품명"] == plan.line), None)
    if row is None:
        return plan
    row["용량(ml)"] = str(concept["volume"])
    row["용기"] = concept["container"]
    for key, label in FEATURE_LABELS.items():
        if key in features:
            value = features[key]
            row[label] = f"탄산 {value}" if key == "form" and value in ("약함", "보통", "강함") else value

    form = features.get("form", "")
    fizz = carbonation(form)
    kind = features.get("kind", "")
    if fizz is False and kind in ("탄산", "탄산수"):
        kind = "비탄산 음료"
    elif fizz is True and not kind:
        kind = "탄산"

    nutrition = features.get("sugar_caffeine", "")
    sugar = next((name for name in ("무가당", "저당", "가당") if name in nutrition), "")
    if not sugar and any(word in nutrition for word in ("제로슈거", "무설탕", "당류 0g", "당 0g")):
        sugar = "제로"
    caffeine = ("없음" if any(word in nutrition for word in ("무카페인", "카페인 없음", "디카페인"))
                else "많음" if "카페인 많음" in nutrition else "조금" if "카페인 조금" in nutrition else "")
    rules = beverage_rules({
        "종류": kind, "당": sugar, "카페인": caffeine, "탄산": "있음" if fizz else "없음",
        "성분": "", "알려진 브랜드": "", "가격(원)": int(row["가격(원)"]), "행사": row["행사"],
        "용량(ml)": int(concept["volume"]),
    })
    # 맛의 표현에서 당 함량을 추정하지 않고, 명시된 맛과 소구점만 니즈에 연결한다.
    flavor, appeal = features.get("flavor", ""), features.get("appeal", "")
    if not sugar:
        for code in ("N05", "N06", "N07"):
            rules[code] = (NONE, "")
    if any(word in flavor for word in ("덜 달", "향을 줄", "연한 맛", "가벼운 맛")):
        rules["N07"] = (SOME if sugar == "가당" else NONE, "맛 설명의 강도")
    elif any(word in flavor for word in ("진한 맛", "리치", "달콤", "오리지널")):
        rules["N07"] = (WELL, "맛 설명의 강도")
    if any(word in appeal for word in ("한정", "새로운 맛", "신제품")):
        rules["N08"] = (WELL, "매대 소구점에 표시된 신제품·한정")
    # 11차만: 신제품이 새로움 욕구를 채우는 정도를 AX_CONCEPT_NOVELTY로 바꾼다(well이면 위 규칙 그대로).
    if getattr(plan, "round_number", None) == 11:
        novelty = concept_novelty()
        if novelty == "partly" and rules.get("N08", (NONE,))[0] == WELL:
            rules["N08"] = (SOME, "매대 소구점에 표시된 신제품·한정(조금)")
        elif novelty == "none":
            rules.pop("N08", None)
    if any(word in appeal for word in ("식사와", "음식과", "입가심")):
        rules["N09"] = (WELL if rules["N09"][0] == WELL else SOME, "식사와 곁들이는 소구점")
    codes = {need["번호"] for need in ctx.get("needs", [])}
    ctx["fulfills"] = {
        **ctx.get("fulfills", {}),
        plan.line: {code: degree for code, (degree, _) in rules.items() if code in codes},
    }
    return plan


def concept_prompt(plan: Any, order: list[dict[str, str]]) -> str:
    """선택 번호는 그대로 두고, 보드에 적힌 매대 표기를 같은 형식으로 전달한다."""
    if getattr(plan, "round_number", None) == 11:
        return ""  # 이 차수는 매대 JSON의 해당 상품 안에 표기를 담는다.
    for i, row in enumerate(order, 1):
        if row["상품명"] == plan.line:
            if "용기" not in row:
                return ""
            details = [f"- {label}: {row.get(label) or '표기 없음'}" for label in FEATURE_LABELS.values()]
            details.extend((f"- 가격: {int(row['가격(원)']):,}원",
                            f"- 용량: {row['용량(ml)']}mL", f"- 용기: {row['용기']}"))
            return (f"\n\n[{i}번 새 제품의 매대 표기]\n" + "\n".join(details)
                    + "\n출시 전 제품은 매대에 보이는 표시로만 판단하세요. 실제로 마셔 본 것처럼 답하지 마세요.")
    return ""


def shelf_items(shelf: str) -> list[dict[str, Any]]:
    """한 매대의 제품을 결합 목록 순서대로 반환한다."""
    return [{
        "id": p.key,
        "shelf": p.shelf,
        "name": p.name,
        "maker": p.row["제조사"],
        "kind": p.kind,
        "container": p.container,
        "volume": p.volume,
        "pack": p.pack,
        "price": p.price,
        "promo": None if p.promo.strip() in ("", catalog.NO_PROMO) else p.promo.strip(),
        "sku": p.sku,
        "ours": p.is_own,
        "is_own": p.is_own,
    } for p in catalog.current() if p.shelf == shelf]


def shelves() -> list[str]:
    return list(dict.fromkeys(p.shelf for p in catalog.public()))
