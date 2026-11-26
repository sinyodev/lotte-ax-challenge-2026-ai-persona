import json

import pandas as pd
import pytest

from onsite.schema import CSV_COLUMNS
from onsite.survey import CONCEPT_NAMES, RATING_FIELDS, RESPONDENT_FIELDS, SHEETS, build_survey

MILKIS, COFFEE, JUICE = CONCEPT_NAMES


def respondent(rid, **changes):
    return {
        "rid": rid, "gender": "여성", "birth_year": 2002, "age_band": "19~29세",
        "region": "견본권역", "job": "견본직업", "income": None, "buy_coffee": 2,
        "buy_soda": 3, "buy_juice": 4, "main_channel": "견본채널", "novelty": 3,
        "health": 3, "price_sens": 3, "seconds": 250, "order": "견본순서",
        "timestamp": "2026-10-08 00:00:00", "phone_hash": f"견본-{rid}",
    } | changes


def ratings_for(rid, *, milkis_intent=4, milkis_position=1, flat=False):
    positions = [milkis_position] + [p for p in (1, 2, 3) if p != milkis_position]
    return [
        {"rid": rid, "concept": concept, "understand": 3, "like": 3, "distinct": 3,
         "intent": 3 if flat or concept != MILKIS else milkis_intent, "price_ok": 3,
         "wtp": None, "monthly": 1, "shown_price": 1800, "price_format": "정가 표기",
         "position": position, "comment": "지어낸 견본"}
        for concept, position in zip(CONCEPT_NAMES, positions)
    ]


def workbook(tmp_path, respondents, ratings=None, *, population=(), questionnaire=()):
    path = tmp_path / "견본.xlsx"
    if ratings is None:
        ratings = [row for person in respondents for row in ratings_for(person["rid"])]
    with pd.ExcelWriter(path) as writer:
        for index, rows, fields in ((0, respondents, RESPONDENT_FIELDS), (1, ratings, RATING_FIELDS)):
            excel = pd.DataFrame(rows, columns=list(fields.values())).rename(
                columns={column: original for original, column in fields.items()}
            )
            excel.to_excel(writer, sheet_name=SHEETS[index], index=False)
        pd.DataFrame(questionnaire, columns=["영역", "문항 내용"]).to_excel(
            writer, sheet_name=SHEETS[2], index=False
        )
        pd.DataFrame(population, columns=["구분", "항목", "모집단 비중(추정)"]).to_excel(
            writer, sheet_name=SHEETS[3], index=False
        )
    tables, report = build_survey(path)
    return tables, {rule["rule"]: rule for rule in report}


def test_duplicate_keeps_earliest_and_does_not_group_blank_hashes(tmp_path):
    people = [
        respondent("late", phone_hash="같은 값", timestamp="2026-10-09"),
        respondent("early", phone_hash="같은 값", timestamp="2026-10-01"),
        respondent("tie", phone_hash="같은 값", timestamp="2026-10-01"),
        respondent("unknown-date", phone_hash="같은 값", timestamp=None),
        respondent("blank-one", phone_hash=None), respondent("blank-two", phone_hash=" "),
        respondent("0007"),
    ]
    tables, report = workbook(tmp_path, people)
    assert tables["survey_respondents"]["rid"].tolist() == ["early", "blank-one", "blank-two", "0007"]
    assert tables["survey_ratings"]["rid"].nunique() == 4
    rule = report["duplicate_hash"]
    assert rule["removed"] == 3 and rule["flagged"] == 0
    assert "답한 사람은 1명" in rule["detail"]
    for name, frame in tables.items():
        if name in CSV_COLUMNS:
            assert tuple(frame.columns) == CSV_COLUMNS[name]
    assert "phone_hash" not in tables["survey_respondents"]
    assert "timestamp" not in tables["survey_respondents"]


def test_same_id_cannot_represent_two_respondent_rows(tmp_path):
    with pytest.raises(ValueError, match="응답자 ID가 비었거나 겹칩니다"):
        workbook(tmp_path, [respondent("same"), respondent("same", phone_hash="다른 값")])


def test_inattentive_counts_raw_overlap_and_net_removals(tmp_path):
    people = [
        respondent("first", phone_hash="견본 묶음"),
        respondent("duplicate", phone_hash="견본 묶음", seconds=60, timestamp="2026-10-09"),
        respondent("same-score", seconds=120), respondent("too-fast", seconds=119),
        respondent("both", seconds=40), respondent("threshold", seconds=120), respondent("partial"),
    ]
    ratings = [row for person in people for row in ratings_for(
        person["rid"], flat=person["rid"] in {"duplicate", "same-score", "both", "partial"}
    )]
    ratings[-1]["intent"] = None
    tables, report = workbook(tmp_path, people, ratings)
    assert tables["survey_respondents"]["rid"].tolist() == ["first", "threshold", "partial"]
    assert report["duplicate_hash"]["removed"] == 1
    rule = report["inattentive"]
    assert rule["removed"] == 3
    assert "모두 같은 답은 3건" in rule["detail"]
    assert "120초 미만에 마친 답은 3건" in rule["detail"]
    assert "모두 해당하는 2건" in rule["detail"]
    assert "한 번만 세면 4건" in rule["detail"]
    assert "1건은 중복 정제에서 이미 빠졌고" in rule["detail"]


def test_age_range_and_band_boundaries(tmp_path):
    ages = [18, 19, 29, 30, 39, 40, 49, 50, 59, 60]
    people = [respondent(f"age-{age}", birth_year=2026 - age) for age in ages]
    people.append(respondent("unknown-age", birth_year=None))
    tables, report = workbook(tmp_path, people)
    assert tables["survey_respondents"]["rid"].tolist() == [f"age-{age}" for age in ages[1:-1]]
    assert tables["survey_respondents"]["age_band"].tolist() == [
        "19~29세", "19~29세", "30~39세", "30~39세", "40~49세", "40~49세", "50~59세", "50~59세",
    ]
    assert report["age_mismatch"]["removed"] == 3
    assert report["age_mismatch"]["flagged"] == 6


def test_two_population_margins_and_weight_mean(tmp_path):
    age_groups = [(2002, "19~29세", "여성"), (1982, "40~49세", "남성")]
    regions = ("견본가", "견본나")
    people = []
    for index, (year, band, gender) in enumerate(age_groups):
        for other, region in enumerate(regions):
            for number in range(1 + index + other):
                people.append(respondent(f"{index}-{other}-{number}", birth_year=year, age_band=band,
                                         gender=gender, region=region))
    population = [("연령×성별", "19~29세 여성", 0.35), ("연령×성별", "40~49세 남성", 0.65),
                  ("거주권역", "견본가", 0.6), ("거주권역", "견본나", 0.4)]
    tables, report = workbook(tmp_path, people, population=population)
    respondents = tables["survey_respondents"]
    assert respondents["weight"].mean() == pytest.approx(1)
    assert respondents.groupby(["age_band", "gender"])["weight"].sum().div(len(people)).to_dict() == (
        pytest.approx({("19~29세", "여성"): 0.35, ("40~49세", "남성"): 0.65})
    )
    assert respondents.groupby("region")["weight"].sum().div(len(people)).to_dict() == (
        pytest.approx({"견본가": 0.6, "견본나": 0.4})
    )
    detail = report["population_weight"]["detail"]
    assert "연령대×성별" in detail and "권역" in detail
    assert detail.count("최대 차이는 0.00%p") == 2


def test_weight_cap_and_missing_population_cell_keep_average_one(tmp_path):
    people = [respondent(f"common-{index}") for index in range(9)]
    people.append(respondent("rare", birth_year=1982, gender="남성"))
    population = [("연령×성별", "19~29세 여성", 0.1), ("연령×성별", "40~49세 남성", 0.8),
                  ("연령×성별", "50~59세 여성", 0.1), ("거주권역", "견본권역", 1.0)]
    tables, report = workbook(tmp_path, people, population=population)
    weights = tables["survey_respondents"].set_index("rid")["weight"]
    assert weights.mean() == pytest.approx(1)
    assert weights.max() == weights["rare"] == 5
    assert (weights >= 0).all()
    rule = report["population_weight"]
    assert rule["flagged"] == 1
    assert "최대 차이는 40.00%p" in rule["detail"]


def test_order_adjustment_uses_equal_weight_per_position_and_segments_use_population_weights(tmp_path):
    people = [respondent("young", region="견본가")]
    for index, region in enumerate(["견본가", "견본나", "견본나", "견본가"]):
        people.append(respondent(f"older-{index}", birth_year=1982, region=region))
    ratings = [row for index, person in enumerate(people) for row in ratings_for(
        person["rid"], milkis_intent=[5, 4, 2, 2, 5][index], milkis_position=[1, 1, 1, 2, 3][index]
    )]
    population = [("연령×성별", "19~29세 여성", 0.6), ("연령×성별", "40~49세 여성", 0.4),
                  ("거주권역", "견본가", 0.9), ("거주권역", "견본나", 0.1)]
    tables, report = workbook(tmp_path, people, ratings, population=population)
    summary = tables["survey_summary"]["concepts"][MILKIS]
    assert summary["top2"] == pytest.approx({
        "raw": 0.6, "clean": 0.6, "weighted": 0.9, "order_adjusted": 5 / 9,
    })
    assert summary["by_position"] == {
        "1": {"n": 3, "top2": 2 / 3}, "2": {"n": 1, "top2": 0}, "3": {"n": 1, "top2": 1},
    }
    assert len(summary["segments"]) == 8
    segments = {(row["age_band"], row["gender"]): (row["n"], row["top2"]) for row in summary["segments"]}
    assert segments["40~49세", "여성"] == pytest.approx((4, 0.75))
    assert segments["40~49세", "남성"] == (0, None)
    assert "모집단 가중치를 적용하지 않았어요" in report["order_adjustment"]["detail"]


@pytest.mark.parametrize("leading_wording, special_price", [(True, False), (False, True), (False, False)])
def test_questionnaire_and_price_display_set_leading_without_removing_scores(
    tmp_path, leading_wording, special_price
):
    ratings = ratings_for("one")
    for row in ratings:
        if row["concept"] == JUICE:
            row.update(intent=5, price_ok=4, shown_price=3200)
            if special_price:
                row["price_format"] = "정가 4,700원 → 출시기념가 3,200원"
    questionnaire = [
        ("구매 의향" if leading_wording else "이해도", "쥬시모먼트는 프리미엄 음료예요. 사 보겠어요?"),
        ("가격 수용도", "이 가격에 사 보겠어요?"),
    ]
    tables, report = workbook(tmp_path, [respondent("one")], ratings, questionnaire=questionnaire)
    cleaned = tables["survey_ratings"].set_index("concept")
    assert cleaned["leading"].to_dict() == {
        MILKIS: False, COFFEE: False, JUICE: leading_wording or special_price,
    }
    assert tuple(cleaned.loc[JUICE, ["intent", "price_ok", "shown_price"]]) == (5, 4, 3200)
    assert tables["survey_summary"]["concepts"][JUICE]["leading"] is (leading_wording or special_price)
    rule = report["leading_question"]
    assert rule["removed"] == 0
    assert rule["flagged"] == int(leading_wording or special_price)
    assert ("구매의향 문항" in rule["detail"]) is leading_wording
    assert ("정가 4,700원과 출시기념가 3,200원" in rule["detail"]) is special_price
    assert "PET 1,800원" in rule["detail"] and "캔 1,200원" in rule["detail"]


def test_wtp_blanks_are_excluded_and_unseen_order_has_no_adjustment(tmp_path):
    values = [0, 1000, None, " ", 2000]
    people = [respondent(f"r{i}") for i in range(len(values))]
    ratings = []
    for person, value in zip(people, values):
        rows = ratings_for(person["rid"])
        rows[0]["wtp"] = value
        ratings.extend(rows)
    tables, _ = workbook(tmp_path, people, ratings)
    summary = tables["survey_summary"]["concepts"]
    assert summary[MILKIS]["wtp"] == {"median": 1000, "p25": 500, "p75": 1500, "n": 3}
    assert summary[COFFEE]["wtp"] == {"median": None, "p25": None, "p75": None, "n": 0}
    assert summary[MILKIS]["by_position"]["2"] == {"n": 0, "top2": None}
    assert summary[MILKIS]["top2"]["order_adjusted"] is None


@pytest.mark.parametrize("all_excluded", [False, True])
def test_empty_raw_or_empty_clean_sample_serializes_nulls(tmp_path, all_excluded):
    people = [respondent("removed", seconds=20)] if all_excluded else []
    population = [("연령×성별", "19~29세 여성", 1.0), ("거주권역", "견본권역", 1.0)]
    tables, report = workbook(tmp_path, people, population=population)
    assert tables["survey_respondents"].empty and tables["survey_ratings"].empty
    summary = tables["survey_summary"]
    assert summary["n"] == {"raw": len(people), "clean": 0}
    assert summary["concepts"][MILKIS]["top2"] == {
        "raw": 1.0 if all_excluded else None, "clean": None, "weighted": None, "order_adjusted": None,
    }
    assert all(r["n"] == 0 and r["top2"] is None for r in summary["concepts"][MILKIS]["segments"])
    assert "남은 응답이 없어요" in report["population_weight"]["detail"]
    json.dumps(summary, allow_nan=False)
    assert sum(rule["removed"] for rule in report.values()) == len(people)
