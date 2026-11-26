"""주류 매대 후보 표를 만든다. 세븐일레븐 할인행사 목록의 주류와 한국소비자원의 편의점 가격을 쓴다.

실행:
    python3 scripts/build_alcohol_shelf.py

입력:  data/clean/seven_eleven_events_<날짜>.csv              (주류의 묶음·할인 행사)
       data/raw/kca-price/kca_price_<날짜>.csv                 (한국소비자원 생필품 가격 정보. 공공데이터포털 15083256)
출력:  data/clean/kca_cvs_prices_<날짜>.csv                    (편의점에서 조사된 상품의 가격 요약)
       data/ours/alcohol_shelf_candidates.csv                  (주류 매대 후보)

규칙 (2026-11-17 참가자 결정):
- 주류는 행사 없는 상품의 전체 목록을 구할 수 없다. 세븐일레븐의 행사 목록(묶음 할인 등)에서 주류를 고르고,
  행사 없는 기본 가격은 한국소비자원의 편의점 조사 가격을 쓴다.
- 주류인지와 주종은 이름을 보고 우리가 판단한 것이다. 표에 "확인 필요"로 남긴다.
"""

import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "clean"
OURS = ROOT / "data" / "ours"

# 위에서부터 먼저 맞는 주종으로 본다.
KINDS = [
    ("논알콜", r"논알콜|넌알콜|0\.0|제로500ml캔$|올제로"),
    ("하이볼·RTD", r"하이볼|순하리|레몬진|자몽진|유자진|샹그리아|츄하이|호로요이|이슬톡톡|와인볼|토닉워터"),
    ("소주", r"소주|참이슬|처음처럼|새로|진로|좋은데이|에이슬|대선|한라산|여울|화요|일품"),
    ("막걸리", r"막걸리|탁주|장수|느린마을"),
    ("와인·사케·위스키", r"와인|샴페인|사케|위스키|보드카|데낄라|리큐르|청하|매취순|복분자|백세주|산사춘"),
    ("맥주", r"맥주|카스|테라|켈리|클라우드|크러시|필라이트|하이네켄|칭따오|아사히|삿포로|기린|버드와이저|호가든|스텔라|"
             r"기네스|블랑|칼스버그|파울라너|타이거|필스너|에일|라거|IPA|블루문|코젤|에델바이스|써머스비|한맥|하이트"),
]
ALCOHOL_MAKERS = {"오비", "하이트", "진로", "아사히", "하이네", "비어", "엠즈", "세븐브로이", "카브루", "산토리", "칼스", "디아",
                  "골든", "제주", "에이이", "금양", "리커", "아영", "나라", "레뱅드", "니혼슈", "젠니혼", "신세계", "인디", "무학",
                  "신동엽", "스퀴즈", "앙리마티스", "롯데"}
NOT_ALCOHOL = re.compile(r"젤리|캔디|카스타드|카스테라|어포|튀김|바\d|콘\d|모나카|아이스|빙수|와일드바디|우유|라떼|초코|쿠키|과자|스낵|컵|주스")


def latest(folder: Path, pattern: str) -> Path:
    return sorted(folder.glob(pattern))[-1]


def kind_of(name: str) -> str:
    for kind, pattern in KINDS:
        if re.search(pattern, name):
            return kind
    return ""


def kca_summary() -> dict:
    source = latest(ROOT / "data" / "raw" / "kca-price", "kca_price_*.csv")
    groups = defaultdict(list)
    for row in csv.DictReader(open(source, encoding="cp949")):
        # 이 파일의 "제조사" 칸에는 업태(대형마트, 슈퍼마켓, 백화점, 편의점)가 들어 있다.
        if row["제조사"] == "편의점" and row["판매가격"].isdigit():
            groups[row["상품명"]].append(row)
    out = CLEAN / source.name.replace("kca_price_", "kca_cvs_prices_")
    summary = {}
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["상품명", "조사 건수", "가격 중앙값(원)", "최저(원)", "최고(원)", "세일 표시 건수", "1+1 표시 건수", "조사일"])
        for name, rows in sorted(groups.items()):
            prices = [int(r["판매가격"]) for r in rows]
            days = sorted({r["조사일"] for r in rows})
            summary[name] = int(statistics.median(prices))
            writer.writerow([name, len(rows), summary[name], min(prices), max(prices),
                             sum(r["세일여부"] == "Y" for r in rows), sum(r["원플러스원"] == "Y" for r in rows), "~".join(days[::max(1, len(days) - 1)])])
    print(f"편의점 조사 상품 {len(summary)}종 -> {out.relative_to(ROOT)}")
    return summary


def main() -> None:
    kca = kca_summary()
    rows = []

    # 1. 기본 가격: 한국소비자원이 편의점에서 조사한 주류
    for name, price in kca.items():
        kind = kind_of(name)
        if kind and not NOT_ALCOHOL.search(name):
            bundle = re.search(r"(\d+)캔|\*(\d+)개", name)
            count = int(bundle.group(1) or bundle.group(2)) if bundle else 1
            rows.append([name, kind, "편의점 4개 체인(한국소비자원 조사)", "행사 없음(기본 가격)", count, price, round(price / count), "", "주종 확인 필요"])

    # 2. 행사: 세븐일레븐 행사 목록의 주류
    for row in csv.DictReader(open(latest(CLEAN, "seven_eleven_events_*.csv"), encoding="utf-8")):
        name, maker = row["상품명"], row["이름 앞 표기(제조사·브랜드)"]
        kind = kind_of(name)
        if not kind or NOT_ALCOHOL.search(name) or not row["정가(원)"]:
            continue
        if maker not in ALCOHOL_MAKERS and kind in ("소주", "맥주", "막걸리"):
            continue
        bundle = re.search(r"\((\d+)입|(\d+)입\)|(\d+)입번들|(\d+)팩|\((\d+)$|\(박스", name)  # 홈페이지가 이름 끝을 자르므로 "(6"도 묶음으로 본다
        count = 1
        if bundle:
            count = 20 if "박스" in bundle.group(0) else int(next(g for g in bundle.groups() if g))
        price = int(row["정가(원)"])
        rows.append([name, kind, "세븐일레븐", row["행사"] + (f" ({count}개 묶음)" if count > 1 else ""), count, price,
                     round(price / count), row["바코드(이미지 경로에서)"], "주류 여부와 주종 확인 필요"])

    OURS.mkdir(parents=True, exist_ok=True)
    out = OURS / "alcohol_shelf_candidates.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["상품명", "주종(짐작)", "판매처", "행사", "묶음 수량", "표시 가격(원)", "1개당 가격(원)", "바코드", "확인"])
        writer.writerows(sorted(rows, key=lambda r: (r[1], r[2], r[0])))
    print(f"{len(rows)}건 -> {out.relative_to(ROOT)}")

    by = defaultdict(list)
    for r in rows:
        by[(r[1], r[2] == "세븐일레븐", r[4] > 1)].append(r)
    for (kind, seven, bundle), items in sorted(by.items()):
        label = ("세븐일레븐 " + ("묶음" if bundle else "낱개")) if seven else "소비자원 기본 가격"
        unit = sorted(i[6] for i in items)
        print(f"  {kind} / {label}: {len(items)}건, 1개당 {unit[0]:,}~{unit[-1]:,}원 (중앙값 {unit[len(unit) // 2]:,}원)")
    print("\n== 롯데 주류")
    for r in rows:
        if r[0].startswith("롯데)") or "처음처럼" in r[0] or "클라우드" in r[0]:
            print(f"  {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[5]:,}원 (1개당 {r[6]:,}원)")


if __name__ == "__main__":
    main()
