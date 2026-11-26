from datetime import datetime, timezone

import pandas as pd
import pytest
from openpyxl import Workbook

from onsite import journeys
from onsite.schema import CSV_COLUMNS


@pytest.mark.parametrize(
    ("purpose", "memo", "seconds", "compared", "gaze", "style"),
    [
        ("장보기", "2+1을 보고 선택", 55, 6, 8.0, "행사형"),
        ("장보기", "늘 사던 상품부터 집음", 47, 5, 6.0, "습관형"),
        ("장보기", "메모 없음", 15, 2, 0.0, "목적형"),
        ("장보기", "진열대를 둘러봄", 45, 5, 0.0, "목적형"),
        ("가족용 음료", "", 50, 3, 5.0, "목적형"),
        ("간식", "", 15, 2, 0.0, "습관형"),
        ("간식", "진열대를 둘러봄", 45, 5, 0.0, "탐색형"),
        ("간식", "진열대를 둘러봄", 42, 3, 5.0, "탐색형"),
        ("간식", "가격을 비교함", 45, 5, 8.0, "목적형"),
        ("간식", "가격이 비싸서 내려놓음", 20, 2, 0.0, "목적형"),
        ("아이에게 줄 음료", "", 28, 3, 0.0, "목적형"),
        ("행사 상품 위주", "", 26, 3, 0.0, "행사형"),
        ("간식", "", 22, 3, 0.0, "탐색형"),
        ("간식", "", 17, 2, 0.0, "습관형"),
        (None, None, 22, pd.NA, 0.0, "탐색형"),
        (None, None, None, None, None, "습관형"),
    ],
)
def test_visit_styles_use_observed_actions_then_purpose_then_metrics(purpose, memo, seconds, compared, gaze, style):
    assert journeys._visit_style(purpose, memo, seconds, compared, gaze) == style


@pytest.mark.parametrize(
    ("stamp", "zone", "expected", "converted"),
    [
        ("2023-12-31 20:30:00", "UTC", "2024-01-01T05:30:00+09:00", True),
        ("2023-12-31 20:30:00", "KST", "2023-12-31T20:30:00+09:00", False),
        (datetime(2023, 4, 5, tzinfo=timezone.utc), "", "2023-04-05T09:00:00+09:00", True),
        ("2023-12-31T00:05:00+09:00", "", "2023-12-31T00:05:00+09:00", False),
        ("2023-12-31T03:00:00Z", "", "2023-12-31T12:00:00+09:00", True),
        ("2023-12-31 20:30:00", "", None, False),
        ("입력 오류", "UTC", None, False),
        (pd.NaT, "KST", None, False),
    ],
)
def test_timestamp_normalization(stamp, zone, expected, converted):
    assert journeys._normalize_timestamp(stamp, zone) == (expected, converted)


def test_bot_concentration_counts_union_and_preserves_rows(monkeypatch):
    monkeypatch.setattr(journeys, "IP_BOT_MIN_EVENTS", 4)
    monkeypatch.setattr(journeys, "COOKIE_BOT_MIN_EVENTS", 3)
    groups = [
        ("집중 IP", "집중 쿠키"), ("집중 IP", "견본 1"), ("집중 IP", "견본 2"), ("집중 IP", "견본 3"),
        ("일반 IP 1", "집중 쿠키"), ("일반 IP 2", "집중 쿠키"),
        ("일반 IP 3", "일반 쿠키"), ("일반 IP 3", "일반 쿠키"), ("일반 IP 3", "견본 4"),
        ("", None), ("", None), ("", None), ("", None),
    ]
    raw = pd.DataFrame([
        [f"견본-{i}", i, cookie, "2024-02-21 03:00:00", "제휴몰", "클릭", "임의 상품코드",
         "임의 제품", 4, "PC", ip, "없음", "UTC"]
        for i, (ip, cookie) in enumerate(groups)
    ], columns=list(journeys.ONLINE_RENAME))

    logs, (timezone_report, bot_report) = journeys._build_online(raw)

    assert logs["log_id"].tolist() == raw["로그ID"].tolist()
    assert logs["is_bot"].tolist() == [True] * 6 + [False] * 7
    assert logs["ts_kst"].tolist() == ["2024-02-21T12:00:00+09:00"] * len(raw)
    assert tuple(logs.columns) == CSV_COLUMNS["journeys_online"]
    assert bot_report["removed"] == timezone_report["removed"] == 0
    assert bot_report["flagged"] == 6
    assert "겹치는 1건" in bot_report["detail"]
    assert "다른 시간대 13건" in timezone_report["detail"]


def test_trend_keeps_values_and_search_sns_pairing():
    search = pd.DataFrame({"기준월": ["2024-01", "2024-02"], "유자": [-8, 102], "자몽": [32, 52]})
    sns = pd.DataFrame([
        ("2024-02", "자몽", 9, None), ("2024-02", "유자", 15, 1.0),
        ("2024-01", "자몽", 45, .3), ("2024-01", "유자", -9, .25),
    ], columns=["기준월", "키워드", "SNS언급량(건)", "광고·협찬 비중"])

    trend, (bounds, organic) = journeys._build_trend(search, sns)
    assert tuple(trend.columns) == CSV_COLUMNS["trend"]
    keyed = trend.set_index(["month", "keyword"])
    assert keyed.loc[("2024-01", "유자")].tolist() == [0, -8, 0, -9, .25, 0]
    assert keyed.loc[("2024-02", "유자")].tolist() == [100, 102, 15, 15, 1, 0]
    assert keyed.loc[("2024-01", "자몽"), "sns_organic"] == pytest.approx(31.5)
    assert pd.isna(keyed.loc[("2024-02", "자몽"), "sns_organic"])
    assert bounds["flagged"] == 2
    assert "언급 수가 줄어든 기록은 2건" in organic["detail"]
    assert bounds["removed"] == organic["removed"] == organic["flagged"] == 0


def test_build_journeys_wires_workbook_and_preserves_observed_fields(tmp_path, monkeypatch):
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = {
        "1_구매여정_오프라인": [
            list(journeys.OFFLINE_RENAME),
            ["견본", "2024-01-13", "동네점(편의점)", "60대", "여성", "가족 장보기", 32, 4, 1.2,
             "견본 음료", "구매 안 함", "제품 비교 중"],
        ],
        "2_구매여정_온라인로그": [list(journeys.ONLINE_RENAME)],
        "3_검색트렌드지수": [["기준월", "자몽"], ["2024-01", 22]],
        "4_검색량환산참고": [["키워드", "지수100에해당하는월검색량(회)"], ["자몽", 340]],
        "5_SNS언급량": [["기준월", "키워드", "SNS언급량(건)", "광고·협찬 비중"], ["2024-01", "자몽", 20, .1]],
        "6_연관검색어": [["키워드", "연관검색어", "비중(최근 12개월)"], ["자몽", "자몽 껍질", .2]],
    }
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    xlsx, docx = tmp_path / "견본.xlsx", tmp_path / "견본.docx"
    workbook.save(xlsx)

    def fake_fgi(path):
        assert path == docx
        return {"participants": []}, []

    monkeypatch.setattr(journeys, "build_fgi", fake_fgi)
    tables, report = journeys.build_journeys(xlsx, docx)

    assert set(tables) == {"trend", "trend_related", "trend_volume", "journeys_offline", "journeys_online", "fgi"}
    for name in set(tables) - {"fgi"}:
        assert tuple(tables[name].columns) == CSV_COLUMNS[name]
    assert tables["journeys_offline"].iloc[0].tolist() == [
        "견본", "2024-01-13", "동네점(편의점)", "편의점", "60대", "여성", "가족 장보기", 32, 4, 1.2,
        "견본 음료", "구매 안 함", "제품 비교 중", "목적형",
    ]
    assert tables["trend_related"].iloc[0].tolist() == ["자몽", "자몽 껍질", .2]
    assert tables["trend_volume"].iloc[0].tolist() == ["자몽", 340]
    assert tables["fgi"] == {"participants": []}
    assert {entry["source"] for entry in report} == {"trend", "journeys_online"}
