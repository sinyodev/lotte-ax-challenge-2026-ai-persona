"""aT 식품산업통계정보(FIS)의 소매 POS 매출에서 음료·주류 품목별 연 매출과 편의점 비중을 받아 온다.

실행:
    /usr/bin/python3 scripts/collect_fis_pos.py          # 2025년
    /usr/bin/python3 scripts/collect_fis_pos.py 2024     # 다른 해(맞추는 자료와 검증 자료를 나눌 때 쓴다)

원본:  https://www.atfis.or.kr/home/offsales.do  (마켓링크 소매점 POS, 2020년~. 로그인 없이 보이는 화면)
원시:  data/raw/fis-pos/<받은 날>/<품목>.json, <품목>_<구분>.html   (받은 그대로. 저장소에 올리지 않는다)
출력:  data/clean/fis_pos_<연도>_cvs.csv          품목별 연 매출, 편의점 비중, 편의점 매출(곱한 값), 편의점 안에서의 비중
       data/clean/fis_pos_<연도>_top_brands.csv   품목별로 화면에 나온 브랜드와 세분시장의 순서
       data/clean/fis_pos_<연도>_brands.csv       브랜드와 세분시장의 연 매출(화면에서 이름을 눌렀을 때 부르는 조회를 그대로 부른다).
                                                  화면의 10위 안에 없어도 우리 매대에 있는 브랜드는 EXTRA에 적어 함께 받는다

읽을 때 주의:
- 화면에 "일부 유통채널의 POS 정보를 수집·가공한 데이터"라고 적혀 있다. 시장 전체가 아니다.
- 편의점 매출은 (품목의 연 매출) × (그 해의 편의점 비중)으로 우리가 곱한 값이다.
- 생수, 이온음료, 에너지음료, 탄산수는 이 화면의 품목에 따로 없다. 그래서 "편의점 안에서의 비중"은 여기 있는 품목끼리의 비중이다.
- 브랜드별 금액은 품목 전체(모든 채널)의 금액이다. 편의점만의 금액은 브랜드 단위로 주지 않는다.
- 제품(용량·맛) 단위의 금액은 이 화면에 없다. 가장 잘게 볼 수 있는 것이 브랜드와 세분시장이다.
- 그 해의 금액이 없으면(예: 더하다는 2024년까지만 있다) 가장 가까운 앞선 해의 금액을 적고 어느 해인지 남긴다.
"""

import csv
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
BASE = "https://www.atfis.or.kr/home/offsales.do"
RAW = ROOT / "data" / "raw" / "fis-pos" / date.today().isoformat()
CLEAN = ROOT / "data" / "clean"

# (매대, 대분류 번호, 중분류 번호, 품목 이름)
ITEMS = [
    ("음료", 5, 32, "탄산음료"), ("음료", 5, 33, "과채음료"), ("음료", 5, 34, "액상차"), ("음료", 5, 35, "두유"),
    ("음료", 5, 36, "액상커피"), ("음료", 5, 85, "단백질음료"), ("음료", 4, 28, "우유"), ("음료", 4, 30, "발효유"),
    ("주류", 18, 59, "탁주"), ("주류", 18, 60, "맥주"), ("주류", 18, 70, "소주"),
]

# 화면의 10위 안에 없지만 우리 매대에 있는 브랜드. 이름은 "브랜드_제조사"로 화면의 표기를 따른다. 자료가 없는 이름은 버린다.
EXTRA = {
    "액상차": ["더하다_롯데칠성음료(주)", "립톤_롯데칠성음료(주)", "실론티_롯데칠성음료(주)"],
    "탄산음료": ["마운틴듀_롯데칠성음료(주)"],
    "과채음료": ["미닛메이드_한국코카콜라(유)"],
    "맥주": ["한맥_오비맥주(주)", "칭따오_비어케이(주)", "호가든_오비맥주(주)", "곰표_(주)세븐브로이맥주", "크러시_롯데칠성음료(주)"],
}

opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
opener.addheaders = [("User-Agent", "Mozilla/5.0"), ("Referer", BASE)]


def get(params: dict, ajax: bool = False) -> str:
    request = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(params))
    if ajax:
        request.add_header("X-Requested-With", "XMLHttpRequest")
    with opener.open(request, timeout=40) as response:
        text = response.read().decode("utf-8")
    time.sleep(1)
    return text


def names(page: str) -> list:
    """화면의 '매출 내역' 표에 나온 이름을 위에서부터 돌려준다(총매출 제외)."""
    found = re.findall(r"initDashboard\('([^']+)'\)", page)
    return list(dict.fromkeys(html.unescape(n) for n in found))


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    get({"dataGubun": "NEW"})  # 쿠키 받기
    rows, brands, amounts = [], [], []
    for shelf, c1, c2, name in ITEMS:
        text = get({"act": "searchLatestSummary", "dataGubun": "NEW", "category1": c1, "category2": c2, "beginYear": YEAR, "year": YEAR,
                    "beginPeriod": "", "endPeriod": "", "periodGubun": "YEAR"}, ajax=True)
        (RAW / f"{name}_{YEAR}.json").write_text(text, encoding="utf-8")
        data = json.loads(text)
        amount = next(x["amount"] for x in data["yearSumList"] if x["year"] == YEAR)
        share = data["distPercentList"]["편의점"]
        rows.append([shelf, name, amount, share, round(amount * share / 100)])
        for kind, label in (("BRAND", "브랜드"), ("SEGMENT", "세분시장")):
            page = get({"dataGubun": "NEW", "gubun": kind, "category1": c1, "category2": c2, "periodGubun": "YEAR", "begin": YEAR, "end": YEAR})
            (RAW / f"{name}_{kind}_{YEAR}.html").write_text(page, encoding="utf-8")
            brands += [[shelf, name, label, i + 1, n] for i, n in enumerate(names(page))]
            for n in names(page) + (EXTRA.get(name, []) if kind == "BRAND" else []):
                text = get({"act": "searchGubunSummary", "dataGubun": "NEW", "category1": c1, "category2": c2, "beginYear": YEAR - 1, "gubun": kind,
                            "keyword": n, "targetKeyword": n, "year": YEAR, "endPeriod": "", "periodGubun": "YEAR"}, ajax=True)
                years = {x["year"]: x["amount"] for x in json.loads(text).get("yearSumList", []) if x["year"] <= YEAR and x["amount"]}
                if years:
                    used = max(years)
                    amounts.append([shelf, name, label, n.split("_")[0], n.split("_")[1] if "_" in n else "", years[used], used])
        print(f"{name}: 연 매출 {amount:,}백만원, 편의점 {share}%")
    totals = {shelf: sum(r[4] for r in rows if r[0] == shelf) for shelf in ("음료", "주류")}
    with open(CLEAN / f"fis_pos_{YEAR}_cvs.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["매대", "품목", "연 매출(백만원)", "편의점 비중(%)", "편의점 매출(백만원, 곱한 값)", "편의점 안에서의 비중(%)", "연도", "출처", "받은 날"])
        for r in rows:
            writer.writerow(r + [round(100 * r[4] / totals[r[0]], 1), YEAR, "aT 식품산업통계정보 소매 POS(마켓링크)", date.today().isoformat()])
    with open(CLEAN / f"fis_pos_{YEAR}_top_brands.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["매대", "품목", "구분", "화면에 나온 순서", "이름"])
        writer.writerows(brands)
    with open(CLEAN / f"fis_pos_{YEAR}_brands.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["매대", "품목", "구분", "이름", "제조사", "연 매출(백만원, 모든 채널)", "금액의 연도"])
        writer.writerows(sorted(amounts, key=lambda r: (r[0], r[1], r[2], -r[5])))
    print(f"-> data/clean/fis_pos_{YEAR}_cvs.csv, fis_pos_{YEAR}_top_brands.csv, fis_pos_{YEAR}_brands.csv")


if __name__ == "__main__":
    main()
