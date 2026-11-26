"""CU 음료 목록(정가)과 세븐일레븐 행사 목록(행사)을 상품명으로 맞춰 음료 매대 후보 표를 만든다.

실행:
    python3 scripts/build_beverage_shelf.py

입력:  data/clean/cu_drinks_<날짜>.csv              (정가의 근거. 행사 없는 상품 포함)
       data/clean/seven_eleven_events_<날짜>.csv    (행사의 근거)
출력:  data/ours/beverage_shelf_candidates.csv

규칙 (2026-11-17 참가자 결정):
- 제품과 정가는 CU 목록을 바탕으로 한다.
- 행사는 세븐일레븐 목록에서 같은 상품을 찾아 붙인다. 못 찾으면 "행사 없음"으로 둔다.
- 맞춘 것은 우리가 판단한 것이므로 맞춘 점수와 확인 필요 여부를 함께 남긴다.

같은 상품으로 보는 조건: 제조사가 같은 묶음이고, 용량 숫자가 같고, 이름의 닮은 정도가 기준 이상이고,\n"제로" 같은 핵심 낱말이 양쪽에 똑같이 있거나 없다.
"""

import csv
import difflib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "clean"
OUT = ROOT / "data" / "ours" / "beverage_shelf_candidates.csv"

AUTO = 0.80    # 이 점수 이상이면 같은 상품으로 본다
REVIEW = 0.62  # 이 점수 이상이면 붙이되 사람이 확인한다
# 이 낱말이 한쪽에만 있으면 다른 상품일 수 있다(예: 사이다와 사이다 제로). 점수가 높아도 "확인 필요"로 내린다.
KEY_WORDS = ["제로", "라이트", "디카페인", "저당", "무가당", "논알콜", "프로틴", "락토프리"]

# 두 체인이 같은 회사를 다르게 적는 것을 한 이름으로 모은다.
MAKER = {
    "롯데": "롯데칠성", "칠성": "롯데칠성", "코카": "코카콜라", "동아": "동아오츠카", "오츠카": "동아오츠카",
    "하이트": "하이트진로", "진로": "하이트진로", "서울": "서울우유", "스벅": "스타벅스", "스타벅스": "스타벅스",
    "티오피": "동서", "맥심": "동서",
}
# 이름 안의 표기를 통일한다.
REPLACE = [
    ("콜라제로", "제로"), ("제로콜라", "제로"), ("코크", "코카콜라"), ("페트", "P"), ("펫", "P"), ("PET", "P"),
    ("RICH", "리치"), ("&", ""), ("(", ""), (")", ""), (" ", ""), ("_", ""), ("ML", "ml"), ("mL", "ml"),
]


def latest(pattern: str) -> Path:
    return sorted(CLEAN.glob(pattern))[-1]


def split(name: str) -> tuple[str, str, str]:
    """상품명을 (제조사, 용량, 맞출 이름)으로 나눈다."""
    maker, body = (name.split(")", 1) + [""])[:2] if ")" in name[:12] else ("", name)
    maker = MAKER.get(maker.strip(), maker.strip())
    for old, new in REPLACE:
        body = body.replace(old, new)
    volume = ""
    m = re.search(r"(\d+(?:\.\d+)?)(ml|L|l)?$", body) or re.search(r"(\d+(?:\.\d+)?)(ml|L|l)", body)
    if m:
        number = float(m.group(1))
        if (m.group(2) or "").lower() == "l" or number < 10:
            number *= 1000
        volume = str(int(number))
        body = body[: m.start()] + body[m.end():]
    body = re.sub(r"(캔|P|병|ml)$", "", body)
    return maker, volume, body


def main() -> None:
    cu = list(csv.DictReader(open(latest("cu_drinks_*.csv"), encoding="utf-8")))
    seven = [r for r in csv.DictReader(open(latest("seven_eleven_events_*.csv"), encoding="utf-8"))]
    index = {}
    for row in seven:
        maker, volume, body = split(row["상품명"])
        index.setdefault((maker, volume), []).append((body, row))

    out_rows, counts = [], {"같은 상품": 0, "확인 필요": 0, "못 찾음": 0}
    for row in cu:
        maker, volume, body = split(row["상품명"])
        best, best_score = None, 0.0
        for other_body, other in index.get((maker, volume), []):
            score = difflib.SequenceMatcher(None, body, other_body).ratio()
            if score > best_score:
                best, best_score = other, score
        differs = best is not None and any((w in row["상품명"]) != (w in best["상품명"]) for w in KEY_WORDS)
        if best and best_score >= AUTO and not differs:
            state = "같은 상품"
        elif best and best_score >= REVIEW:
            state = "확인 필요"
        else:
            state, best = "못 찾음", None
        counts[state] += 1
        out_rows.append([
            row["상품명"], maker, volume, row["정가(원)"], row["행사"] or "행사 없음",
            best["상품명"] if best else "", best["정가(원)"] if best else "",
            best["행사"] if best else "행사 없음", round(best_score, 2) if best else "", state,
            best["바코드(이미지 경로에서)"] if best else "", row["꼬리표"], row["확인한 날"],
        ])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "CU 상품명", "제조사(통일)", "용량(ml)", "CU 정가(원)", "CU 행사", "세븐일레븐 상품명", "세븐일레븐 정가(원)",
            "세븐일레븐 행사", "맞춘 점수", "맞춘 상태", "바코드", "CU 꼬리표", "확인한 날",
        ])
        writer.writerows(out_rows)
    print(f"{len(out_rows)}건 -> {OUT.relative_to(ROOT)}  {counts}")

    for state in ("같은 상품", "확인 필요"):
        print(f"\n== {state} 예시")
        for r in [r for r in out_rows if r[9] == state][:14]:
            print(f"  {r[8]}  {r[0]} ({r[3]}원, CU {r[4]})  <->  {r[5]} ({r[6]}원, {r[7]})")
    matched = [r for r in out_rows if r[9] == "같은 상품"]
    same_price = sum(1 for r in matched if r[3] == r[6])
    same_event = sum(1 for r in matched if r[4] == r[7])
    print(f"\n같은 상품 {len(matched)}건 가운데 정가가 같은 것 {same_price}건, 행사가 같은 것 {same_event}건")
    lotte = [r for r in out_rows if r[1] == "롯데칠성"]
    print(f"롯데칠성 {len(lotte)}건: " + str({s: sum(1 for r in lotte if r[9] == s) for s in counts}))


if __name__ == "__main__":
    main()
