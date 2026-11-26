"""판매·자산 정제 규칙을 지어낸 통합 문서와 원본 집계로 확인한다."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from onsite.sales import build_sales
from onsite.schema import CSV_COLUMNS


SHEET_HEADERS = {
    "1_POS_판매": (
        "기준월", "권역", "판매채널", "제품코드", "제품명", "브랜드", "카테고리",
        "판매수량", "판매금액", "행사구분", "수량단위",
    ),
    "2_출고_sell-in": ("기준월", "판매채널", "제품코드", "제품명", "출고수량"),
    "3_권역별기온": ("기준월", "권역", "평균기온(℃)"),
    "4_제품자산DB": (
        "SKU코드", "제품명", "브랜드", "카테고리", "용기·용량", "출시일",
        "폐지(중단)일", "상태", "컨셉요약", "최고연매출(억원)", "단종·중단사유", "비고",
    ),
    "5_유통채널_인프라": (
        "채널", "점포·기기수(가상)", "냉동 음료 진열 가능 점포율", "냉장 쇼케이스 보유율", "비고",
    ),
    "6_과거컨셉테스트_실적": (
        "제품", "컨셉테스트연도", "카테고리", "컨셉테스트_구매의향TOP2",
        "출시6개월_취급점포율", "출시12개월_실제구매경험률", "비고", "환산계수(실제/의향)",
    ),
}
TABLE_NAMES = {"pos_clean", "sellin", "temperature", "assets", "infra", "past_tests"}


def _sale(
    sku="S-001", *, month="2024-01", region="가권역", channel="가판매처", name="솔잎 음료",
    brand="솔잎", units=8, amount=10900, unit="EA",
):
    return month, region, channel, sku, name, brand, "기타음료", units, amount, "행사없음", unit


def _asset(
    sku="S-001", *, name="솔잎 음료", launched=None, ended=None, status="운영",
    reason=None, note=None,
):
    return sku, name, "솔잎", "기타음료", "캔", launched, ended, status, "식물향", None, reason, note


def _build(tmp_path, *, sales=(), assets=(), other=None):
    workbook = Workbook()
    workbook.active.title = "안내"
    rows = {"1_POS_판매": sales, "4_제품자산DB": assets, **(other or {})}
    for sheet, headers in SHEET_HEADERS.items():
        worksheet = workbook.create_sheet(sheet)
        worksheet.append(headers)
        for row in rows.get(sheet, ()):
            worksheet.append(row)
    path = tmp_path / "sales.xlsx"
    workbook.save(path)
    tables, report = build_sales(path)
    return tables, {entry["rule"]: entry for entry in report}


def test_box_conversion_changes_only_quantity(tmp_path):
    tables, report = _build(tmp_path, sales=[
        _sale("001", units=3, amount=700, unit="BOX(24)"),
        _sale("002", brand="경쟁사토끼", units=3, amount=900),
        _sale("003", brand="편의점PB토끼"),
    ])
    pos = tables["pos_clean"]
    assert pos["sku"].tolist() == ["001", "002", "003"]
    assert pos["units"].tolist() == [72, 3, 8]
    assert pos["amount"].tolist() == [700, 900, 10900]
    assert pos["is_own"].tolist() == [True, False, False]
    assert report["box_24"]["flagged"] == 1
    assert report["box_24"]["removed"] == 0


def test_negative_units_rule_keeps_zero_and_uses_quantity_only(tmp_path):
    tables, report = _build(tmp_path, sales=[
        _sale("A", units=-1),
        _sale("B", units=0),
        _sale("C", units=3, amount=-12),
    ])
    assert tables["pos_clean"][["sku", "units"]].values.tolist() == [["B", 0], ["C", 3]]
    assert report["negative_units"]["removed"] == 1


def test_duplicate_key_uses_all_four_fields_and_keeps_first_valid_row(tmp_path):
    tables, report = _build(tmp_path, sales=[
        _sale(units=7),
        _sale(name="포장 변경", units=16),
        _sale(month="2024-02"),
        _sale(region="나권역"),
        _sale(channel="나판매처"),
        _sale("B"),
    ])
    assert tables["pos_clean"]["units"].tolist() == [7, 8, 8, 8, 8]
    assert report["duplicate_key"]["removed"] == 1


def test_test_products_and_overlapping_rules_have_distinct_raw_and_actual_counts(tmp_path):
    tables, report = _build(tmp_path, sales=[
        _sale("A", name="테스트 상품(시안)", units=-5, unit="BOX(24)"),
        _sale("A", units=2, unit="BOX(24)"),
        _sale("B", units=-8),
        _sale("B", units=6),
        _sale("B", units=7, unit="BOX(24)"),
        _sale("C", name="테스트상품 임시"),
        _sale("D", name="향 테스트 음료"),
    ])
    assert tables["pos_clean"][["sku", "units"]].values.tolist() == [
        ["A", 48], ["B", 6], ["D", 8],
    ]
    assert report["test_product"]["removed"] == 2
    assert report["negative_units"]["removed"] == 1
    assert "원본은 2행" in report["negative_units"]["detail"]
    assert report["duplicate_key"]["removed"] == 1
    assert "첫 행을 빼면 3행" in report["duplicate_key"]["detail"]
    assert "겹친 행 중 2행" in report["duplicate_key"]["detail"]
    assert report["box_24"]["flagged"] == 1
    assert "원본 3행" in report["box_24"]["detail"]


def test_after_end_uses_only_valid_discontinued_assets_and_excludes_end_month(tmp_path):
    tables, report = _build(tmp_path, sales=[
        _sale("A", month="2024-11"),
        _sale("A", month=date(2024, 12, 1)),
        _sale("A", month="2025-01"),
        _sale("B", month="2025-01"),
        _sale("C", month="2025-01"),
        _sale("D", month="2025-01"),
        _sale("E", month="2025-01"),
    ], assets=[
        _asset("A", status="단종", ended="2024-04-08"),
        _asset("A", name="변경한 솔잎 음료", status="단종", ended=date(2024, 12, 1)),
        _asset("A", name="다른 솔잎 음료 안", status="개발중단", ended="2025-02-08"),
        _asset("B", status="개발중단", ended="2024-04-08"),
        _asset("C", status="단종", launched="2025-01-01", ended="2024-04-08"),
        _asset("D", status="아이디어", ended="2024-04-08"),
    ])
    assert tables["pos_clean"]["month"].iloc[1] == "2024-12"
    assert tables["pos_clean"]["after_end"].tolist() == [False, False, True, False, False, False, False]
    assert report["after_end"]["flagged"] == 1
    assert "같은 달의 1행" in report["after_end"]["detail"]


def test_asset_ids_and_duplicate_flags_survive_source_reordering(tmp_path):
    rows = [
        _asset("0001", name="소나무 음료", status="단종"),
        _asset("0001", name="소나무 음료", status="개발중단"),
        _asset("0001-1", name="솔방울 음료"),
    ]
    first, report = _build(tmp_path, assets=rows)
    second, _ = _build(tmp_path, assets=rows[::-1])
    assets = first["assets"]
    assert assets["asset_id"].is_unique
    assert set(assets["asset_id"]) == {"0001-1", "0001-2", "0001-1-1"}
    for name in ("flags", "asset_id"):
        assert assets.set_index("status")[name].to_dict() == second["assets"].set_index("status")[name].to_dict()
    assert assets["flags"].str.contains("duplicate_sku").tolist() == [True, True, False]
    assert report["duplicate_sku"]["flagged"] == 2


def test_asset_dates_and_reasons_are_preserved_when_flagged(tmp_path):
    tables, report = _build(tmp_path, assets=[
        _asset("A", status="단종", launched=date(2024, 6, 1), ended="2024-04-08"),
        _asset("B", status="개발중단", ended="2024-05-09", reason="개발 일정 변경"),
        _asset("C", status="운영", launched="2024-05-09"),
        _asset("D", status="단종", launched="2024-05-09", ended="2024-05-09", reason="NA"),
    ])
    assets = tables["assets"]
    assert assets["launched"].tolist() == ["2024-06-01", "", "2024-05-09", "2024-05-09"]
    assert assets["ended"].tolist() == ["2024-04-08", "2024-05-09", "", "2024-05-09"]
    assert assets["reason"].tolist() == ["", "개발 일정 변경", "", "NA"]
    assert assets["flags"].tolist() == ["date_reversed,reason_missing", "", "reason_missing", ""]
    assert report["date_reversed"]["flagged"] == 1
    assert report["reason_missing"]["flagged"] == 2
    assert "중단된 자산은 1행" in report["reason_missing"]["detail"]


def test_six_contract_tables_and_published_input_figures(tmp_path):
    tables, report = _build(tmp_path, other={
        "2_출고_sell-in": [("2024-01", "가판매처", "012", "솔잎 음료", 17)],
        "3_권역별기온": [("2024-01", "가권역", -8.1)],
        "5_유통채널_인프라": [("가판매처", 27, 0.25, 0.75, ""), ("나판매처", None, 0.1, 0.4, "")],
        "6_과거컨셉테스트_실적": [("솔잎 음료", 2015, "기타음료", 0.5, 0.62, 0.1, "", 0.21)],
    })
    assert set(tables) == TABLE_NAMES
    for name, table in tables.items():
        assert tuple(table.columns) == CSV_COLUMNS[name]
    assert tables["sellin"]["sku"].tolist() == ["012"]
    assert tables["sellin"]["units"].tolist() == [17]
    assert tables["temperature"]["temp_c"].tolist() == [-8.1]
    assert tables["infra"]["stores"].iloc[0] == 27
    assert pd.isna(tables["infra"]["stores"].iloc[1])
    assert tables["infra"]["frozen_rate"].tolist() == [0.25, 0.1]
    assert tables["past_tests"]["ratio"].tolist() == [0.21]
    assert len(report) == 8
    for entry in report.values():
        assert set(entry) == {"source", "rule", "label", "removed", "flagged", "detail"}
    json.dumps(report, allow_nan=False)


def test_onsite_sales_source_aggregates():
    source = Path(__file__).resolve().parents[3] / "data" / "raw" / "onsite"
    paths = list(source.glob("3-1_*.xlsx"))
    if not paths:
        pytest.skip("판매 원본이 없어요.")
    assert len(paths) == 1
    tables, report = build_sales(paths[0])
    rules = {entry["rule"]: entry for entry in report}
    assert {name: tuple(table.columns) for name, table in tables.items()} == {
        name: CSV_COLUMNS[name] for name in TABLE_NAMES
    }
    raw = pd.read_excel(paths[0], sheet_name="1_POS_판매")
    key = ["기준월", "권역", "판매채널", "제품코드"]
    test_products = raw["제품명"].str.match(r"테스트\s*상품")
    negative_units = raw["판매수량"] < 0
    eligible = raw.loc[~(test_products | negative_units)]
    expected = eligible.drop_duplicates(key)
    assert len(raw) == 8971
    assert raw["수량단위"].eq("BOX(24)").sum() == 162
    assert raw.duplicated(key).sum() == 24
    assert test_products.sum() == rules["test_product"]["removed"] == 7
    assert rules["negative_units"]["removed"] == (negative_units & ~test_products).sum()
    assert rules["duplicate_key"]["removed"] == eligible.duplicated(key).sum()
    assert rules["box_24"]["flagged"] == expected["수량단위"].eq("BOX(24)").sum()
    assert rules["after_end"]["flagged"] == tables["pos_clean"]["after_end"].sum()
    assert len(tables["pos_clean"]) == len(expected) == len(raw) - sum(entry["removed"] for entry in report)
    assert len(tables["sellin"]) == 1504
    assert len(tables["temperature"]) == 144
    assert len(tables["assets"]) == tables["assets"]["asset_id"].nunique() == 21
    assert len(tables["infra"]) == len(tables["past_tests"]) == 5
