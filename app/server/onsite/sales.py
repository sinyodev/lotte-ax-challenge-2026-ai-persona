"""현장 판매 자료에서 계약에 맞는 표와 정제 내역을 만든다."""

from pathlib import Path

import pandas as pd

from .schema import CSV_COLUMNS


POS_KEY = ["month", "region", "channel", "sku"]
BOX_SIZE = 24
BOX_UNIT = f"BOX({BOX_SIZE})"
SHEETS = {
    "pos_clean": ("1_POS_판매", {
        "기준월": "month", "권역": "region", "판매채널": "channel", "제품코드": "sku",
        "제품명": "name", "브랜드": "brand", "카테고리": "category", "판매수량": "units",
        "판매금액": "amount", "행사구분": "promo", "수량단위": "unit",
    }),
    "sellin": ("2_출고_sell-in", {
        "기준월": "month", "판매채널": "channel", "제품코드": "sku", "제품명": "name",
        "출고수량": "units",
    }),
    "temperature": ("3_권역별기온", {
        "기준월": "month", "권역": "region", "평균기온(℃)": "temp_c",
    }),
    "assets": ("4_제품자산DB", {
        "SKU코드": "sku", "제품명": "name", "브랜드": "brand", "카테고리": "category",
        "용기·용량": "pack", "출시일": "launched", "폐지(중단)일": "ended", "상태": "status",
        "컨셉요약": "concept", "최고연매출(억원)": "peak_sales_100m", "단종·중단사유": "reason",
        "비고": "note",
    }),
    "infra": ("5_유통채널_인프라", {
        "채널": "channel", "점포·기기수(가상)": "stores", "냉동 음료 진열 가능 점포율": "frozen_rate",
        "냉장 쇼케이스 보유율": "chilled_rate", "비고": "note",
    }),
    "past_tests": ("6_과거컨셉테스트_실적", {
        "제품": "product", "컨셉테스트연도": "year", "카테고리": "category",
        "컨셉테스트_구매의향TOP2": "intent_top2", "출시6개월_취급점포율": "distribution_6m",
        "출시12개월_실제구매경험률": "trial_12m", "환산계수(실제/의향)": "ratio", "비고": "note",
    }),
}


def _read_sheet(book: pd.ExcelFile, name: str) -> pd.DataFrame:
    sheet, columns = SHEETS[name]
    table = pd.read_excel(
        book,
        sheet_name=sheet,
        usecols=list(columns),
        dtype={original: "string" for original, col in columns.items() if col == "sku"},
        keep_default_na=False,
    ).rename(columns=columns)
    if "month" in table:
        months = pd.to_datetime(table["month"].astype("string"), format="mixed", errors="coerce")
        invalid = months.isna().sum()
        if invalid:
            raise ValueError(f"{sheet}에서 기준월을 읽을 수 없는 행이 {invalid}개 있어요.")
        table["month"] = months.dt.strftime("%Y-%m")
    return table


def _report(source, rule, label, detail, *, removed=0, flagged=0):
    return {
        "source": source,
        "rule": rule,
        "label": label,
        "removed": int(removed),
        "flagged": int(flagged),
        "detail": detail,
    }


def _remove_test_products(pos):
    is_test = pos["name"].str.strip().str.match(r"테스트\s*상품", na=False)
    count = is_test.sum()
    return pos.loc[~is_test], _report(
        "pos", "test_product", "테스트 상품을 뺐어요",
        f"제품명이 ‘테스트상품’ 또는 ‘테스트 상품’으로 시작하는 원본 {count}행을 뺐어요.",
        removed=count,
    )


def _remove_negative_units(pos, raw):
    negative = pos["units"].lt(0)
    count = negative.sum()
    raw_count = raw["units"].lt(0).sum()
    return pos.loc[~negative], _report(
        "pos", "negative_units", "판매수량이 음수인 행을 뺐어요",
        f"판매수량이 0 미만인 원본은 {raw_count}행이에요. "
        f"테스트 상품으로 먼저 뺀 {raw_count - count}행을 제외하고 {count}행을 뺐어요.",
        removed=count,
    )


def _remove_duplicate_keys(pos, raw):
    duplicate = pos.duplicated(POS_KEY)
    count = duplicate.sum()
    raw_count = raw.duplicated(POS_KEY).sum()
    raw_members = raw.duplicated(POS_KEY, keep=False)
    overlap = (raw_members & ~raw.index.isin(pos.index)).sum()
    return pos.loc[~duplicate], _report(
        "pos", "duplicate_key", "같은 월·권역·채널·상품의 판매는 한 행만 남겼어요",
        f"원본에서 키가 겹친 행은 {raw_members.sum()}행이고, 키마다 첫 행을 빼면 {raw_count}행이에요. "
        f"겹친 행 중 {overlap}행이 앞선 규칙으로 빠졌어요. "
        f"남은 자료에서 키마다 원본 순서대로 첫 행을 남기고 {count}행을 뺐어요.",
        removed=count,
    )


def _convert_box_units(pos, raw):
    unknown_unit = ~pos["unit"].isin(["EA", BOX_UNIT])
    if unknown_unit.any():
        raise ValueError(f"판매수량 단위를 알 수 없는 행이 {unknown_unit.sum()}개 있어요.")
    boxed = pos["unit"].eq(BOX_UNIT)
    count = boxed.sum()
    raw_count = raw["unit"].eq(BOX_UNIT).sum()
    units = pos["units"].copy()
    units.loc[boxed] *= BOX_SIZE
    return pos.assign(units=units), _report(
        "pos", "box_24", "상자 단위 판매수량을 낱개로 바꿨어요",
        f"{BOX_SIZE}개들이 상자 단위는 원본 {raw_count}행이에요. "
        f"걸러 낸 뒤 남은 {count}행의 판매수량에만 {BOX_SIZE}를 곱했어요.",
        flagged=count,
    )


def _asset_ids(assets):
    # 같은 SKU의 행은 원본에서 순서를 바꿔도 같은 자산에 같은 번호를 붙인다.
    order = ["sku", "status", "launched", "ended", "name", "brand", "category", "pack",
             "concept", "peak_sales_100m", "reason", "note"]
    ordered = assets.sort_values(order)
    sequence = ordered.groupby("sku").cumcount().add(1)
    return ordered["sku"] + "-" + sequence.astype("string")


def _duplicate_sku(assets):
    flags = assets.duplicated("sku", keep=False)
    return flags, _report(
        "assets", "duplicate_sku", "코드가 같은 자산에 각각 번호를 붙였어요",
        f"코드를 함께 쓰는 자산 {flags.sum()}행을 모두 표시했어요.",
        flagged=flags.sum(),
    )


def _reversed_dates(assets):
    flags = assets["ended"].ne("") & assets["ended"].lt(assets["launched"])
    return flags, _report(
        "assets", "date_reversed", "종료일이 출시일보다 이른 자산을 표시했어요",
        f"종료일이 출시일보다 앞선 {flags.sum()}행은 날짜를 그대로 남겼어요.",
        flagged=flags.sum(),
    )


def _missing_reasons(assets):
    flags = assets["reason"].fillna("").str.strip().eq("")
    closed_without_reason = (assets["status"].isin(["단종", "개발중단"]) & flags).sum()
    return flags, _report(
        "assets", "reason_missing", "사유 기록이 없는 자산을 표시했어요",
        f"사유가 비어 있는 원본 {flags.sum()}행은 사유를 그대로 두고 표시했어요. "
        f"그중 단종됐거나 개발이 중단된 자산은 {closed_without_reason}행이에요.",
        flagged=flags.sum(),
    )


def _clean_assets(assets):
    for col in ("launched", "ended"):
        values = assets[col].replace("", None)
        dates = pd.to_datetime(values, format="mixed", errors="coerce")
        invalid = values.notna() & dates.isna()
        if invalid.any():
            raise ValueError(f"제품 자산에서 읽을 수 없는 {col} 날짜가 {invalid.sum()}행 있어요.")
        assets[col] = dates.dt.strftime("%Y-%m-%d").fillna("")
    assets["peak_sales_100m"] = pd.to_numeric(assets["peak_sales_100m"])
    assets["asset_id"] = _asset_ids(assets)
    report = []
    flags_by_row = [[] for _ in range(len(assets))]
    for rule in (_duplicate_sku, _reversed_dates, _missing_reasons):
        flags, entry = rule(assets)
        for index, marked in enumerate(flags):
            if marked:
                flags_by_row[index].append(entry["rule"])
        report.append(entry)
    assets["flags"] = pd.Series(
        [",".join(flags) for flags in flags_by_row], index=assets.index, dtype="string",
    )
    return assets, report


def _mark_after_end(pos, assets):
    valid_end = (
        assets["status"].eq("단종")
        & assets["ended"].ne("")
        & assets["ended"].ge(assets["launched"])
    )
    discontinued = assets.loc[valid_end]
    end_month_by_sku = discontinued.groupby("sku")["ended"].max().str.slice(0, 7)
    end_month = pos["sku"].map(end_month_by_sku).astype("string")
    sale_month = pos["month"].astype("string")
    after_end = sale_month.gt(end_month).fillna(False).astype(bool)
    count = after_end.sum()
    same_month = sale_month.eq(end_month).sum()
    return pos.assign(after_end=after_end), _report(
        "pos", "after_end", "단종월 이후의 판매를 표시했어요",
        f"종료일이 유효한 단종 상품의 판매 {count}행이 단종월보다 뒤예요. "
        f"같은 달의 {same_month}행은 월별 집계의 한계로 표시에서 제외했어요. "
        "같은 코드에 단종일이 여럿이면 가장 늦은 날짜를 썼어요.",
        flagged=count,
    )


def _clean_pos(raw, assets):
    pos, test = _remove_test_products(raw)
    pos, negative = _remove_negative_units(pos, raw)
    pos, duplicate = _remove_duplicate_keys(pos, raw)
    pos, box = _convert_box_units(pos, raw)
    pos, after_end = _mark_after_end(pos, assets)
    pos["is_own"] = ~pos["brand"].str.startswith(("경쟁사", "편의점PB"))
    return pos, [test, negative, duplicate, box, after_end]


def build_sales(path: Path) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """3-1 원본을 읽어 판매·자산 관련 여섯 표와 정제 내역을 돌려준다."""
    with pd.ExcelFile(path) as book:
        tables = {name: _read_sheet(book, name) for name in SHEETS}
    assets, asset_report = _clean_assets(tables["assets"])
    pos, pos_report = _clean_pos(tables["pos_clean"], assets)
    tables.update(pos_clean=pos, assets=assets)
    tables["infra"]["stores"] = pd.to_numeric(tables["infra"]["stores"]).astype("Int64")
    return (
        {name: table.loc[:, list(CSV_COLUMNS[name])].reset_index(drop=True)
         for name, table in tables.items()},
        pos_report + asset_report,
    )
