"""가상 매출(calibrate/sales.py): 지어낸 작은 표로 기준, 계절, 점포율, 순증, 범위를 확인한다. 모델을 부르지 않는다."""

import csv
import json

import pytest

import onsite
from calibrate import sales
from onsite.schema import CSV_COLUMNS, FILENAMES, JSON_NAMES
from shelftest import catalog, method, result, runner, store

MONTHS = [f"2025-{m:02}" for m in range(1, 13)]
SUMMER = {6, 7, 8}
MODEL = "시험모델"


def write(root, table, rows):
    with (root / FILENAMES[table]).open("w", encoding="utf-8", newline="") as stream:
        w = csv.DictWriter(stream, fieldnames=CSV_COLUMNS[table])
        w.writeheader()
        w.writerows(rows)


def sale(sku, name, category, own, units, price, month, **kw):
    return {"month": month, "region": "견본 권역", "channel": "편의점", "sku": sku, "name": name, "brand": "견본" + sku,
            "category": category, "units": units, "amount": units * price, "promo": "없음",
            "is_own": str(own).lower(), "after_end": "false", **kw}


def pos_rows():
    rows = []
    for m in MONTHS:
        lift = 3 if int(m[5:]) in SUMMER else 1  # 여름 세 달이 3배, 나머지 1배 → 평균 1.5
        rows.append(sale("T-1", "견본소다 300ml 캔", "탄산", True, 1000 * lift, 1000, m))
        rows.append(sale("T-2", "견본콜라 300ml 캔", "탄산", False, 3000 * lift, 1500, m))
        rows.append(sale("T-3", "견본커피 300ml 캔", "캔커피", False, 500, 1200, m))
        rows.append(sale("T-1", "견본소다 300ml 캔", "탄산", True, 99999, 1000, m, channel="대형마트"))
    rows.append(sale("T-2", "견본콜라 300ml 캔", "탄산", False, 77777, 1500, "2025-07", after_end="true"))
    return rows


@pytest.fixture
def data(monkeypatch, tmp_path):
    root = tmp_path / "onsite"
    root.mkdir()
    for name in JSON_NAMES:
        (root / FILENAMES[name]).write_text("[]", encoding="utf-8")
    for name in CSV_COLUMNS:
        write(root, name, [])
    write(root, "pos_clean", pos_rows())
    write(root, "infra", [{"channel": "편의점", "stores": 100, "frozen_rate": 0.25, "chilled_rate": 0.9}])
    monkeypatch.setenv("AX_ONSITE_DIR", str(root))
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(store, "BASE_DIR", tmp_path / "baselines")
    monkeypatch.setattr(runner, "shopper_model", lambda: MODEL)
    population(root)
    return root


def key(sku):
    return next(p.key for p in catalog.current() if p.sku == sku)


def shown(sku):
    return next(p.name for p in catalog.current() if p.sku == sku)


def baseline(counts, n=100, model=MODEL):
    picks = [key(s) for s, k in counts.items() for _ in range(k)]
    picks += [method.NO_PURCHASE] * (n - len(picks))
    for i, product in enumerate(picks):
        store.append_baseline(method.shelf_v(), model, {"uuid": f"u{i}", "occasion": "o", "product": product})


def population(root):
    write(root, "population", [
        {"dimension": "age_gender", "age_band": a, "gender": g, "share": 0.1 if g == "여성" else 0.15}
        for a in ("19~29세", "30~39세", "40~49세", "50~59세") for g in ("여성", "남성")])


def concept(**kw):
    return {"id": "c1", "name": "견본 신제품 소다", "price": 2000, "season": "6~8월 한정", "launch": "2027-06", **kw}


def res(picked=10, n=100, own=(), pending=0):
    return {"n": n, "picked": picked, "from": {"own": [{"name": a, "count": b} for a, b in own], "rival": [],
                                               "none": 0, "pending": pending}}


def test_units_season_and_amount(data):
    baseline({"T-1": 2, "T-2": 6, "T-3": 4})
    v = sales.estimate(concept(), res())
    # 월평균 (1000 + 3000) × 1.5 = 6000개, 선택 8%p → 1%p에 750개. 10% × 750 × 여름 지수 2 = 15000개
    assert v["basis"] == {"per_point_units": 750.0, "per_point_units_high": 750.0, "category": "탄산", "store_rate": 1.0,
                          "target_share": 1.0, "products": 2}
    assert [m["month"] for m in v["monthly"]] == ["2027-06", "2027-07", "2027-08"]
    assert all(m["units"][1] == 15000 and m["amount"][1] == 30_000_000 for m in v["monthly"])
    assert v["season_total"]["units"][1] == 45000 and v["season_total"]["amount"][1] == 90_000_000
    low, mid, high = v["season_total"]["amount"]
    assert 0 < low < mid < high
    assert v["net"] == {"amount": v["season_total"]["amount"], "lost_own": []} and v["backtest"] is None
    text = " ".join(v["assumptions"])
    assert "행사" in text and "시장점유율" not in text and "편의점" in text
    assert all(a.endswith("요.") or a.endswith("세요.") or a.endswith(").") for a in v["assumptions"])


def test_price_and_rate_move_the_amount(data):
    baseline({"T-1": 2, "T-2": 6})
    one = sales.estimate(concept(price="2,000원"), res())["season_total"]
    assert sales.estimate(concept(price=3000), res())["season_total"]["amount"][1] == one["amount"][1] * 1.5
    assert sales.estimate(concept(), res(picked=20))["season_total"]["units"][1] == one["units"][1] * 2
    narrow = sales.estimate(concept(), res(picked=100, n=1000))["season_total"]
    assert narrow["units"][1] == one["units"][1] and narrow["units"][0] > one["units"][0] and narrow["units"][2] < one["units"][2]


def test_net_subtracts_own_at_pos_price(data):
    baseline({"T-1": 2, "T-2": 6})
    v = sales.estimate(concept(), res(own=[(shown("T-1"), 4)], pending=2))
    total = v["season_total"]["amount"][1]
    # 확인한 8명 가운데 4명이 옮겨 옴: 45000 × 0.5 × 1000원
    assert v["net"]["lost_own"] == [{"sku": "T-1", "name": shown("T-1"), "amount": 22_500_000}]
    assert v["net"]["amount"][1] == total - 22_500_000
    assert any("2명은" in a for a in v["assumptions"])
    waiting = sales.estimate(concept(), res(pending=10))
    assert waiting["net"] is None  # 모르면 값을 만들지 않는다
    assert any("순증 가상 매출은 내지 않았어요" in a for a in waiting["assumptions"])


def test_unmatched_own_product_is_not_invented(data):
    baseline({"T-1": 2, "T-2": 6})
    v = sales.estimate(concept(), res(own=[("매대에 없는 제품", 3)]))
    assert v["net"]["lost_own"] == [] and any("매대에 없는 제품" in a and "빼지 못했" in a for a in v["assumptions"])


def test_shelf_products_outside_pos_are_an_assumption_not_the_range(data):
    baseline({"T-1": 2, "T-2": 6})
    before = sales.estimate(concept(), res())
    other = next(p.key for p in catalog.current() if p.kind == "탄산" and not p.sku)
    for i in range(8):  # 판매 자료에 없는 탄산도 8명이 고르면 같은 종류의 선택률이 두 배
        store.append_baseline(method.shelf_v(), MODEL, {"uuid": f"v{i}", "occasion": "o", "product": other})
    v = sales.estimate(concept(), res())
    assert v["basis"]["per_point_units"] == 405.0 and v["basis"]["per_point_units_high"] == 810.0  # 6000 ÷ (16 또는 8 / 108명)
    assert v["season_total"]["units"][1] == 10 * 405 * 6  # 중앙은 낮은 쪽 기준
    # 높은 값도 같은 기준이다: 범위는 선택률의 오차만
    assert v["season_total"]["units"][2] == pytest.approx(before["season_total"]["units"][2] * 405 / 750, abs=1)
    assert any("판매를 몰라 보수적으로" in x for x in v["assumptions"])
    assert "범위에는 선택률의 오차만 넣었어요." in v["assumptions"]


def test_range_is_wilson_times_the_two_bases(data):
    from shelftest.result import wilson

    baseline({"T-1": 2, "T-2": 6})
    low, high = wilson(10, 100)
    units = sales.estimate(concept(), res())["season_total"]["units"]
    assert units[0] == pytest.approx(low * 750 * 6, rel=0.02) and units[2] == pytest.approx(high * 750 * 6, rel=0.02)


def test_counts_only_the_target_share(data):
    baseline({"T-1": 2, "T-2": 6})
    whole = sales.estimate(concept(), res())["season_total"]["units"][1]
    for target, share in (({"age": "19-29", "sex": None}, 0.25), ({"age": "40-49", "sex": "남자"}, 0.15),
                          ({"age": None, "sex": "여자"}, 0.4)):
        v = sales.estimate(concept(), {**res(), "target": target})
        assert v["basis"]["target_share"] == share and v["season_total"]["units"][1] == round(whole * share)
        assert any(a.startswith("타깃이 사는 몫만 셌어요") and "타깃 밖의 구매는 넣지 않았어요" in a for a in v["assumptions"])
    assert sales.estimate(concept(), {**res(), "target": {"age": "60-69", "sex": None}}) is None  # 구성비에 없는 타깃
    write(data, "population", [])
    assert sales.estimate(concept(), {**res(), "target": {"age": "19-29", "sex": None}}) is None


def test_zero_picks_give_zero_middle_and_an_upper_bound(data):
    baseline({"T-1": 2, "T-2": 6})
    v = sales.estimate(concept(), res(picked=0))
    low, mid, high = v["season_total"]["units"]
    assert low == mid == 0 < high
    assert any("0" in a and "가운데" in a for a in v["assumptions"])


def test_store_rate_follows_storage(data):
    baseline({"T-1": 2, "T-2": 6})
    room = sales.estimate(concept(storage="상온"), res())
    frozen = sales.estimate(concept(storage="냉동"), res())
    assert frozen["basis"]["store_rate"] == 0.25
    assert frozen["season_total"]["units"][1] == room["season_total"]["units"][1] / 4
    write(data, "infra", [])
    assert sales.estimate(concept(storage="냉동"), res()) is None  # 점포율을 지어내지 않는다


def test_year_round_index_averages_to_one(data):
    baseline({"T-1": 2, "T-2": 6})
    v = sales.estimate(concept(season=None, launch="2027-11"), res())
    assert len(v["monthly"]) == 12 and v["monthly"][0]["month"] == "2027-11" and v["monthly"][2]["month"] == "2028-01"
    assert v["season_total"]["units"][1] == 10 * 750 * 12


def test_widens_to_all_drinks_when_the_kind_was_never_picked(data):
    baseline({"T-3": 5})
    v = sales.estimate(concept(), res())
    assert v["basis"]["category"] == sales.ALL_KINDS and v["basis"]["products"] == 3
    assert any("넓혔어요" in a for a in v["assumptions"])


def test_none_without_choices_data_or_price(data, monkeypatch):
    assert sales.estimate(concept(), res()) is None  # 기준 선택이 없다
    baseline({"T-1": 2})
    assert sales.estimate(concept(price=None), res()) is None
    assert sales.estimate(concept(), {}) is None and sales.estimate({}, res()) is None
    assert sales.estimate(concept(), {"n": "?"}) is None
    monkeypatch.setenv("AX_ONSITE_DIR", str(data / "없음"))
    assert not onsite.available() and sales.estimate(concept(), res()) is None


def run(run_id, picks, base_products, **kw):
    meta = {"id": run_id, "status": "done", "chat_id": "chat", "concept_id": "c1", "concept": concept(volume=300),
            "line": "새 제품", "target": {"age": "19-29", "sex": None}, "updated_at": "2026-11-24",
            "shelf_products": result.catalog_snapshot(), **kw}
    store.save_meta(meta)
    for i, base in enumerate(base_products):
        row = {"visit": f"T{i:03}", "uuid": f"u{i}", "occasion": "o"}
        store.append_answer(run_id, {**row, "cond": method.CONCEPT, "product": "새 제품" if i < picks else method.NO_PURCHASE})
        store.append_answer(run_id, {**row, "cond": method.BASELINE, "product": base})
    return meta


def test_uses_the_run_that_made_the_result(data):
    baseline({"T-1": 50})
    half = [key("T-2")] * 4 + [method.NO_PURCHASE] * 96
    run("run-000000000001", 10, half)
    run("run-000000000002", 30, [key("T-2")] * 40 + [method.NO_PURCHASE] * 60)
    c = concept(volume=300)
    assert sales.find_run(c, res())["id"] == "run-000000000001"
    v = sales.estimate(c, res())
    assert v["basis"]["per_point_units"] == 1500.0  # 6000 ÷ 4%p
    assert not any("다른 가상 소비자" in a for a in v["assumptions"]) and v["basis"]["target_share"] == 0.25
    other = sales.estimate(c, {**res(), "run_id": "run-000000000002"})
    assert other["basis"]["per_point_units"] == 150.0


def test_reads_pos_once(data, monkeypatch):
    baseline({"T-1": 2, "T-2": 6})
    sales.estimate(concept(), res())
    real, calls = onsite.load, []
    monkeypatch.setattr(onsite, "load", lambda name: calls.append(name) or real(name))
    sales.estimate(concept(), res())
    assert "pos_clean" not in calls


def test_json_shape(data):
    baseline({"T-1": 2, "T-2": 6})
    v = sales.estimate(concept(), res())
    assert set(v) == {"monthly", "season_total", "net", "assumptions", "basis", "backtest"}
    json.dumps(v, ensure_ascii=False)
