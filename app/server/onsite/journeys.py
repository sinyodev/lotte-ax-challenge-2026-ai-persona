"""구매여정 기록과 검색·SNS 원본을 W1 표로 변환한다."""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .fgi import build_fgi
from .schema import CSV_COLUMNS

KST = timezone(timedelta(hours=9))
TIMEZONES = {"KST": KST, "UTC": timezone.utc}
IP_BOT_MIN_EVENTS = 100
COOKIE_BOT_MIN_EVENTS = 11
STORE_TYPE = re.compile(r"편의점|대형마트")
PROMOTION = re.compile(r"(?:\d\s*\+\s*\d|행사|할인).{0,15}(?:선택|고르|구매|집|위주|고름)")
HABIT = re.compile(r"늘\s*사던|평소\s*(?:사던|사는|먹던)|자주\s*사던|습관적으로")
PURPOSE = re.compile(r"장보기|장\s*보러|가족|식구|아이(?=들|에게|용|\s|$)|자녀|선물")
PRICE_DECISION = re.compile(r"가격.{0,15}(?:때문|부담|비싸|내려놓|포기)")

OFFLINE_RENAME = {
    "관찰ID": "oid", "촬영일": "date", "점포(유형)": "store", "연령대": "age",
    "성별": "gender", "방문목적": "purpose", "매대도착~선택(초)": "seconds",
    "비교한제품수": "compared", "신제품매대시선고정(초)": "gaze_new_s",
    "선택제품": "chosen", "구매결과": "bought", "관찰자메모": "memo",
}
ONLINE_RENAME = {
    "로그ID": "log_id", "세션ID": "session", "쿠키ID": "cookie", "일시": "timestamp",
    "유입경로": "source", "이벤트": "event", "제품코드": "sku", "제품명": "name",
    "체류시간(초)": "dwell_s", "기기": "device", "IP그룹": "ip_group",
    "프로모션여부": "promo", "시간대": "timezone",
}


def _project(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    return frame.loc[:, list(CSV_COLUMNS[name])]


def _bound_trend_metrics(trend: pd.DataFrame) -> dict:
    search_below = trend["search_raw"] < 0
    search_above = trend["search_raw"] > 100
    sns_below = trend["sns_raw"] < 0
    trend["search_index"] = trend["search_raw"].clip(lower=0, upper=100)
    trend["sns_mentions"] = trend["sns_raw"].clip(lower=0)
    return {
        "source": "trend", "rule": "out_of_range", "label": "범위를 벗어난 트렌드 수치를 보정했어요",
        "removed": 0, "flagged": int((search_below | search_above | sns_below).sum()),
        "detail": (
            f"검색 지수 음수 {int(search_below.sum())}건과 SNS 언급 수 음수 "
            f"{int(sns_below.sum())}건을 0으로, 검색 지수 100 초과 "
            f"{int(search_above.sum())}건을 100으로 바꿨어요. 원래 수치는 함께 남겼어요."
        ),
    }


def _exclude_ad_mentions(trend: pd.DataFrame) -> dict:
    trend["sns_organic"] = trend["sns_mentions"] * (1 - trend["ad_share"])
    adjusted = (trend["sns_mentions"] > 0) & (trend["ad_share"] > 0)
    return {
        "source": "trend", "rule": "organic_mentions", "label": "광고와 협찬을 뺀 언급 수를 계산했어요",
        "removed": 0, "flagged": 0,
        "detail": (
            f"보정한 SNS 언급 수에 광고·협찬을 뺀 비중을 곱했어요. "
            f"언급 수가 줄어든 기록은 {int(adjusted.sum())}건이에요."
        ),
    }


def _build_trend(search: pd.DataFrame, sns: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    search = search.rename(columns={"기준월": "month"}).melt(
        id_vars="month", var_name="keyword", value_name="search_raw",
    )
    sns = sns.rename(columns={
        "기준월": "month", "키워드": "keyword", "SNS언급량(건)": "sns_raw", "광고·협찬 비중": "ad_share",
    })
    trend = search.merge(sns, on=["month", "keyword"], how="outer", validate="one_to_one")
    report = [_bound_trend_metrics(trend), _exclude_ad_mentions(trend)]
    return _project(trend, "trend"), report


def _visit_style(purpose: str, memo: str, seconds: float, compared: float, gaze: float) -> str:
    """관찰 메모의 선택 단서, 장보기·가족용 등 방문 목적, 비교·시선·시간 순으로 해석한다.

    행사 반응, 가격 판단·가족 용도, 익숙한 제품 순으로 명시적인 행동을 우선한다.
    비교 5개 이상 또는 신제품 응시 5초 이상은 탐색, 비교 2개 이하이면서
    15초 이하는 습관 단서다. 해당 기준에 들지 않으면 행사 위주의 방문 목적을 보고,
    그다음 3개 이상 비교·신제품 응시 또는 비교 수 없는 15초 초과를 탐색으로 본다.
    남은 기록은 습관형으로 분류한다.
    """
    memo = memo if pd.notna(memo) else ""
    purpose = purpose if pd.notna(purpose) else ""
    seconds, compared, gaze = (
        float(value) if pd.notna(value) else float("nan") for value in (seconds, compared, gaze)
    )
    if PROMOTION.search(memo):
        return "행사형"
    if (
        PURPOSE.search(memo)
        or PRICE_DECISION.search(memo)
        or (seconds >= 45 and "가격" in memo and "비교" in memo)
    ):
        return "목적형"
    if HABIT.search(memo):
        return "습관형"
    if PURPOSE.search(purpose):
        return "목적형"
    if compared >= 5 or gaze >= 5:
        return "탐색형"
    if compared <= 2 and seconds <= 15:
        return "습관형"
    if PROMOTION.search(purpose):
        return "행사형"
    if compared >= 3 or gaze > 0 or (pd.isna(compared) and seconds > 15):
        return "탐색형"
    return "습관형"


def _build_offline(raw: pd.DataFrame) -> pd.DataFrame:
    visits = raw.rename(columns=OFFLINE_RENAME)
    visits["store_type"] = visits["store"].str.extract(f"({STORE_TYPE.pattern})", expand=False)
    fields = ["purpose", "memo", "seconds", "compared", "gaze_new_s"]
    visits["style"] = [
        _visit_style(purpose, memo, seconds, compared, gaze)
        for purpose, memo, seconds, compared, gaze in visits[fields].itertuples(index=False, name=None)
    ]
    return _project(visits, "journeys_offline")


def _normalize_timestamp(value: str | datetime, zone: str) -> tuple[str | None, bool]:
    if pd.isna(value):
        return None, False
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None, False
    if stamp.tzinfo is None:
        tz = TIMEZONES.get(str(zone).strip().upper())
        if tz is None:
            return None, False
        stamp = stamp.replace(tzinfo=tz)
    return stamp.astimezone(KST).isoformat(), stamp.utcoffset() != KST.utcoffset(None)


def _normalize_online_time(logs: pd.DataFrame) -> dict:
    timestamps = [
        _normalize_timestamp(value, zone)
        for value, zone in logs[["timestamp", "timezone"]].itertuples(index=False, name=None)
    ]
    logs["ts_kst"] = [stamp for stamp, _ in timestamps]
    converted = sum(changed for _, changed in timestamps)
    missing = sum(stamp is None for stamp, _ in timestamps)
    return {
        "source": "journeys_online", "rule": "timezone_kst", "label": "접속 시각을 한국 시간으로 맞췄어요",
        "removed": 0, "flagged": 0,
        "detail": (
            f"한국 시각 {len(logs) - converted - missing}건을 그대로 쓰고 UTC 등 다른 시간대 {converted}건을 "
            f"한국 시간(UTC+9)으로 바꿨어요. 읽을 수 없는 시각 {missing}건은 빈칸으로 남겼어요."
        ),
    }


def _flag_bot_logs(logs: pd.DataFrame) -> dict:
    ips = logs["ip_group"].replace(r"^\s*$", pd.NA, regex=True)
    cookies = logs["cookie"].replace(r"^\s*$", pd.NA, regex=True)
    ip_counts = ips.value_counts()
    cookie_counts = cookies.value_counts()
    high_ips = ip_counts.index[ip_counts >= IP_BOT_MIN_EVENTS]
    high_cookies = cookie_counts.index[cookie_counts >= COOKIE_BOT_MIN_EVENTS]
    by_ip = ips.isin(high_ips)
    by_cookie = cookies.isin(high_cookies)
    logs["is_bot"] = by_ip | by_cookie
    return {
        "source": "journeys_online", "rule": "bot_concentration", "label": "자동 접속으로 의심되는 기록에 표시했어요",
        "removed": 0, "flagged": int(logs["is_bot"].sum()),
        "detail": (
            f"이 자료에서 IP 그룹당 {IP_BOT_MIN_EVENTS}건 이상이면 의심 기록으로 표시했어요"
            f"({len(high_ips)}개 그룹, {int(by_ip.sum())}건). 쿠키당 {COOKIE_BOT_MIN_EVENTS}건 이상도 "
            f"표시했어요({len(high_cookies)}개 쿠키, {int(by_cookie.sum())}건). "
            f"겹치는 {int((by_ip & by_cookie).sum())}건은 한 번만 세고 모든 기록을 남겼어요."
        ),
    }


def _build_online(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    logs = raw.rename(columns=ONLINE_RENAME)
    report = [_normalize_online_time(logs), _flag_bot_logs(logs)]
    return _project(logs, "journeys_online"), report


def build_journeys(path: Path, fgi_path: Path) -> tuple[dict, list[dict]]:
    """엑셀과 FGI 문서에서 계약에 정의된 여섯 표와 정제 내역을 읽는다."""
    with pd.ExcelFile(path, engine="openpyxl") as workbook:
        offline = pd.read_excel(workbook, "1_구매여정_오프라인", keep_default_na=False, na_values=[""])
        online = pd.read_excel(workbook, "2_구매여정_온라인로그", keep_default_na=False, na_values=[""])
        search = pd.read_excel(workbook, "3_검색트렌드지수")
        volume = pd.read_excel(workbook, "4_검색량환산참고").rename(columns={
            "키워드": "keyword", "지수100에해당하는월검색량(회)": "searches_at_100",
        })
        sns = pd.read_excel(workbook, "5_SNS언급량")
        related = pd.read_excel(workbook, "6_연관검색어").rename(columns={
            "키워드": "keyword", "연관검색어": "related", "비중(최근 12개월)": "share",
        })

    trend, trend_report = _build_trend(search, sns)
    online, online_report = _build_online(online)
    fgi, fgi_report = build_fgi(fgi_path)
    tables = {
        "trend": trend,
        "trend_related": _project(related, "trend_related"),
        "trend_volume": _project(volume, "trend_volume"),
        "journeys_offline": _build_offline(offline),
        "journeys_online": online,
        "fgi": fgi,
    }
    return tables, [*trend_report, *online_report, *fgi_report]
