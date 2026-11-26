"""정량 조사 워크북을 정제하고 컨셉별 구매의향을 요약한다."""

import math
from pathlib import Path

import pandas as pd

from .concepts import CONCEPTS
from .schema import CSV_COLUMNS
from .weights import WEIGHT_CAP, rake_weights

RESPONDENT_FIELDS = {
    "응답자ID": "rid", "성별": "gender", "출생연도": "birth_year", "연령대": "age_band",
    "거주권역": "region", "직업": "job", "월가구소득": "income",
    "커피음료_월구매횟수": "buy_coffee", "탄산_월구매횟수": "buy_soda",
    "주스_월구매횟수": "buy_juice", "주이용채널": "main_channel", "신제품시도성향": "novelty",
    "건강관심도": "health", "가격민감도": "price_sens", "응답시간(초)": "seconds",
    "제시순서": "order", "응답일시": "timestamp", "휴대폰해시": "phone_hash",
}
RATING_FIELDS = {
    "응답자ID": "rid", "컨셉": "concept", "컨셉이해도": "understand", "호감도": "like",
    "차별성": "distinct", "구매의향": "intent", "가격수용도": "price_ok",
    "최대지불의향가격": "wtp", "예상월구매횟수": "monthly", "제시가격": "shown_price",
    "가격제시방식": "price_format", "제시순서": "position", "자유응답": "comment",
}
SHEETS = ("1_응답자정보", "2_컨셉평가", "3_설문지", "4_모집단구성비")
CONCEPT_NAMES = tuple(concept["name"] for concept in CONCEPTS)
SCORE_COLUMNS = ("understand", "like", "distinct", "intent", "price_ok")
POSITIONS = (1, 2, 3)
MIN_SECONDS = 120
PANEL_YEAR = 2026  # 2026년 10월 조사. 생일 정보가 없어 연도 차이로 계산한다.
AGE_BANDS = ("19~29세", "30~39세", "40~49세", "50~59세")
GENDERS = ("여성", "남성")


def _rule(rule: str, label: str, detail: str, *, removed: int = 0, flagged: int = 0) -> dict:
    return {"source": "survey", "rule": rule, "label": label,
            "removed": removed, "flagged": flagged, "detail": detail}


def _read_population(frame: pd.DataFrame) -> pd.DataFrame:
    dimensions = frame["구분"].map({"연령×성별": "age_gender", "거주권역": "region"})
    age_gender = dimensions.eq("age_gender")
    items = frame["항목"].astype("string").str.strip()
    age_parts = items.where(age_gender).str.extract(r"^(\d{2}~\d{2}세?)\s+(여성|남성)$")
    age_bands = age_parts[0].str.rstrip("세") + "세"
    shares = pd.to_numeric(frame["모집단 비중(추정)"], errors="coerce")
    if (dimensions.isna().any() or (age_gender & ~age_bands.isin(AGE_BANDS)).any()
            or (dimensions.eq("region") & (items.isna() | items.eq(""))).any()
            or not shares.between(0, 1).all()):
        raise ValueError("정량 조사의 모집단 구성비에서 구분, 항목 또는 비중을 읽을 수 없습니다.")
    population = pd.DataFrame({
        "dimension": dimensions, "age_band": age_bands, "gender": age_parts[1],
        "region": items.where(dimensions.eq("region")), "share": shares,
    }, columns=CSV_COLUMNS["population"])
    if population.drop(columns="share").duplicated().any():
        raise ValueError("정량 조사의 모집단 구성비에 같은 구간이 두 번 있습니다.")
    return population


def _remove_duplicates(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    hashes = raw["phone_hash"].astype("string").str.strip().replace("", pd.NA)
    times = pd.to_datetime(raw["timestamp"], format="mixed", errors="coerce", utc=True)
    ordered_hashes = hashes.loc[times.sort_values(kind="stable").index].dropna()
    removed = ordered_hashes.loc[ordered_hashes.duplicated()].index
    people = int(ordered_hashes[ordered_hashes.duplicated(keep=False)].nunique())
    return raw.drop(index=removed), _rule(
        "duplicate_hash", "두 번 이상 답한 응답자는 한 번만 남겼어요",
        f"원본에서 같은 휴대폰 해시로 답한 사람은 {people}명이에요. "
        f"응답 일시가 가장 이른 한 건씩만 남겨 {len(removed)}건을 뺐어요. "
        "일시가 같거나 모두 비어 있으면 원본에서 먼저 나온 답을 남겨요. 빈 해시는 비교에서 빼요.",
        removed=len(removed),
    )


def _remove_inattentive(raw: pd.DataFrame, respondents: pd.DataFrame,
                        ratings: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    scores = ratings.groupby("rid")[list(SCORE_COLUMNS)]
    all_same = scores.count().sum(axis=1).eq(len(CONCEPT_NAMES) * len(SCORE_COLUMNS)) & (
        scores.min().min(axis=1).eq(scores.max().max(axis=1))
    )
    flat = raw["rid"].isin(all_same.index[all_same])
    fast = raw["seconds"].lt(MIN_SECONDS)
    detected = flat | fast
    removed = detected.loc[respondents.index]
    n_removed = int(removed.sum())
    return respondents.loc[~removed].copy(), _rule(
        "inattentive", "같은 점수만 고르거나 너무 빨리 답한 응답을 뺐어요",
        f"원본에서 15개 평가 점수가 모두 같은 답은 {flat.sum()}건, "
        f"{MIN_SECONDS}초 미만에 마친 답은 {fast.sum()}건이에요. "
        f"두 기준에 모두 해당하는 {int((flat & fast).sum())}건을 한 번만 세면 {detected.sum()}건이에요. "
        f"이 가운데 {int(detected.sum()) - n_removed}건은 중복 정제에서 이미 빠졌고, "
        f"이 단계에서 {n_removed}건을 더 뺐어요.",
        removed=n_removed,
    )


def _correct_ages(raw: pd.DataFrame, respondents: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    age = PANEL_YEAR - raw["birth_year"]
    expected = pd.cut(age, bins=[18, 29, 39, 49, 59], labels=AGE_BANDS).astype("string")
    inside = expected.notna()
    mismatched = inside & raw["age_band"].ne(expected).fillna(True)
    kept = respondents.loc[inside.loc[respondents.index]].copy()
    corrected = int(mismatched.loc[kept.index].sum())
    kept["age_band"] = expected.loc[kept.index]
    removed = len(respondents) - len(kept)
    return kept, _rule(
        "age_mismatch", "출생연도로 나이대를 다시 확인했어요",
        f"조사 연도인 {PANEL_YEAR}년에서 출생연도를 뺐어요. "
        f"원본에서 범위 안의 나이대 불일치는 {mismatched.sum()}건, "
        f"19~59세를 벗어나거나 나이를 확인할 수 없는 답은 {(~inside).sum()}건이에요. "
        f"앞선 정제에서 남은 답 중 나이대 {corrected}건을 고치고 {removed}건을 뺐어요.",
        removed=removed, flagged=corrected,
    )


def _weight_respondents(respondents: pd.DataFrame, population: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    weights, detail = rake_weights(respondents, population)
    at_cap = int((weights >= WEIGHT_CAP - 1e-8).sum())
    if len(weights):
        detail = (f"나이대와 성별, 권역의 비중을 번갈아 맞췄어요. 가중치 평균은 {weights.mean():.2f}예요. "
                  f"상한은 {WEIGHT_CAP:g}이고 상한에 닿은 응답은 {at_cap}건이에요. " + detail)
    return respondents.assign(weight=weights), _rule(
        "population_weight", "모집단 구성에 따라 응답에 가중치를 줬어요", detail, flagged=at_cap
    )


def _mark_leading(questionnaire: pd.DataFrame, raw: pd.DataFrame,
                  ratings: pd.DataFrame) -> tuple[pd.DataFrame, set[str], dict]:
    juice = "쥬시모먼트"
    section = questionnaire["영역"].astype("string")
    intent = section.str.contains(r"구매\s*의향", na=False)
    wording = questionnaire["문항 내용"].astype("string")
    leading_intent = bool((intent & wording.str.contains(juice, regex=False, na=False)
                           & wording.str.contains(r"건강|정성|프리미엄", na=False)).any())
    price_question = bool(section.str.contains(r"가격\s*수용", na=False).any())
    juice_rows = raw["concept"].eq(juice)
    price_format = raw["price_format"].astype("string")
    different_price = price_format.str.contains(
        r"출시\s*기념가|정가.*[→➝]", na=False
    ) & juice_rows
    marked = ratings.index.isin(raw.index[juice_rows if leading_intent else different_price])
    notes = []
    if leading_intent:
        notes.append("쥬시모먼트의 구매의향 문항에 제품의 장점을 강조하는 소개가 붙었어요.")
    if different_price.any():
        question = "가격수용도를 물을 때 " if price_question else ""
        prices = price_format.loc[different_price].str.extract(
            r"정가\s*([\d,]+)원.*출시\s*기념가\s*([\d,]+)원"
        ).drop_duplicates()
        condition = "정가와 출시기념가"
        if len(prices) == 1 and prices.notna().all(axis=None):
            regular, launch = prices.iloc[0]
            condition = f"정가 {regular}원과 출시기념가 {launch}원"
        notes.append(f"쥬시모먼트는 {question}{condition} 두 가격을 함께 보여 줬어요.")
    if notes:
        notes.append("구매의향과 가격수용도를 다른 컨셉과 견줄 때 이 차이를 감안해 주세요.")
    milkis_prices = raw.loc[raw["concept"].eq("밀키스 화채"), "shown_price"].dropna()
    if not milkis_prices.empty and milkis_prices.eq(1800).all():
        notes.append("밀키스 화채는 500mL PET 1,800원 조건으로 물었어요. 250mL 캔 1,200원 조건은 묻지 않았어요.")
    if not notes:
        notes.append("구매의향 문구와 가격 표기에서 별도로 표시할 차이를 찾지 못했어요.")
    n_marked = int(marked.sum())
    design = {juice} if leading_intent or different_price.any() else set()
    report = _rule("leading_question", "구매의향 문구와 가격 표기를 확인했어요",
                   " ".join(notes), flagged=n_marked)
    return ratings.assign(leading=marked), design, report


def _top2(rows: pd.DataFrame, *, weighted: bool = False) -> float | None:
    valid = rows.loc[rows["intent"].between(1, 5)]
    top = valid["intent"].isin((4, 5))
    if weighted:
        total = valid["weight"].sum()
        return float(valid.loc[top, "weight"].sum() / total) if total else None
    return float(top.mean()) if len(valid) else None


def _order_top2(rows: pd.DataFrame) -> tuple[dict, float | None]:
    by_position = {}
    for position in POSITIONS:
        seen = rows.loc[rows["position"].eq(position)]
        by_position[str(position)] = {"n": len(seen), "top2": _top2(seen)}
    rates = [position["top2"] for position in by_position.values()]
    adjusted = sum(rates) / len(rates) if all(rate is not None for rate in rates) else None
    return by_position, adjusted


def _segments(rows: pd.DataFrame) -> list[dict]:
    segments = []
    for age_band in AGE_BANDS:
        for gender in GENDERS:
            cell = rows.loc[rows["age_band"].eq(age_band) & rows["gender"].eq(gender)]
            segments.append({"age_band": age_band, "gender": gender, "n": cell["rid"].nunique(),
                             "top2": _top2(cell, weighted=True)})
    return segments


def _wtp(rows: pd.DataFrame) -> dict:
    valid = rows["wtp"].dropna()
    if valid.empty:
        return {"median": None, "p25": None, "p75": None, "n": 0}
    lower, median, upper = valid.quantile([0.25, 0.5, 0.75])
    return {"median": float(median), "p25": float(lower), "p75": float(upper), "n": len(valid)}


def _summarize(raw: pd.DataFrame, ratings: pd.DataFrame, respondents: pd.DataFrame,
               design: set[str], n_raw: int) -> tuple[dict, dict]:
    summary = {"n": {"raw": n_raw, "clean": len(respondents)}, "concepts": {}}
    comparisons = []
    merged = ratings.merge(respondents[["rid", "weight", "age_band", "gender"]],
                           on="rid", validate="many_to_one")
    for name in CONCEPT_NAMES:
        rows = merged.loc[merged["concept"].eq(name)]
        by_position, adjusted = _order_top2(rows)
        top2 = {"raw": _top2(raw.loc[raw["concept"].eq(name)]), "clean": _top2(rows),
                "weighted": _top2(rows, weighted=True), "order_adjusted": adjusted}
        summary["concepts"][name] = {
            "top2": top2, "by_position": by_position, "segments": _segments(rows),
            "wtp": _wtp(rows), "leading": name in design,
        }
        rates = " → ".join(f"{rate:.1%}" if rate is not None else "자료 없음" for rate in top2.values())
        comparisons.append(f"{name} {rates}")
    report = _rule(
        "order_adjustment", "세 제시 순서의 구매의향을 같은 비중으로 계산했어요",
        "정제한 답에서 첫째·둘째·셋째로 본 사람의 구매의향 4·5점 비율을 각각 구해 "
        "세 값에 같은 비중을 줬어요. 순서 보정에는 모집단 가중치를 적용하지 않았어요. "
        "한 순서라도 평가가 없으면 순서 보정값은 비워요. "
        f"정제 전 → 정제 후 → 모집단 가중 → 순서 보정은 {', '.join(comparisons)}예요.",
    )
    return summary, report


def _validate_keys(respondents: pd.DataFrame, ratings: pd.DataFrame) -> None:
    if respondents["rid"].isna().any() or respondents["rid"].duplicated().any():
        raise ValueError("정량 조사에서 응답자 ID가 비었거나 겹칩니다.")
    if (ratings.duplicated(["rid", "concept"]).any() or not ratings["rid"].isin(respondents["rid"]).all()
            or not ratings["concept"].isin(CONCEPT_NAMES).all()):
        raise ValueError("정량 조사에서 응답자별 컨셉 평가를 한 건씩 연결할 수 없습니다.")


def build_survey(path: Path) -> tuple[dict[str, pd.DataFrame | dict], list[dict]]:
    frames = pd.read_excel(path, sheet_name=list(SHEETS), dtype={"응답자ID": str, "휴대폰해시": str})
    raw, raw_ratings, questionnaire, raw_population = (frames[name] for name in SHEETS)
    raw = raw[list(RESPONDENT_FIELDS)].rename(columns=RESPONDENT_FIELDS)
    raw_ratings = raw_ratings[list(RATING_FIELDS)].rename(columns=RATING_FIELDS)
    _validate_keys(raw, raw_ratings)
    birth_year = pd.to_numeric(raw["birth_year"], errors="coerce")
    raw = raw.assign(birth_year=birth_year.where(birth_year.mod(1).eq(0)),
                     seconds=pd.to_numeric(raw["seconds"], errors="coerce"))
    for score in SCORE_COLUMNS:
        values = pd.to_numeric(raw_ratings[score], errors="coerce")
        raw_ratings[score] = values.where(values.isin(range(1, 6)))
    wtp = pd.to_numeric(raw_ratings["wtp"], errors="coerce")
    raw_ratings["wtp"] = wtp.where(wtp.map(math.isfinite))
    population = _read_population(raw_population)

    respondents, duplicate_report = _remove_duplicates(raw)
    respondents, inattentive_report = _remove_inattentive(raw, respondents, raw_ratings)
    respondents, age_report = _correct_ages(raw, respondents)
    respondents, weight_report = _weight_respondents(respondents, population)
    ratings = raw_ratings.loc[raw_ratings["rid"].isin(respondents["rid"])]
    ratings, design, leading_report = _mark_leading(questionnaire, raw_ratings, ratings)
    summary, order_report = _summarize(raw_ratings, ratings, respondents, design, len(raw))
    return {
        "survey_respondents": respondents[list(CSV_COLUMNS["survey_respondents"])],
        "survey_ratings": ratings[list(CSV_COLUMNS["survey_ratings"])],
        "population": population,
        "survey_summary": summary,
    }, [duplicate_report, inattentive_report, age_report, weight_report, order_report, leading_report]
