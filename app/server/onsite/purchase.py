"""컨셉 조사에서 밝힌 의향과 출시 후 12개월 구매경험률을 각 출처에서 읽는다."""

import onsite


def percent(value):
    return "미측정" if value is None else f"{value:.1%}"


def measure_lines(row):
    if "intent_method" in row:
        adjustment = "제시 순서 보정" if row["intent_method"] == "order_adjusted" else "모집단 가중"
        intent = f"조사 당시 컨셉의 구매의향(5점 중 4·5점, {adjustment}) {percent(row['intent_top2'])}"
        if row["leading"]:
            intent += " · 문항에 제품 장점을 강조한 설명이 포함됨"
    else:
        intent = f"과거 컨셉테스트 구매의향(상위 두 응답) {percent(row['intent_top2'])}"
    return [intent, f"출시 후 12개월 실제 구매경험률 {percent(row['trial_12m'])}"]


def outcomes():
    try:
        past = onsite.load("past_tests")
    except onsite.NoData:
        past = []
    try:
        survey = onsite.load_json("survey_summary")
    except onsite.NoData:
        survey = {}

    history = []
    for row in past:
        intent, actual = row["intent_top2"], row["trial_12m"]
        history.append({"product": row["product"], "test_year": row["year"], "category": row["category"],
                        "intent_top2": intent, "trial_12m": actual,
                        "actual_to_intent": actual / intent if intent and actual is not None else None,
                        "distribution_6m": row["distribution_6m"]})
    concepts = []
    for name, row in survey.get("concepts", {}).items():
        scores = row.get("top2") or {}
        method = "order_adjusted" if scores.get("order_adjusted") is not None else "weighted"
        # 같은 이름의 실적이 여러 연도에 있으면 어느 제품판인지 특정할 수 없다.
        matches = [r for r in history if r["product"] == name]
        observed = matches[0] if len(matches) == 1 else {}
        concepts.append({"product": name, "intent_top2": scores.get(method), "intent_method": method,
                         "leading": row.get("leading", False), "trial_12m": observed.get("trial_12m"),
                         "trial_source_year": observed.get("test_year")})
    return {"concepts": concepts, "history": history}
