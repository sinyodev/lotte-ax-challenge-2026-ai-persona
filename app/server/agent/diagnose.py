"""컨셉 보드 분석(화면의 1부 세 번째 단계)과 기획자가 고른 안의 매대 테스트."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import replace
from math import isfinite
from statistics import quantiles
from typing import TYPE_CHECKING, Literal

import onsite
from agent.note import Note
from events import ActionItem, Actions, Card, Say, Stage
from onsite.concepts import CONCEPTS
from shelftest import catalog
from trend.verdicts import verdicts

if TYPE_CHECKING:
    from shelftest.runner import Spec

_CONCEPT = next(concept for concept in CONCEPTS if concept["id"] == "milkis-hwachae")
_MISSING = "자료 없음"
REPLY_TO = "w7-diagnose"


def _won(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".") + "원"


def _key(value: str | None) -> str:
    return re.sub(r"[^\w]|_", "", (value or "").casefold())


def _container(value: str | None) -> str:
    value = _key(value)
    for label, words in (("페트", ("페트", "pet")), ("캔", ("캔", "can")),
                         ("파우치", ("파우치", "pouch")), ("병", ("병", "bottle"))):
        if any(word in value for word in words):
            return label
    return value


def _official(concept: dict) -> dict:
    task = concept.get("_task_concept")  # 지시서 33 후속: 과제 컨셉으로 채운 아이디어에서 나온 컨셉
    return next((item for item in CONCEPTS if item["id"] == task), None) or next((item for item in CONCEPTS if item["id"] == concept["id"]
                 or _key(item["name"]) == _key(concept["name"])), {})


def _price_amount(value: str | int | None) -> int:
    if isinstance(value, int):
        return value
    money = re.search(r"([\d,]+)\s*원", value or "")
    return int(money[1].replace(",", "")) if money else 0


def _section(key: str, summary: str, *, status: str = "ok", source: str | None = None,
             details: list[str] | None = None, **data) -> dict:
    return {"id": key, "summary": summary, "status": status, "source": source,
            "details": details or [], **data}


# 화면과 대화에 내는 쉬운 말. 판정의 이름(피크아웃 등)은 계산과 기록에만 쓴다.
STAGE_PLAIN = {"피크아웃": "정점이 지났어요", "계절성 수요": "여름에만 찾아요", "상승기": "찾는 사람이 늘고 있어요",
               "광고성 바이럴": "광고·협찬으로 늘어난 언급이 많아요", "안정기": "찾는 사람이 꾸준해요"}


def _plain_stages(stages: list[str]) -> str:
    return " ".join(f"{STAGE_PLAIN.get(stage, stage)}." for stage in stages)


def _seasonal_peaks(series: list[dict]) -> list[dict]:
    seasons = ("겨울", "봄", "여름", "가을")
    readings: dict[tuple[int, int], dict[int, float]] = defaultdict(dict)
    for point in series:
        year, month = map(int, point["month"].split("-"))
        value = point["search_index"]
        if value is not None and isfinite(value) and 0 <= value <= 100:
            readings[(year - (month < 3), (month % 12) // 3)][month] = value
    return [{"year": year, "season": seasons[season], "peak": max(values.values()), "slot": year * 4 + season}
            for (year, season), values in sorted(readings.items()) if len(values) == 3]


def _trend_section(offer: dict, concept: dict) -> dict:
    findings = verdicts()
    keywords = offer.get("keywords") or concept.get("keywords") or []
    fallback = [_key(concept.get("_flavor") or concept.get("flavor")), _key(concept["name"])]
    matches = [item for item in findings
               if (_key(item["keyword"]) in {_key(term) for term in keywords} if keywords else
                   any(_key(item["keyword"]) in term for term in fallback))]
    primary = next((item for term in keywords for item in matches if _key(item["keyword"]) == _key(term)),
                   next(iter(matches), None))
    if not primary or not any(p["search_index"] is not None or p["sns_mentions"] is not None for p in primary["series"]):
        return _section("trend", "이 컨셉에 해당하는 검색·SNS 자료가 없어요.", status="missing")

    keyword = primary["keyword"]
    points = _seasonal_peaks(primary["series"])
    start, end = primary["series"][0]["month"], primary["series"][-1]["month"]
    stages = primary["stage"]
    details = [f"월별 검색·SNS 관측 기간은 {start}~{end}예요.", *primary["reasons"]]
    summary = f"{keyword} 검색을 보면 {_plain_stages(stages)}" if stages else (
        f"{keyword} 검색에서 눈에 띄는 흐름은 없어요.")
    band = "여름" if offer.get("season") or any(word in keyword for word in ("화채", "얼려", "슬러시")) else None
    if band:
        peaks = [point for point in points if point["season"] == band]
        if len(peaks) >= 2 and peaks[-2]["year"] + 1 == peaks[-1]["year"]:
            before, after = peaks[-2:]
            summary = (f"{keyword}의 여름(6~8월) 최고 검색 지수는 {before['year']}년 {before['peak']:g}, "
                       f"{after['year']}년 {after['peak']:g}예요.")
            if "피크아웃" in stages:
                summary += f" {STAGE_PLAIN['피크아웃']}."
    for item in matches:
        if item is not primary and item["stage"]:
            details.append(f"{item['keyword']} 검색도 보면 {_plain_stages(item['stage'])}")
    other_terms = [item for item in findings if item not in matches]
    alternatives = [item["keyword"] for item in other_terms
                    if "상승기" in item["stage"] and "광고성 바이럴" not in item["stage"]]
    alternative = (f"다른 음료 검색어 중 {', '.join(alternatives)}의 검색이 늘었어요. 별도 컨셉으로 살펴볼 수 있어요."
                   if alternatives else "광고·협찬을 빼고 검색이 늘고 있는 다른 음료 검색어는 제공 자료에 없어요.")
    details.append(alternative)
    ads = [item["keyword"] for item in other_terms if {"상승기", "광고성 바이럴"} <= set(item["stage"])]
    if ads:
        details.append(f"{', '.join(ads)}는 찾는 사람이 늘었지만, 광고·협찬으로 늘어난 언급이 많아요.")
    if band:
        details.append("제공 자료에서 대신 검토할 다른 과일 맛의 상승 근거는 확인되지 않았어요."
                       if "화채" in keyword else "검색 증가에는 광고·협찬의 영향이 섞일 수 있어요.")
    # 달별 검색 지수: 분석 화면의 선 그래프가 그린다(트렌드 조사 카드가 쓰는 것과 같은 값)
    series = [{"month": point["month"], "search_index": point["search_index"]} for point in primary["series"]]
    return _section("trend", summary, status="flag" if {"피크아웃", "광고성 바이럴"} & set(stages) else "ok",
                    source="제공 검색·SNS 자료", details=details, stages=stages, peaks=points, highlight=band,
                    keyword=keyword, series=series)


def _asset_history(query: dict) -> list[dict]:
    try:
        assets = onsite.load("assets")
    except onsite.NoData:
        return []
    brand, kind = _key(query.get("brand")), _key(query.get("kind"))
    flavor = _key(query.get("flavor") or query.get("_flavor")).removesuffix("맛")
    if "수박화채" in flavor or "수박화채" in query.get("keywords", []):
        flavor = "수박"
    ranked = []
    for asset in assets:
        name = asset.get("name") or ""
        text = _key(" ".join((name, asset.get("concept") or "")))
        same_brand = brand and brand == _key(asset.get("brand"))
        same_kind = kind and kind in _key(asset.get("category"))
        similar_form = query.get("storage") == "냉동" and any(word in text for word in ("얼려", "냉동"))
        exact_flavor = flavor and flavor in text
        score = 3 * bool(same_brand) + 2 * bool(same_kind) + 4 * bool(exact_flavor) + 5 * similar_form
        if name and score >= 4:
            status = asset.get("status")
            launched = asset.get("launched") if status in {"운영", "단종"} else None
            ranked.append((score, {"name": name, "source": "assets", "status": status, "score": score,
                                   "launched_on": launched, "started": asset.get("launched"),
                                   "reason": asset.get("reason"), "concept": asset.get("concept")}))
    return [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)]


def _reason_labels(reason: str | None) -> list[str] | None:
    """사유의 원문 대신 묶음 이름. 사유가 비었으면 None, 묶음에 없으면 빈 목록."""
    if not reason or not reason.strip():
        return None
    groups = (
        ("계획된 종료", ("한정", "계획")),
        ("사업성 부족", ("사업성", "손익", "원가", "수익")),
        ("유통 제약", ("유통", "취급점", "취급 점포", "냉장", "냉동")),
        ("높은 폐기율", ("폐기율",)),
        ("판매 부진", ("수요", "회전", "판매 부진")),
    )
    return [label for label, terms in groups if any(term in reason for term in terms)]


def _reason_summary(reason: str | None) -> str:
    matched = _reason_labels(reason)
    if matched is None:
        return "사유는 기록에 없어요."
    return f"사유는 {', '.join(matched)}예요." if matched else "상세 사유는 아이디어 보드에 있어요."


def _history_line(row: dict, status: str | None, launched: str, started: str) -> str:
    """'밀키스 수박 500mL(2021년, 시즌 한정)이 단종된 적이 있어요. 사유는 기록에 없어요.'"""
    from tools.consumer import josa

    data = f"{row.get('name') or ''} {row.get('concept') or ''}"
    seasonal = bool(re.search(r"(?:여름|시즌|계절)\s*한정", data))
    name = re.sub(r"\s*\((?:여름|시즌|계절)\s*한정\)", "", row["name"]).strip()
    year = launched[:4] if launched[:4].isdigit() else started[:4] if started[:4].isdigit() else ""
    notes = [f"{year}년" if year else "", "시즌 한정" if seasonal else ""]
    note = ", ".join(part for part in notes if part)
    head = f"{name}({note})" if note else name
    if status == "단종":
        line = f"{head}{josa(name, '이/가')} 단종된 적이 있어요."
    elif status == "개발 중단":
        line = f"{head}{josa(name, '은/는')} 개발을 중단했어요."
    elif status == "출시":
        line = f"{head}{josa(name, '이/가')} 출시된 적이 있어요."
    else:
        line = f"{head}{josa(name, '은/는')} {status or '진행 단계가 기록에 없는'} 단계예요."
    if status in {"단종", "개발 중단"}:
        line += f" {_reason_summary(row.get('reason'))}"
    return line


def _history_section(offer: dict, concept: dict, kind: str | None, *, asset_only: bool = False) -> dict:
    query = {**offer, **concept, "kind": kind, "category": kind}
    try:
        from ideas import similar
        found = similar(query)
    except (ImportError, FileNotFoundError):
        found = []
    rows = [row for row in found if row.get("source") == "assets"
            or not asset_only and row.get("status") in {"출시", "단종", "폐기"}
            and _key(row["name"]) != _key(concept["name"])]
    if not rows:
        rows = _asset_history(query)
    if not rows:
        return _section("history", "비슷한 제품의 검토·출시 이력이 없어요.", status="missing")

    rows = sorted(rows, key=lambda row: (row.get("score", 0), bool(row.get("launched_on"))), reverse=True)
    details, table = [], []
    for row in rows[:3]:
        status = {"운영": "출시", "폐기": "개발 중단", "개발중단": "개발 중단"}.get(row.get("status"), row.get("status"))
        launched = row.get("launched_on") or ""
        started = row.get("started") or ""
        details.append(_history_line(row, status, launched, started))
        # 분석 화면의 표: 제품, 연도, 결과, 사유(원문 대신 묶음 이름)
        year = launched[:4] if launched[:4].isdigit() else started[:4] if started[:4].isdigit() else None
        name = re.sub(r"\s*\((?:여름|시즌|계절)\s*한정\)", "", row["name"]).strip()
        ended = status in {"단종", "개발 중단"}
        table.append({"name": name, "year": int(year) if year else None, "status": status,
                      "reasons": _reason_labels(row.get("reason")) if ended else None})
    return _section("history", details[0], source="아이디어 보드", details=details[1:], link="/ideas", rows=table)


def _range(products: list[catalog.Product]) -> dict | None:
    if not products:
        return None
    prices = [p.price for p in products]
    return {"count": len(prices), "low": min(prices), "high": max(prices)}


def _rivals(kind: str | None, volume: int, container: str
            ) -> tuple[dict | None, dict | None, bool, list[catalog.Product]]:
    if not kind:
        return None, None, False, []
    try:
        rivals = [p for p in catalog.current() if p.shelf == catalog.BEVERAGES and p.kind == kind
                  and p.pack == 1 and not p.is_own and p.price > 0]
    except FileNotFoundError:
        return None, None, False, []
    same = [p for p in rivals if volume and p.volume == volume and container != ""
            and (_container(p.row.get("모양")) or catalog._package(p.name)) == container]
    return _range(rivals), _range(same), any(p.added for p in rivals), same


def _survey_wtp(offer: dict, volume: int, container: str) -> tuple[dict | None, str | None]:
    if not offer:
        return None, "같은 품목으로 소비자가 내겠다는 값을 물은 자료가 없어요."
    variants = offer["variants"]
    # 과제 정량조사는 밀키스 화채의 PET 한 규격만 물었다. 나머지 품목은 제시 규격이 하나다.
    surveyed = variants[0] if len(variants) == 1 else next(
        (variant for variant in variants if _container(variant["pack"]) == "페트"), None)
    if surveyed is None:
        return None, "정량조사에서 제시한 규격을 확인할 수 없어요."
    spec = f"{surveyed['volume_ml']}mL {surveyed['pack']}"
    if volume != surveyed["volume_ml"] or container != _container(surveyed["pack"]):
        return None, f"2026년 10월 정량조사는 {spec}로 물었어요. 현재 규격으로 소비자가 내겠다는 값은 자료가 없어요."
    try:
        stats = onsite.load_json("survey_summary").get("concepts", {}).get(offer["name"], {})
    except onsite.NoData:
        stats = {}
    try:
        ratings = onsite.load("survey_ratings")
    except onsite.NoData:
        ratings = None
    special_price = False
    if ratings is None:
        wtp = stats.get("wtp", {})
    else:
        # 제시가격은 조사 품목·규격을 확인하는 데만 쓴다. 현재 권장가가 바뀌어도 규격은 같다.
        valid = [row for row in ratings if row.get("concept") == offer["name"]
                 and row.get("shown_price") == surveyed["price"] and isinstance(row.get("wtp"), (int, float))
                 and isfinite(row["wtp"]) and row["wtp"] >= 0]
        special_price = special_price or any("출시기념" in _key(row.get("price_format")) for row in valid)
        amounts = list({row["rid"]: row["wtp"] for row in valid if row.get("rid")}.values())
        lower, middle, upper = (quantiles(amounts, n=4, method="inclusive") if len(amounts) > 1 else amounts * 3
                                if amounts else (None, None, None))
        wtp = {"n": len(amounts), "p25": lower, "median": middle, "p75": upper}
        if len(amounts) > 1:
            # 상자 그림의 수염(상자에서 상자 길이의 1.5배 안에 든 가장 작은 값과 큰 값)과,
            # 100원마다 그 값 이상을 내겠다고 답한 사람 수. 응답자 단위 값은 내보내지 않는다.
            reach = (upper - lower) * 1.5
            inside = [a for a in amounts if lower - reach <= a <= upper + reach]
            wtp["low"], wtp["high"] = min(inside), max(inside)
            # 답한 값 전체를 덮되, 동떨어진 값 때문에 칸이 너무 많아지면 수염까지만 센다(그 밖은 양 끝 칸에 든다)
            first, last = int(min(amounts) // 100 * 100), int(-(-max(amounts) // 100) * 100)
            if (last - first) // 100 > 40:
                first, last = int(wtp["low"] // 100 * 100), int(-(-wtp["high"] // 100) * 100)
            wtp["accept"] = [[price, sum(a >= price for a in amounts)] for price in range(first, last + 100, 100)]
    if not wtp.get("n") or any(wtp.get(key) is None for key in ("p25", "median", "p75")):
        return None, "같은 품목·규격의 유효한 최대 얼마까지 내겠는지에 대한 응답이 없어요."
    note = None
    if special_price:
        note = "정량조사에서는 정가와 출시기념가를 함께 제시했어요."
    elif stats.get("leading"):
        note = "정량조사의 질문 문구나 가격 제시 조건에 차이가 있어요."
    return {**wtp, "spec": spec}, note


def _price_section(offer: dict, concept: dict, kind: str | None, volume: int, container: str) -> tuple[dict, list[dict]]:
    from agent import improve

    current = _price_amount(concept.get("price"))
    rivals, same, includes_pos, same_products = _rivals(kind, volume, container)
    flavor = _key(concept.get("flavor") or concept.get("_flavor"))
    survey_matches = (offer and _key(concept["name"]) == _key(offer["name"])
                      and (offer["id"] != "milkis-hwachae" or not flavor or "수박" in flavor))
    wtp, survey_note = _survey_wtp(offer if survey_matches else {}, volume, container)
    spec = concept.get("pack") or (f"{volume}mL {concept.get('_container')}" if volume and container else "")
    official = any(v["volume_ml"] == volume and _container(v["pack"]) == container and v["price"] == current
                   for v in offer.get("variants", []))
    label = "권장 소비자가" if official else "컨셉 보드 가격"
    topic = f"{label}는" if official else f"{label}은"
    summary = f"{topic} {_won(current)}이에요." if current else "컨셉 보드 가격이 정해지지 않았어요."
    details = []
    if spec:
        details.append(f"비교할 규격은 {spec} 1개예요.")
    if survey_note:
        details.append(survey_note)
    if not rivals:
        details.append("비교할 같은 종류의 타사 1개입 음료 가격 자료가 없어요.")
    else:
        details.append(f"편의점 매대의 같은 종류({kind}) 타사 1개입 {rivals['count']}종은 "
                       f"{_won(rivals['low'])}~{_won(rivals['high'])}이에요.")
        if includes_pos:
            try:
                months = [row["month"] for row in onsite.load("pos_clean")
                          if row.get("month") and row.get("channel") == "편의점" and not row.get("after_end")]
            except onsite.NoData:
                months = []
            period = f"({min(months)}~{max(months)}) " if months else " "
            details.append(f"공개 매대 표시가와 편의점 POS{period}기간 평균 판매단가를 원/개로 비교해요.")
        else:
            details.append("공개 편의점 매대 표시가를 원/개로 비교해요.")
        if same:
            details.append(f"같은 용기·용량 {same['count']}종은 {_won(same['low'])}~{_won(same['high'])}이에요.")
        else:
            details.append("같은 용기·용량으로 확인된 타사 1개입 음료는 없어요.")

    fixes = []
    status = "ok" if (rivals or wtp) and current else "missing"
    if wtp:
        mid = wtp["median"]
        evidence = (f"2026년 10월 정량조사에서 {wtp['spec']}에 최대 얼마까지 내겠는지 답한 "
                    f"{wtp['n']:,}명의 가운데 값은 {_won(mid)}, 가운데 절반은 "
                    f"{_won(wtp['p25'])}~{_won(wtp['p75'])}이에요.")
        details.insert(0, evidence)
        if current:
            if current == mid:
                summary = f"{topic} {_won(current)}으로, 소비자가 내겠다는 값(조사의 가운데 값)과 같아요."
            else:
                relation = "높아요" if current > mid else "낮아요"
                summary = (f"{topic} {_won(current)}으로, 소비자가 내겠다는 값(조사의 가운데 값)보다 "
                           f"{_won(abs(current - mid))} {relation}.")
            limits = same or {}
            lower = current > mid
            higher = current < limits.get("low", 0) and current < mid and not survey_note
            if lower:
                status = "flag"
            target = min(mid, same["low"]) if higher else mid
            candidate = int(target // 100 * 100)
            base = improve.Base(concept["name"], container, volume, current)
            if ((lower and candidate < current) or (higher and candidate > current)) and not improve.check_values(
                    base, {"price": candidate}):
                reason = f"소비자가 내겠다는 값(조사의 가운데 값)을 참고해 {_won(candidate)}에 테스트해요."
                proof = [{"origin": "internal", "text": evidence}]
                if higher:
                    proof.append({"origin": "shelf", "text": f"같은 용기·용량 {same['count']}종의 최저가는 {_won(same['low'])}이에요."})
                fixes.append({"id": f"price-{candidate}", "values": {"price": candidate}, "reason": reason,
                              "hypothesis": ("가격을 낮추면 매대에서 고르는 사람이 늘 수 있어요." if lower else
                                             "같은 규격의 경쟁 가격에 가까워져도 선택률이 유지될 수 있어요."),
                              "evidence": proof})
    source = ("정량조사 · 편의점 매대" if wtp and rivals else "정량조사" if wtp else
              "편의점 매대" if rivals else None)
    return _section("price", summary, status=status, source=source, details=details,
                    current=current or None, label=label, kind=kind, spec=spec, rivals=rivals, same=same, wtp=wtp,
                    # 분석 화면의 가격 그림: 같은 용기·용량 제품마다 점 하나
                    points=[{"name": p.name, "price": p.price} for p in sorted(same_products, key=lambda p: p.price)]
                    ), fixes


def _distribution_section(storage: str | None) -> dict:
    if storage not in {"상온", "냉장", "냉동"}:
        return _section("distribution", "컨셉 보드에 보관 조건이 없어요.", status="missing")
    if storage == "상온":
        return _section("distribution", "상온 보관 제품이라 냉장·냉동 진열 설비가 필요 없어요.", status="ok",
                        details=["제공된 유통 인프라에는 상온 제품의 진열 가능 점포율이 없어요."], storage=storage)
    try:
        store = next((row for row in onsite.load("infra") if row.get("channel") == "편의점"), {})
    except onsite.NoData:
        store = {}
    key = "frozen_rate" if storage == "냉동" else "chilled_rate"
    metric = "냉동 음료 진열 가능 점포율" if storage == "냉동" else "냉장 쇼케이스 보유율"
    rate, total = store.get(key), store.get("stores")
    if rate is None or not 0 <= rate <= 1 or not total or total < 0:
        return _section("distribution", f"{storage} 보관 제품이에요. 편의점의 {metric} 자료가 없어요.", status="missing",
                        storage=storage)
    return _section("distribution", f"편의점 {total:,}곳 기준 {metric}은 {rate:.1%}예요.".replace(".0%", "%"),
                    status="flag" if rate < 0.5 else "ok", source="제공 유통 인프라",
                    details=(["쇼케이스 보유율을 기준으로 봤어요. 실제 취급 점포율은 확인되지 않았어요."] if storage == "냉장"
                             else ["제공 자료의 편의점 전체를 분모로 집계했어요."]),
                    stores=total, rate=rate, storage=storage)


def _payload(n: Note, concept: dict, *, asset_only: bool = False) -> dict:
    offer = _official(concept)
    kind = concept.get("kind") or offer.get("kind") or n.shelf_kind
    variants = concept.get("variants") or offer.get("variants") or []
    if variants and not (concept.get("_volume") or concept.get("volume")):
        spec = concept.get("pack") or ""
        size = re.search(r"(\d+)\s*ml", spec, re.I)
        representative = next((v for v in variants if size and v.get("volume_ml") == int(size[1])
                               and _container(v.get("container") or v.get("pack")) == _container(spec)), None)
        if representative or not spec:
            v = representative or variants[0]
            pack = v.get("container") or v.get("pack")
            concept = {**concept, "_volume": v["volume_ml"], "_container": concept.get("_container") or pack,
                       "pack": spec or f"{v['volume_ml']}mL {pack}", "price": concept.get("price") or v.get("price")}
    volume = int(concept.get("_volume") or concept.get("volume") or 0)
    container = _container(concept.get("_container") or concept.get("container"))
    price, fixes = _price_section(offer, concept, kind, volume, container)
    storage = concept.get("_storage") or concept.get("storage") or offer.get("storage")
    sections = [_trend_section(offer, concept), price, _history_section(offer, concept, kind, asset_only=asset_only),
                _distribution_section(storage)]
    status_order = {"flag": 0, "ok": 1, "missing": 2}
    return {"concept_id": concept["id"], "concept_name": concept["name"],
            "sections": sorted(sections, key=lambda item: status_order[item["status"]]), "fixes": fixes}


def _signature(concept: dict) -> list:
    values = [concept.get(key) for key in ("name", "price", "pack", "kind", "_container", "_volume",
                                          "container", "volume", "_flavor", "flavor", "_storage", "storage")]
    return [*values, concept["variants"]] if concept.get("variants") else values


def board(n: Note, concept: dict) -> Card:
    payload = _payload(n, concept)
    signature = _signature(concept)
    state = concept.get("_diagnosis") or {}
    if state.get("signature") != signature:
        state = {"signature": signature}
    state["offered"] = payload["fixes"]
    concept["_diagnosis"] = state
    return Card(id=f"diagnosis-{concept['id']}", kind="diagnosis", stage="concept",
                title="컨셉 보드 분석", status="ready", payload=payload)


PICK = REPLY_TO + "|"  # 대화의 버튼(확정 차례)의 id 앞머리: "w7-diagnose|컨셉 id|고른 것|고친 안 id"


def pick_ids(ids: list[str]) -> list[str] | None:
    """대화의 버튼이 보낸 id를 분석 카드의 버튼이 보내던 ids([컨셉 id, 고른 것, 고친 안 id])로 푼다. 아니면 None."""
    if len(ids) == 1 and ids[0].startswith(PICK):
        return ids[0].split("|")[1:]
    return None


def _half_up(x: float) -> int:
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def _year_peaks(series: list[dict]) -> list[float]:
    """해마다의 정점(값이 6달 이상 있는 해만). 화면의 yearPeaks와 같다."""
    best: dict[str, list[float]] = {}
    for m in series:
        v = m.get("search_index")
        if v is None:
            continue
        cur = best.get(m["month"][:4])
        best[m["month"][:4]] = [v, 1] if cur is None else [max(cur[0], v), cur[1] + 1]
    return [v for _, (v, k) in sorted(best.items()) if v > 0 and k >= 6]


def _trend_pair(trend: dict) -> tuple[float, float] | None:
    """작년과 올해의 정점(강조 계절끼리, 없으면 해마다의 정점끼리). 화면의 trendPair와 같다."""
    seasonal = [p for p in trend.get("peaks") or [] if p["season"] == trend.get("highlight")]
    now = seasonal[-1] if seasonal else None
    before = next((p for p in seasonal if now and p["year"] == now["year"] - 1), None)
    if now and before and before["peak"] > 0:
        return before["peak"], now["peak"]
    peaks = _year_peaks(trend.get("series") or [])
    return (peaks[-2], peaks[-1]) if len(peaks) >= 2 and peaks[-2] > 0 else None


def confirm_turn(payload: dict) -> tuple[str, list[tuple[str, str]]]:
    """확정 차례(보드 하나)의 칠성이의 말과 대화의 버튼. 살펴볼 점을 한 문장씩 정리하고 끝에 테스트를 제안한다.
    숫자는 payload에서 코드가 넣는다(견본 /proto/analysis의 sayOf와 같은 조건)."""
    from agent import phrases as P

    sections = {s["id"]: s for s in payload["sections"]}
    facts = []
    trend = sections.get("trend")
    pair = _trend_pair(trend) if trend and trend["status"] == "flag" else None
    if pair and _half_up((pair[1] / pair[0] - 1) * 100) < 0:
        facts.append(P.analysis_cooling(trend.get("keyword") or "", _half_up(pair[1] / pair[0] * 100)))
    price = sections.get("price") or {}
    current, wtp, same = price.get("current"), price.get("wtp"), price.get("same")
    if price.get("status") == "flag" and current is not None and wtp and current > wtp["median"]:
        facts.append(P.analysis_price_over(current, wtp["median"], current - wtp["median"]))
        if same and current < same["low"]:
            facts.append(P.analysis_cheaper(same["count"], same["low"]))
    fix = next((f for f in payload["fixes"] if isinstance(f["values"].get("price"), (int, float))), None)
    flags = sum(s["status"] == "flag" for s in payload["sections"])
    cid = payload["concept_id"]
    if current is not None and fix is not None:
        to = fix["values"]["price"]
        ask = P.analysis_propose(current, to)
        buttons = [(f"{PICK}{cid}|both|{fix['id']}", P.btn_test_both(current, to)),
                   (f"{PICK}{cid}|original", P.btn_test_only(current)),
                   (f"{PICK}{cid}|fix|{fix['id']}", P.btn_test_only(to))]
    else:
        ask = P.ANALYSIS_PROPOSE_ONE
        buttons = [(f"{PICK}{cid}|original", P.BTN_TEST_AS_IS), ("download", P.BTN_DOWNLOAD)]
    return "\n\n".join(x for x in (P.analysis_lead(flags), " ".join(facts), ask) if x), buttons


def prototype_diagnosis(pack: str | None = None) -> dict:
    """시안의 진단은 대화를 만들거나 테스트를 시작하지 않고 집계한다."""
    variants = _CONCEPT["variants"]
    variant = next((v for v in variants if f"{v['volume_ml']}mL {v['pack']}" == pack), None) if pack else variants[0]
    if variant is None:
        raise ValueError("과제 컨셉의 규격을 확인해 주세요.")
    concept = {**_CONCEPT, "_volume": variant["volume_ml"], "_container": variant["pack"],
               "pack": f"{variant['volume_ml']}mL {variant['pack']}", "price": variant["price"]}
    return _payload(Note(), concept, asset_only=True)


def choose(n: Note, conv_id: str, ids: list[str]) -> list:
    from agent import explore
    from agent.machine import _end

    retry = "컨셉 보드 분석에서 테스트할 안을 골라 주세요."
    if len(ids) not in (2, 3) or ids[1] not in {"original", "both", "fix"}:
        return _end(n, retry, n.last_offer)
    concept = n.concept(ids[0])
    if not concept:
        return _end(n, retry, n.last_offer)
    state = concept.get("_diagnosis") or {}
    if state.get("signature") != _signature(concept):
        return [board(n, concept), *_end(n, "지금 컨셉 보드의 조건으로 다시 분석했어요.", None)]
    mode = ids[1]
    offered = state["offered"]
    fix = (next((item for item in offered if item["id"] == ids[2]), None) if len(ids) == 3 else
           offered[0] if len(offered) == 1 else None)
    if (mode == "original" and len(ids) != 2) or (mode != "original" and not fix):
        return _end(n, retry, n.last_offer)
    if (concept.get("_shelf_flow") or {}).get("step") in {"exploring", "choose", "confirm"}:
        return _end(n, "진행 중인 매대 테스트의 선택을 마쳐 주세요.", n.last_offer)
    state["choice"] = mode
    state["approved"] = fix if mode != "original" else None
    return explore.entry(n, concept)


def selected_spec(concept: dict, spec: Spec) -> Spec:
    """고친 안만 고른 경우 그 값으로 탐색·타깃을 시작한다."""
    state = concept.get("_diagnosis") or {}
    fix = state.get("approved")
    if state.get("choice") != "fix" or state.get("signature") != _signature(concept) or not fix:
        return spec
    return replace(spec, price=fix["values"]["price"])


def after_target(n: Note, conv_id: str, concept: dict, base_run_id: str) -> list:
    """타깃 실행으로 정해진 방문을 그대로 받아 승인한 안을 시작한다."""
    from agent import improve, machine
    from shelftest import store

    state = concept.get("_diagnosis") or {}
    fix = state.get("approved")
    mode = state.get("choice")
    if not fix or mode != "both" or state.get("signature") != _signature(concept):
        return []
    base = store.load_meta(base_run_id)
    if (not base or base.get("chat_id") != conv_id or base.get("concept_id") != concept["id"]
            or base.get("mode", "target") != "target" or base.get("change")):
        return machine._end(n, "같은 손님으로 테스트를 시작할 수 없어요. 매대 테스트를 다시 열어 주세요.", None)
    imp = machine._improve_state(n, base_run_id, concept["id"])
    values = fix["values"]
    item = next((it for it in imp["items"] if it["values"] == values), None)
    if item is None:
        item = machine._add_item(imp, improve.Base.of(base["concept"]), values, fix["reason"],
                                 fix["hypothesis"], fix["evidence"])
    item.update(reason=fix["reason"], hypothesis=fix["hypothesis"], evidence=fix["evidence"])
    run_id = item.get("run_id")
    variant = store.load_meta(run_id) if run_id else None
    if not variant or variant["status"] in {"stopped", "failed"}:
        run_id = machine._start_rerun(n, conv_id, base, item)
        variant = store.load_meta(run_id) if run_id else None
    if not variant:
        return machine._end(n, "고친 안을 시작할 수 없어요. 매대 테스트를 다시 열어 주세요.", None)
    return [Stage(current="improve"), machine.improve_card(n),
            *machine._end(n, "같은 손님에게 원래 안과 고친 안을 보여주고 있어요.", None)]


def _summer_trend(finding: dict) -> str:
    by_month = {point["month"]: point["search_index"] for point in finding["series"]}
    peaks = []
    for year in (2025, 2026):
        summer = [by_month.get(f"{year}-{month:02}") for month in (6, 7, 8)]
        if any(value is None for value in summer):
            return _MISSING
        peaks.append(max(summer))
    previous, current = peaks
    stage = "·".join(finding["stage"]) or "판정 기준에 해당하는 흐름 없음"
    change = ""
    if previous > 0 and current != previous:
        direction = "낮아요" if current < previous else "높아요"
        change = f" 전년 같은 기간보다 {abs(current / previous - 1):.0%} {direction}."
    return (f"수박화채의 6~8월 최고 검색 지수는 2025년 {previous:g}, 2026년 {current:g}예요.{change} "
            f"트렌드 판정은 {stage}예요.")


def _alternative(findings: list[dict], keyword: str) -> str:
    rising = [item["keyword"] for item in findings if item["keyword"] != keyword
              and "상승기" in item["stage"] and "광고성 바이럴" not in item["stage"]]
    if rising:
        return f"상승기로 판정된 다른 검색어는 {', '.join(rising)}예요. 새 컨셉을 검토할 때 참고할 수 있어요."
    promoted = [item["keyword"] for item in findings if item["keyword"] != keyword
                and "상승기" in item["stage"] and "광고성 바이럴" in item["stage"]]
    if promoted:
        return (f"다른 음료 검색어 중 {', '.join(promoted)}는 상승기와 광고성 바이럴에 함께 해당해요. "
                "제공 자료에서 수박화채를 대체할 과일 맛은 확인되지 않았어요.")
    stable = [item["keyword"] for item in findings if item["keyword"] != keyword and "안정기" in item["stage"]]
    if stable:
        return f"광고성 바이럴을 제외한 상승기 검색어는 자료 없음. 음료 범위를 넓히면 {', '.join(stable)}는 안정기예요."
    return _MISSING


def _history() -> str:
    try:
        assets = onsite.load("assets")
    except onsite.NoData:
        return _MISSING
    launched = [asset for asset in assets if asset["brand"] == _CONCEPT["brand"]
                and "수박" in (asset["name"] or "") and asset["launched"]
                and asset["status"] in {"운영", "단종"}]
    if not launched:
        return _MISSING
    years = ", ".join(f"{year}년" for year in sorted({asset["launched"][:4] for asset in launched}))
    discontinued = [asset for asset in launched if asset["status"] == "단종"]
    summary = f"제품 자산에서 밀키스 수박 계열 출시 이력이 {len(launched)}건 확인돼요({years})."
    if not discontinued:
        return summary
    recorded = sum(bool((asset["reason"] or "").strip()) for asset in discontinued)
    reason = f"단종 {len(discontinued)}건 중 {recorded}건에 사유가 남아 있어요." if recorded else "단종 사유 기록 없음."
    return f"{summary} {reason}"


# 초기에 승인한 대본 데모는 500mL PET 컨셉을 다룬다.
_DEMO_PET = next(v for v in _CONCEPT["variants"] if v["pack"] == "PET")


def _price() -> str:
    price = _DEMO_PET["price"]
    prefix = f"{_DEMO_PET['volume_ml']}mL PET 권장 소비자가는 {_won(price)}이에요."
    try:
        summary = onsite.load_json("survey_summary")
    except onsite.NoData:
        summary = {}
    wtp = summary.get("concepts", {}).get(_CONCEPT["name"], {}).get("wtp", {})
    if not wtp.get("n") or any(wtp.get(key) is None for key in ("p25", "median", "p75")):
        return f"{prefix} 정량 조사 최대 지불의향가격은 자료 없음."
    median = wtp["median"]
    if price == median:
        difference = "중앙값과 같아요."
    else:
        relation = "높아요" if price > median else "낮아요"
        difference = f"권장가는 중앙값보다 {_won(abs(price - median))} {relation}."
    return (f"{prefix} 같은 규격으로 답한 정량조사 응답자 {wtp['n']:,}명의 최대 지불의향가격 중앙값은 "
            f"{_won(median)}, 가운데 절반은 {_won(wtp['p25'])}~{_won(wtp['p75'])}이에요. {difference}")


def _competition() -> str:
    try:
        products = catalog.current()
    except FileNotFoundError:
        return _MISSING
    if not any(product.sku for product in products):
        return _MISSING
    rivals = [product for product in products if product.shelf == catalog.BEVERAGES
              and product.kind == _CONCEPT["kind"] and product.pack == 1 and not product.is_own
              and product.price > 0]
    if not rivals:
        return _MISSING

    def price_range(items: list[catalog.Product]) -> str:
        prices = [item.price for item in items]
        low, high = min(prices), max(prices)
        return _won(low) if low == high else f"{_won(low)}~{_won(high)}"

    comparable = [product for product in rivals if product.volume == _DEMO_PET["volume_ml"] and product.container == "페트"]
    pet_range = f"{len(comparable)}종이 {price_range(comparable)}이에요" if comparable else _MISSING
    return (f"결합 매대의 타사 단품 탄산 {len(rivals)}종은 {price_range(rivals)}이에요. "
            f"같은 {_DEMO_PET['volume_ml']}mL PET는 {pet_range}. 공개 매대 가격과 판매자료 평균 단가를 사용했어요.")


def _distribution() -> str:
    storage = _CONCEPT["storage"]
    rate = catalog.store_rate(storage) if storage in {"냉장", "냉동"} else None
    if rate is None:
        return f"보관 조건은 {storage}이에요. 이 조건의 편의점 진열 가능 점포율은 자료 없음."
    return f"보관 조건은 {storage}이에요. 편의점의 {rate:g}%에서 이 조건으로 진열할 수 있어요."


def demo_diagnosis() -> dict[str, str]:
    keyword = _CONCEPT["keywords"][0]
    findings = verdicts()
    finding = next((item for item in findings if item["keyword"] == keyword), None)
    return {
        "trend": _summer_trend(finding) if finding else _MISSING,
        "history": _history(),
        "price": _price(),
        "competition": _competition(),
        "distribution": _distribution(),
        "alternative": _alternative(findings, keyword),
    }


_NAV = {"diagnosis": "컨셉 진단", "fgi": "FGI 보기", "fgd": "FGD 보기", "compare": "개선 비교"}
_WELCOME = ("밀키스 화채를 고른 손님과 지나친 손님이 원탁에 모였어요. ‘재생 시작’을 누르면 첫 발언부터 들여다볼 수 있어요. "
            "컨셉 진단은 제공 자료를 집계했고, 조사실 발언은 창작 대본이에요. 개선안의 선택률은 데모용 가상 소비자로 계산했어요.")
_SCOPE = ("이 데모에서는 밀키스 화채의 컨셉 진단, FGI·FGD 대본, 개선 비교를 볼 수 있어요. "
          "보고 싶은 항목을 골라 주세요.")


def _demo_section(text: str, reply_ids: list[str]) -> str | None:
    for action in reply_ids:
        section = action.removeprefix("w7-demo-")
        if section in _NAV:
            return section
    text = text.casefold()
    if "fgi" in text and "fgd" in text:
        return "fgd"
    if "fgi" in text or "심층" in text or "인터뷰" in text:
        return "fgi"
    if "fgd" in text or "토론" in text:
        return "fgd"
    if re.search(r"개선|바꾸|올리|내리|낮추|높이|탄산(?:을|이)?\s*(?:빼|없)|무탄산|제형|맛(?:을|이)?\s*(?:변경|은은|옅|약하)", text):
        return "compare"
    if re.search(r"진단|가격|지불|얼마|검색|트렌드|피크아웃|유통|보관|진열|이력|단종|과거|대안|수박\s*화채.*지났", text):
        return "diagnosis"
    if "비교" in text:
        return "compare"
    return None


def _reply(section: str | None, text: str, diagnosis: dict[str, str]) -> str:
    text = text.casefold()
    if section == "diagnosis":
        if re.search(r"가격|지불|얼마", text):
            return f"{diagnosis['price']} {diagnosis['competition']}"
        if re.search(r"유통|보관|진열", text):
            return diagnosis["distribution"]
        if re.search(r"이력|과거|단종", text):
            return diagnosis["history"]
        if re.search(r"검색|트렌드|피크아웃|대안|지났", text):
            return f"{diagnosis['trend']} {diagnosis['alternative']}"
        return f"제공 자료에서 검색 흐름, 과거 출시 이력, 가격과 보관 조건을 확인했어요. {diagnosis['trend']}"
    if section == "fgi":
        return "집단 심층 인터뷰(FGI)를 열었어요. 칠성이가 같은 질문을 한 사람씩 드리고, 각 참석자는 다른 사람의 답을 보지 않고 말해요."
    if section == "fgd":
        if "fgi" in text and "fgd" in text:
            return ("집단 심층 인터뷰(FGI)는 같은 질문에 각자 답해요. 집단 토론(FGD)은 1차에 각자 답한 뒤 "
                    "2차에 앞 발언을 보고 서로 응답해요. 화면에서 집단 토론을 열었어요.")
        return "집단 토론(FGD)을 열었어요. 1차에는 각자 선택 이유를 말하고, 2차에는 다른 참석자의 앞 발언에 답해요."
    if section == "compare":
        if re.search(r"가격|올리|내리|낮추|높이", text):
            return "가격만 내린 안, 그대로 둔 안, 올린 안을 같은 합성 패널에서 비교한 데모예요. 세 가격의 선택률을 볼 수 있어요."
        if re.search(r"탄산|제형", text):
            return "탄산만 빼는 제형 변경안과 원래 안을 같은 합성 패널에서 비교한 데모예요."
        if "맛" in text:
            return "수박화채 맛을 은은하게 하는 안과 원래 안을 같은 합성 패널에서 비교한 데모예요."
        return "같은 합성 패널에 원래 안과 한 가지 조건만 바꾼 안을 보여 준 데모예요. 맛, 제형, 가격을 골라 비교할 수 있어요."
    return _SCOPE


def demo_turn(text: str, reply_ids: list[str], n_user: int) -> Iterator[Say | Card | Actions]:
    """시연 질문을 기존 집계·대본·비교 결과로 연결한다."""
    from agent.improve import demo_comparison
    from shelftest import group

    first = n_user <= 1
    section = "fgd" if first else _demo_section(text, reply_ids)
    sessions = group.demo_sessions()
    linked = next(((mode, turn) for mode, session in sessions["modes"].items() for turn in session["turns"]
                   if f"w7-quote/{turn['id']}" in reply_ids), None)
    if linked:
        section = "compare"
    diagnosis = demo_diagnosis()
    view = section if section in ("diagnosis", "compare") else "room"
    mode: Literal["fgi", "fgd"] = "fgi" if section == "fgi" else "fgd"
    comparison = demo_comparison()
    if view == "compare":
        if re.search(r"가격|올리|내리|낮추|높이", text):
            comparison["focus"] = "price"
        elif "맛" in text and not re.search(r"탄산|제형", text):
            comparison["focus"] = "flavor"
    message = _WELCOME if first else _reply(section, text, diagnosis)
    reference = {}
    if linked:
        mode, turn = linked
        reference["quoteId"] = turn["id"]
        comparison["focus"] = turn["topic"]
        topic = {"price": "가격", "form": "제형", "flavor": "맛"}[turn["topic"]]
        speaker = next(p["label"] for p in sessions["participants"] if p["id"] == turn["person"])
        message = f"{mode.upper()} {turn['round']}차의 {speaker} 발언을 개선안에 붙였어요. {topic}을 바꾼 안과 원래 안을 비교해 보세요."
    yield Say(text=message)
    yield Card(id="w7-room", stage="result", kind="group", title="밀키스 화채", status="ready",
               payload={"demo": True, "concept": _CONCEPT["name"], **sessions, **reference,
                        "diagnosis": diagnosis, "comparison": comparison,
                        "view": view, "mode": mode, "turn": n_user})
    yield Actions(id="w7-demo-nav", actions=[ActionItem(id=f"w7-demo-{key}", label=label)
                                            for key, label in _NAV.items() if key != (section or "fgd")])
