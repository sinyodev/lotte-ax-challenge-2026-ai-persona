"""W1의 월별 지표로 내부 자료의 흐름을 판정한다."""

from collections import defaultdict
from datetime import date
from statistics import mean, median, pstdev
import re

import onsite

PEAK_OUT_RATIO = 0.60
SEASONAL_RATIO = 3
RISING_RATIO = 1.20
STABLE_VARIATION = 0.20
SPIKE_RATIO = 2

SERIES_COLUMNS = ("month", "search_index", "sns_mentions", "sns_organic", "ad_share")
PRODUCT_SEARCH = re.compile(
    r"제품|상품|구매|가격|판매|편의점|파는|마트|브랜드|추천|배송|카페|스타벅스|"
    r"밀키스|레쓰비|델몬트|코카콜라|칠성사이다|펩시|칸타타|카누|세븐일레븐|GS25|\bCU\b",
    re.IGNORECASE,
)
OTHER_INTENT = re.compile(r"만들|만드|레시피|하는\s*법|재료|비율|효능|부작용|보관")


def _key(keyword: str) -> str:
    return "".join(keyword.casefold().split())


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _search_stages(series: list[dict], stage: list[str], reasons: list[str]) -> None:
    years: dict[int, dict[int, float]] = defaultdict(dict)
    search = {}
    for point in series:
        value = point["search_index"]
        if value is None:
            continue
        month = date.fromisoformat(point["month"] + "-01")
        years[month.year][month.month] = value
        search[month.year * 12 + month.month] = value

    if not search:
        return
    latest_year = max(years)
    current, previous = years[latest_year], years.get(latest_year - 1, {})
    paired = sorted(current.keys() & previous.keys())
    # 두 해에서 함께 관측된 달만 비교한다. 기간 양 끝의 불완전한 연도도 처리한다.
    if len(paired) >= 6:
        current_peak = max(paired, key=current.__getitem__)
        previous_peak = max(paired, key=previous.__getitem__)
        new_peak, old_peak = current[current_peak], previous[previous_peak]
        if old_peak > 0 and new_peak < old_peak * PEAK_OUT_RATIO:
            stage.append("피크아웃")
            reasons.append(
                f"{latest_year}년 최고 검색 지수는 {new_peak:g}로, "
                f"지난해 같은 기간 최고치({old_peak:g})의 {_pct(new_peak / old_peak)}예요."
            )
        old_low = min(previous[m] for m in paired)
        new_low = min(current[m] for m in paired)
        if (current_peak == previous_peak and new_peak > 0 and old_peak > 0
                and new_peak >= SEASONAL_RATIO * new_low and old_peak >= SEASONAL_RATIO * old_low):
            stage.append("계절성 수요")
            reasons.append(
                f"두 해 모두 {current_peak}월에 검색이 가장 많았어요. "
                f"각 해의 낮은 달과 높은 달의 검색 지수는 {old_low:g}~{old_peak:g}, {new_low:g}~{new_peak:g}였어요."
            )

    latest = max(search)
    recent = range(latest - 5, latest + 1)
    if all(m in search and m - 12 in search for m in recent):
        new_avg = mean(search[m] for m in recent)
        old_avg = mean(search[m - 12] for m in recent)
        if old_avg > 0 and new_avg >= old_avg * RISING_RATIO:
            stage.append("상승기")
            reasons.append(
                f"최근 6개월 평균 검색 지수({new_avg:.1f})가 지난해 같은 기간({old_avg:.1f})보다 "
                f"{_pct(new_avg / old_avg - 1)} 높았어요."
            )


def _ad_stage(series: list[dict], stage: list[str], reasons: list[str]) -> None:
    months = [point for point in series if point["sns_mentions"] is not None and point["ad_share"] is not None]
    if len(months) < 6:
        return
    spikes = []
    for month in months:
        baseline = [point for point in months if point is not month]
        posts = median(point["sns_mentions"] for point in baseline)
        ads = median(point["ad_share"] for point in baseline)
        if month["sns_mentions"] > posts * SPIKE_RATIO and month["ad_share"] > ads * SPIKE_RATIO:
            spikes.append((month, posts, ads))
    if spikes:
        month, posts, ads = max(spikes, key=lambda spike: spike[0]["sns_mentions"])
        stage.append("광고성 바이럴")
        reasons.append(
            f"{month['month']}에 SNS 언급이 {month['sns_mentions']:,}건(다른 달의 중앙값 {posts:g}건)이었어요. "
            f"광고·협찬은 {_pct(month['ad_share'])}로 다른 달의 중앙값({_pct(ads)})의 두 배를 넘었어요."
        )


def _diagnose(keyword: str, rows: list[dict], related: list[dict], volume: int | None) -> dict:
    series = [{key: row[key] for key in SERIES_COLUMNS} for row in sorted(rows, key=lambda r: r["month"])]
    stage: list[str] = []
    reasons: list[str] = []
    shares = [point["ad_share"] for point in series if point["ad_share"] is not None]
    search = [point["search_index"] for point in series if point["search_index"] is not None]

    _ad_stage(series, stage, reasons)
    _search_stages(series, stage, reasons)
    if not stage and len(search) >= 6 and (mean(search) == 0 or pstdev(search) <= mean(search) * STABLE_VARIATION):
        stage.append("안정기")
        reasons.append(f"검색 지수는 관측한 {len(search)}개월 동안 평균 {mean(search):.1f}, 표준편차 {pstdev(search):.1f}였어요.")
    if search and not stage:
        reasons.append("관측한 기간의 검색·SNS 수치에서 판정 기준을 충족한 흐름이 없어요.")

    known_shares = [entry for entry in related if entry["share"] is not None]
    product_share = None
    if known_shares:
        product_share = min(1.0, round(sum(
            entry["share"] for entry in known_shares
            if PRODUCT_SEARCH.search(entry["related"]) and not OTHER_INTENT.search(entry["related"])
        ), 8))
        reasons.append(f"연관검색어에서 제품이나 판매처를 찾는 것으로 읽힌 검색의 비중은 {_pct(product_share)}예요.")
    if volume is not None:
        reasons.append(f"내부 자료에서 검색 지수 100은 한 달 약 {volume:,}회 검색에 해당해요.")

    return {
        "keyword": keyword, "stage": stage, "reasons": reasons, "series": series,
        "ad_share_peak": max(shares, default=None), "product_search_share": product_share,
        "related": related, "source": "internal",
    }


def verdicts() -> list[dict]:
    if not onsite.available():
        return []
    try:
        trend, related, volume = (onsite.load(table) for table in ("trend", "trend_related", "trend_volume"))
    except onsite.NoData:
        return []

    rows: dict[str, list[dict]] = defaultdict(list)
    terms: dict[str, list[dict]] = defaultdict(list)
    for row in trend:
        rows[row["keyword"]].append(row)
    for row in related:
        terms[_key(row["keyword"])].append({"related": row["related"], "share": row["share"]})
    search_volumes = {_key(row["keyword"]): row["searches_at_100"] for row in volume}
    return [_diagnose(keyword, points, terms[_key(keyword)], search_volumes.get(_key(keyword)))
            for keyword, points in rows.items()]


def verdict(keyword: str) -> dict:
    key = _key(keyword)
    for item in verdicts():
        if _key(item["keyword"]) == key:
            return item
    return _diagnose(keyword.strip(), [], [], None)
