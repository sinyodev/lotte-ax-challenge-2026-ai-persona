from collections import Counter
from types import SimpleNamespace
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from calibrate import reliability as rel


def test_retest_keeps_pairs_and_distinguishes_no_purchase():
    r = rel.retest({"a": "배", "b": "사지 않음", "c": "물", "d": None},
                   {"a": "배", "b": "사지 않음", "c": "차", "d": "물", "e": "차"})
    assert r["n"] == 3 and r["value"] == 2/3 and r["passed"] is False
    assert (r["detail"]["same"], r["detail"]["same_product"], r["detail"]["both_no_purchase"]) == (2, 1, 1)
    assert r["detail"]["same_product_rate"] == 1/3
    assert r["low"] < r["value"] < r["high"]
    assert rel.retest({}, {})["value"] is None
    assert rel.retest(dict(enumerate("aaaaaaabbb")), dict(enumerate("aaaaaaaaaa")))["passed"]


def test_direction_common_panel_exact_mcnemar_and_wtp():
    def first(n):
        return {i: i < n for i in range(100)}
    prices = {1600: first(70), 1800: first(40), 2000: first(20)}
    prices[1600][99] = None
    r = rel.direction(prices, first(75), [1600, 1800, 2000, None], {"n": 3})
    assert r["passed"]
    d = r["detail"]
    assert [x["n"] for x in d["price"]] == [99]*3
    assert d["price_endpoints"]["p"] == pytest.approx(2**-49)
    assert d["promo"]["low"] > 0 and d["promo"]["gain"] == 35
    assert [x["share"] for x in d["survey_wtp"]] == [1, 2/3, 1/3]
    r = rel.direction({1600: first(1), 1800: first(4), 2000: first(0)}, first(4), [], {})
    assert not r["passed"] and not r["detail"]["monotone"]
    assert r["detail"]["promo"]["p"] == 1 and r["detail"]["promo"]["low"] <= 0


def test_sales_test_months_are_held_out_and_matched_coverage_reported():
    weights = {("가", "갑"): .8, ("나", "을"): .2}
    catalog = {"가물": ("water", "물"), "나물": ("water2", "물"), "차": ("tea", "차")}
    picks = [dict(age=age, sex=sex, product=p) for age, sex in weights
             for p in ("가물", "나물", "나물", "차", "매칭 없음")]
    sales = []
    for year in (2024, 2025):
        for month in range(1, 13):
            amounts = {"water": 10, "water2": 20, "tea": 70, "매대 밖": 10}
            if year == 2025:
                amounts.update(water=20, water2=30, tea=50, 추가=10)
            for sku, units in amounts.items():
                sales.append(dict(channel="편의점", month=f"{year}-{month:02}", sku=sku, units=units))
    r = rel.sales_rank(picks, weights, catalog, sales)
    assert r["n_products"] == 3 and r["gap"] == pytest.approx(25)
    assert r["detail"]["calibrated"]["gap"] == pytest.approx(20)
    assert r["detail"]["calibrated"]["rho"] == pytest.approx(1)
    assert r["detail"]["matched_history"] == pytest.approx({"rho": 1, "gap": 20})
    assert r["detail"]["floor"]["gap_products"] == 5 and r["detail"]["floor"]["n_products"] == 4
    assert r["detail"]["matched_picks"] == 8 and not r["passed"]
    missing = rel.sales_rank([r for r in picks if r["product"] != "차"], weights, catalog, sales)
    assert missing["detail"]["calibrated"]["rho"] is None


def test_survey_match_weighting_ties_and_undefined_correlations():
    weights = {("갑", str(i)): w for i, w in enumerate([.1, .2, .3, .4])}
    names = ["가", "나", "다"]
    selections, segments = {}, {}
    for offset, name in enumerate(names):
        selections[name] = [dict(age=age, sex=sex, selected=j < i + offset)
                            for i, (age, sex) in enumerate(weights) for j in range(6)]
        segments[name] = {cell: i/5 for i, cell in enumerate(weights)}
    r = rel.survey_match(selections, segments, dict(zip(names, [.2, .4, .6])), weights)
    assert r["passed"] and r["detail"]["order"]["virtual"] == names[::-1]
    for c in r["detail"]["concepts"]:
        assert c["rho"] == pytest.approx(1) and -1 <= c["low"] < c["high"] <= 1
        assert c["cells"] == len(weights)
    assert r["detail"]["concepts"][0]["rate"] == pytest.approx(2/6)
    r = rel.survey_match(selections, segments, dict.fromkeys(names, .5), weights)
    assert not r["passed"] and not r["detail"]["order"]["same"]
    assert rel.rank_interval([0, 0], [1, 2], [6, 6]) == (None, None, None)


@pytest.fixture
def command():
    path = Path(__file__).resolve().parents[3] / "scripts" / "reliability4.py"
    spec = importlib.util.spec_from_file_location("reliability_command", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_command_resumes_and_retest_uses_two_independent_queries(tmp_path, monkeypatch, command):
    cmd = command
    args = SimpleNamespace(people=2, per_cell=1, workers=2, version="test", only=[1])
    monkeypatch.setattr(cmd, "OUT", tmp_path)
    monkeypatch.setattr(cmd, "settings", lambda args: {"model": "fixture", "effort": "low"})
    monkeypatch.setenv("AX_LLM", "codex")
    visits = [{"uuid": str(i), "방문": str(i), "연령대": "가", "성별": "갑"} for i in range(2)]
    monkeypatch.setattr(cmd, "make_plan", lambda *args: (SimpleNamespace(visits=visits, line="제품"), cmd.method.BASELINE))
    monkeypatch.setattr(cmd.method, "prompts", lambda plan, v, cond: ("같은 지침", v["uuid"], []))
    calls = Counter()

    async def ask(plan, visit, cond, model, measured):
        calls[visit["uuid"]] += 1
        return {"product": "가물"}, ""

    monkeypatch.setattr(cmd.runner, "_ask", ask)
    asyncio.run(cmd.main(args))
    assert calls == {"0": 2, "1": 2}
    first = (tmp_path / "test.json").read_text()
    asyncio.run(cmd.main(args))
    assert calls == {"0": 2, "1": 2} and (tmp_path / "test.json").read_text() == first
    args.version = "test2"
    asyncio.run(cmd.main(args))
    assert calls == {"0": 4, "1": 4}
    monkeypatch.setenv("AX_LLM", "openai")
    with pytest.raises(ValueError, match="codex"):
        asyncio.run(cmd.main(args))


def test_other_conditions_reuse_only_identical_inputs_and_recover_missing_visits(command, tmp_path, monkeypatch):
    cmd = command
    visits = [{"uuid": str(i), "방문": str(i), "연령대": "가", "성별": "갑"} for i in range(2)]
    plan = SimpleNamespace(visits=visits, line="물")
    monkeypatch.setattr(cmd, "make_plan", lambda *args: (plan, cmd.method.CONCEPT))
    monkeypatch.setattr(cmd.method, "prompts", lambda plan, v, cond: ("지침", v["uuid"], []))
    monkeypatch.setattr(cmd.shelf_items, "concept_prompt", lambda *args: "가격 1000원")
    attempts = Counter()

    async def ask(plan, visit, cond, model, measured):
        key = visit["uuid"]
        attempts[key] += 1
        if key == "0" and attempts[key] == 1:
            return None, "LLMTimeout"
        return {"product": "물"}, ""

    monkeypatch.setattr(cmd.runner, "_ask", ask)
    config = {"model": "fixture", "effort": "low", "method": 1}
    with cmd.records(tmp_path / "one", config) as db:
        rows = asyncio.run(cmd.collect(db, "price-1600", 2, 1, 2))
        assert len(rows["0"]["history"]) == 1 and attempts == {"0": 2, "1": 1}
    with cmd.records(tmp_path / "two", config) as db:
        rows = asyncio.run(cmd.collect(db, "price-1600", 2, 1, 2))
        assert all(r["reused_from"] == "one" for r in rows.values())
        assert attempts == {"0": 2, "1": 1}
        monkeypatch.setattr(cmd.shelf_items, "concept_prompt", lambda *args: "가격 2000원")
        with pytest.raises(ValueError, match="바뀌었습니다"):
            asyncio.run(cmd.collect(db, "price-1600", 2, 1, 2))


def test_cost_unions_overlaps_and_separates_unknown_usage(command):
    rows = [{"product": "물", "calls": 1, "usd": .02, "start": 1., "end": 7.},
            {"product": "차", "calls": 2, "usd": None, "start": 5., "end": 8.},
            {"product": None, "calls": 1, "usd": None, "start": 12., "end": 13.}]
    result = command.cost(rows)
    assert result["calls"] == 4 and result["elapsed_s"] == 8
    assert result["est_cost_usd"] is None and result["known_cost_usd"] == .02
    assert result["completed_est_cost_usd"] == .04 and result["unpriced_answers"] == 1


def test_partial_cost_sample_extends_the_same_plan_without_reasking(command, tmp_path, monkeypatch):
    visits = [{"uuid": str(i), "방문": str(i), "연령대": "가", "성별": "갑"} for i in range(3)]
    plan = SimpleNamespace(visits=visits, line="제품")
    monkeypatch.setattr(command.method, "prompts", lambda p, v, c: ("지침", v["uuid"], []))
    calls = []

    async def ask(p, v, condition, model, measured):
        calls.append(v["방문"])
        return {"product": "물"}, ""

    monkeypatch.setattr(command.runner, "_ask", ask)
    with command.records(tmp_path / "staged", {}) as db:
        for limit in (1, 3, 1):
            batch = asyncio.run(command.collect(db, "dev-cost", 3, 1, 1, visit_limit=limit,
                                                prepared_plan=(plan, command.method.BASELINE)))
            assert len(batch) == limit
    assert calls == ["0", "1", "2"]


def test_table_benchmark_sends_product_facts_and_free_text_without_need_codes(command, tmp_path, monkeypatch):
    from compare_tables_only import table_inputs
    from llm.fake import FakeLLM

    visit = {"방문": "V1", "uuid": "손님1", "연령대": "가", "성별": "갑"}
    plan = SimpleNamespace(visits=[visit], plain={"display": {"견본": "견본 차"}}, line="새 상품")
    order = [{"상품명": "견본", "종류": "차", "용량(ml)": "300", "당": "무가당"}]
    original = {"손님": {"직업": "학생"}, "평소_습관": {"선호": "차"}, "오늘_상황": {"월": 6, "월평균_기온": 21,
                "상황": "배정 상황"}, "평소_욕구": {"B01": 2}, "상황별_욕구_변화": {"B01": 1}, "비구매_번호": 0,
                "욕구별_상품_번호": {"B01": {"잘 채움": [1]}}, "매대": [{"번호": 1, "이름": "견본 차", "가격_원": 1000}]}
    monkeypatch.setattr(command.method, "prompts", lambda *args: ("B01", json.dumps(original), order))
    condition = command.method.BASELINE
    inputs = table_inputs(plan, condition)

    def answer(system, user, schema):
        payload = json.loads(user)
        assert "B01" not in system + user and "배정 상황" not in user
        assert set(payload) == {"손님", "평소_습관", "방문", "비구매_번호", "매대"}
        assert payload["매대"][0]["당"] == "무가당"
        assert set(schema["properties"]) == {"choice_number", "reason_sentence"}
        return {"choice_number": 1, "reason_sentence": "차를 마시고 싶어요."}

    monkeypatch.setattr(command.runner, "get_llm", lambda: FakeLLM({"shopper": answer}))
    with command.records(tmp_path / "table", {}) as db:
        rows = asyncio.run(command.collect(db, "dev-first", 1, 1, 1, prepared_plan=(plan, condition),
                                           prepared_inputs=inputs))
    assert rows["V1"]["product"] == "견본" and rows["V1"]["needs"] == []


def test_products_only_uses_no_relationship_files_or_customer_fields(command, monkeypatch):
    from compare_products_only import product_inputs

    files = {"shelf_products.csv": [{"매대": "음료", "상품명": "견본 차", "가격(원)": "900", "행사": "행사 없음",
                                    "묶음 수량": "1", "종류": "차", "사람": "숨은 손님"}],
             "shelf_display_names.csv": [{"상품명": "견본 차", "손님이 보는 이름": "견본 차"}]}
    catalog = command.catalog
    catalog.public.cache_clear()
    monkeypatch.setattr(catalog, "_read_public", files.__getitem__)
    try:
        products = catalog.public(with_fulfills=False)
        assert not products[0].fulfills
        system, text, order, schema = product_inputs(products, ["T001"])["T001"]
        assert json.loads(text) == [{"번호": 1, "이름": "견본 차", "가격_원": 900, "종류": "차"}]
        assert set(schema["properties"]) == {"choice_number", "reason_sentence"}
        assert "숨은 손님" not in system + text and order[0]["상품명"] == "견본 차"
    finally:
        catalog.public.cache_clear()


def test_check_summary_counts_multiple_reasons_per_nonbuyer(command):
    def row(picked, barriers):
        return {"selected": picked, "product": "가" if picked else "나", "barriers": barriers,
                "start": 0, "end": 1, "calls": 1, "usd": .01}
    rows = [row(False, ["가격", "용기"]), row(False, ["가격"]), row(True, [])]
    item = command.benchmark_summary("check-regular", rows)
    assert item["n"] == 3 and item["picked"] == 1 and item["barrier_responses"] == 2
    assert item["barriers"] == {"가격": 2, "용기": 1}


def test_category_fit_distinguishes_all_purchases_and_matched_products():
    choices = [{"age": "가", "sex": "갑", "product": k} for k in ["a", "a", "b", "c", "사지 않음"]]
    products = {"a": ("s1", "과일", True), "b": ("s2", "차", False), "c": (None, "물", False)}
    sales = [{"sku": "s1", "kind": "과일", "units": 70, "promoted": True},
             {"sku": "s2", "kind": "차", "units": 30, "promoted": False}]
    fit = rel.category_fit(choices, {("가", "갑"): 1}, products, sales)
    assert fit["promoted_picks"] == 2 and fit["bought"] == 4 and fit["matched_picks"] == 3
    assert fit["kinds_all"]["과일"] == pytest.approx(.5)
    assert fit["kinds_matched"]["과일"] == pytest.approx(2/3)
    assert fit["pos_matched"]["과일"] == fit["promoted_units_share"] == .7
    assert "dev_kind_adjusted" not in fit
    dev = rel.category_fit(choices, {("가", "갑"): 1}, products, sales, dev=True)
    assert dev["dev_kind_adjusted"]["gap"] == pytest.approx(0)


@pytest.mark.parametrize("backend", ["codex", "openai"])
def test_final_gpt_default_and_reopening_earlier_shopper_rounds(command, monkeypatch, backend):
    monkeypatch.setenv("AX_LLM", backend)
    monkeypatch.delenv("AX_SHOPPER_ROUND", raising=False)
    assert command.method.prompt_round() == 11
    assert command.runner._saved_round({"participants": [{"visit": "T001"}]}) == 4
    assert command.runner._saved_round({"participants": [{"comparison_limit": 2}]}) == 10
    monkeypatch.setattr(command.method, "shelf_v", lambda number: f"shelf-{number}")
    assert command.runner._saved_round({"participants": [{"visit_month": 8}], "shelf_v": "shelf-7"}) == 7
    assert command.runner._saved_round({"shopper_round": 9}) == 9
    assert command.runner._saved_round({"shopper_round": 11}) == 11


def test_calendar_round_preserves_claude_and_pairs_months(command, monkeypatch):
    m = command.method
    monkeypatch.setenv("AX_LLM", "cli")
    monkeypatch.setenv("AX_SHOPPER_ROUND", "6")
    assert m.prompt_round() == 4
    monkeypatch.setenv("AX_LLM", "codex")
    assert m.prompt_round() == 6
    monkeypatch.setattr(m, "known_concept", lambda line: {"season": "11~2월 한정", "launch": "2030-11"})
    months = m.sale_months("견본")
    assert months == [11, 12, 1, 2] and m.sale_months("견본", annual=True) == list(range(1, 13))
    monkeypatch.setattr(m, "known_concept", lambda _: None)
    assert m.sale_months("임의 신제품", launch="2030-10") == [10, 11, 12, *range(1, 10)]
    assert m.sale_months("임의 신제품", season="5~9월 한정", launch="2030-03") == list(range(5, 10))
    assert m.sale_months("임의 신제품", season="7월 한정") == [7]
    assert m.sale_months("임의 신제품", launch="2030-10-03")[0] == 10
    assert m.sale_months("임의 신제품") == list(range(1, 13))
    assert m.assign_month("손님-1", months, {12: 700}) == 12
    assert m.assign_month("손님-1", months, {}) in months
    visit = {"방문": "T001", "uuid": "손님-1", "연령대": "가", "성별": "갑",
             "상황 번호": "D1", "visit_month": 12, "temp_c": -1.5}
    stored, = command.runner._snapshot(SimpleNamespace(visits=[visit]))
    assert stored["visit_month"] == 12 and stored["temp_c"] == -1.5
    assert m.baseline_occasion(visit) != m.baseline_occasion({**visit, "visit_month": 1})
    assert m.baseline_occasion({"상황 번호": "D1"}) == "D1"


def test_seasonality_compares_observed_months_and_summer_winter():
    choices = [{"age": "가", "sex": "갑", "product": p, "visit_month": m}
               for p, m in [("a", 7), ("a", 7), ("a", 1), ("b", 1)]]
    products = {"a": ("s1", "탄산", False), "b": ("s2", "차", False)}
    sales = [{"sku": sku, "month": m, "kind": kind, "units": n, "promoted": False}
             for sku, kind, m, n in [("s1", "탄산", 7, 8), ("s2", "차", 7, 2),
                                      ("s1", "탄산", 1, 3), ("s2", "차", 1, 7)]]
    shape = rel.category_fit(choices, {("가", "갑"): 1}, products, sales)["seasonality"]
    assert shape["months_compared"] == 2 and shape["rho"] == pytest.approx(1)
    assert shape["virtual_summer_minus_winter"] == .5
    assert shape["pos_summer_minus_winter"] == pytest.approx(.5)
    assert shape["same_direction"]


def test_neutral_concept_uses_same_valid_pairs_for_price_and_promotion(command, tmp_path, monkeypatch):
    monkeypatch.setattr(command, "OUT", tmp_path)
    cases = dict(zip(command.NEUTRAL_CASES, ([True, False, True], [False, False, True], [True, True, None])))

    async def collect(db, case, people, per_cell, workers):
        assert people == 100
        return {i: {"selected": x, "product": "가" if x is not None else None, "start": 0, "end": 1,
                    "calls": 1, "usd": 0.1} for i, x in enumerate(cases[case])}

    monkeypatch.setattr(command, "collect", collect)
    folder = tmp_path / ".work" / "v9"
    config = {"model": "견본"}
    asyncio.run(command.neutral_direction(SimpleNamespace(per_cell=70, workers=2), config, folder))
    stored = json.loads((folder / "neutral_direction.json").read_text())
    assert stored["n"] == 2 and stored["price"]["gain"] == stored["promo"]["gain"] == 1
    metric = {"id": "retest", "detail": {"reference_digest": "fixed", "last_call_epoch": 5}}
    board_path = tmp_path / "v9.json"
    command.save_score(board_path, {**config, "effort": None}, metric)
    assert json.loads(board_path.read_text())["neutral_direction"] == stored


def test_brand_transfer_distinguishes_familiar_brand_and_prior_own_choice(command):
    first = {k: {"product": v} for k, v in enumerate(["우리", "우리", "다른", "다른", None])}
    brand = {k: {"selected": v} for k, v in enumerate([True, False, True, False, True])}
    result = command.brand_transfers(first, brand, {1, 2, 4}, {"우리"})
    assert result["n"] == 4 and result["new_picks"] == 2
    assert result["habit_same_brand"] == 2 and result["habit_same_brand_picked"] == 1
    assert result["from_own"] == 1 and result["from_own_share_of_new"] == result["new_share_of_own_before"] == .5


def test_purchase_habits_use_training_sales_and_only_matching_survey_cells():
    from calibrate import habits

    shelf = [("a", "a행", "가 탄산", "탄산"), ("b", "b행", "나 탄산", "탄산"), ("c", "c행", "다 커피", "커피")]
    sales = [{"month": f"{year}-{month:02}", "sku": sku, "units": units, "brand": brand, "channel": "편의점"}
             for year in [2023, 2024] for month in range(1, 13)
             for sku, units, brand in [("a", 3, "가"), ("b", 1, "나"), ("c", 2, "다")]]
    respondents = [{"age_band": "19~29세", "gender": "여성", "weight": .75,
                    "buy_soda": 4, "buy_coffee": 0, "buy_juice": 1}]
    ref = habits.aggregate(sales, respondents, shelf)
    assert [w for _, w in ref.products["탄산"]] == [36, 12]
    assert ref.frequencies["19-29", "여자", "탄산"] == [(4, .75)]
    changed = [{**r, "units": 2000} if r["month"].startswith("2024") else r for r in sales]
    assert habits.aggregate(changed, respondents, shelf).signature == ref.signature
    incomplete = habits.aggregate(sales[:6], respondents, shelf)
    assert not incomplete.products and incomplete.frequencies == ref.frequencies
    favorites = ["가당 탄산음료", "인스턴트·캔 커피", "탄산수"]
    choice = habits.assign(ref, "합성-손님", "19-29", "여자", favorites, 1)
    assert choice["has_frequency"] and len(choice["products"]) == 1
    assert choice["products"][0] in {"a행", "b행"} and choice["brands"][0] in {"가", "나"}
    assert "탄산음료 4회" in choice["lines"][1] and "커피음료 0회" in choice["lines"][1]
    assert habits.assign(ref, "합성-손님", "19-29", "여자", favorites, 0) == {}
    older = habits.assign(ref, "합성-손님", "70+", "여자", favorites, 1)
    assert not older["has_frequency"] and len(older["products"]) == 2
    assert habits.assign(ref, "합성-손님", "70+", "여자", ["흰우유", "탄산수"], 1) == {}


def test_dev_study_runs_guards_within_total_worker_limit(command, tmp_path, monkeypatch):
    monkeypatch.setattr(command, "OUT", tmp_path)
    monkeypatch.setattr(command, "settings", lambda _: {})
    monkeypatch.setattr(command.method, "prompt_round", lambda: 10)
    monkeypatch.setattr(command, "dev_report", lambda *_: {})
    monkeypatch.setattr(command, "make_plan", lambda *_: (SimpleNamespace(visits=[], plain={}), None))
    monkeypatch.setattr(command.catalog, "current", lambda: [])
    monkeypatch.setattr(command, "paired_neutral", lambda batches: {"arms": len(batches)})
    monkeypatch.setenv("AX_LLM", "codex")
    active, peak, cases = 0, 0, []

    async def collect(db, case, people, per_cell, workers, *, recover):
        nonlocal active, peak
        cases.append(case)
        active += workers
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= workers
        return {"one": {"product": "물", "selected": False, "start": 100., "end": 102.,
                        "calls": 1, "usd": .01}}

    monkeypatch.setattr(command, "collect", collect)
    args = SimpleNamespace(dev_study="trial", dev_claude=False, dev_guard=True, per_cell=70, workers=6)
    asyncio.run(command.dev_study(args))
    assert peak == 6
    assert set(cases) == {"dev-first", "dev-repeat", "dev-brand", *("dev-" + c for c in command.NEUTRAL_CASES)}
    report = json.loads((tmp_path / ".dev" / "trial" / "report.json").read_text())
    assert report["neutral_direction"]["arms"] == 3
    assert report["total_usage"]["calls"] == 6
    assert report["total_usage"]["elapsed_s"] == 2
    assert report["total_usage"]["est_cost_usd"] == pytest.approx(.06)


def test_habit_variants_change_kind_or_presentation_separately():
    from calibrate import habits

    ref = habits.Reference(
        {k: [((k, k + " 제품", k + " 브랜드"), 5)] for k in habits.FIELDS},
        {("가", "갑", k): [(n, 1)] for k, n in (("탄산", 8), ("커피", 2), ("주스", 0))},
        "fixture",
    )
    choices = Counter()
    for i in range(1000):
        args = (ref, str(i), "가", "갑", ["인스턴트·캔 커피"], 1.)
        original = habits.assign(*args)
        weighted = habits.assign(*args, variant="frequency-kinds")
        assert weighted["lines"][1] == original["lines"][1]
        assert len(weighted["products"]) == len(original["products"]) == 1
        choices.update(weighted["products"])
    assert 750 <= choices["탄산"] <= 850 and choices["주스"] == 0
    args = (ref, "합성", "가", "갑", ["인스턴트·캔 커피", "가당 탄산음료"], 1.)
    original = habits.assign(*args)
    # 두 종류가 유지되면 표시 순서와 같은 종류의 SKU까지 대조군과 동일하다.
    assert habits.assign(*args, variant="frequency-kinds") == original
    paired = habits.assign(*args, variant="paired-lines")
    assert paired["products"] == original["products"] and paired["brands"] == original["brands"]
    assert paired["lines"] == ["탄산음료는 한 달에 모두 8회 정도 삽니다. 평소 자주 사는 탄산음료는 탄산 제품입니다.",
                               "커피음료는 한 달에 모두 2회 정도 삽니다. 평소 자주 사는 커피음료는 커피 제품입니다.",
                               "주스는 한 달에 모두 0회 정도 삽니다."]
