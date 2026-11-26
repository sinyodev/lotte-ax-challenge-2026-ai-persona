"""신뢰도를 두 가지로 잰다: 일관성(같은 조건에 같은 답이 나오는가)과 현실 적합성(실제 편의점 판매와 닮았는가).

실행:
    /usr/bin/python3 scripts/reliability.py            # 있는 결과 파일을 모두 재서 표로 만든다

입력:  data/experiments/pilot/<매대>_cli*.csv          사전 측정 결과(scripts/pilot.py)
       data/clean/fis_pos_2024_cvs.csv                 맞추는 데 쓰는 자료(2024년 품목별 편의점 매출)
       data/clean/fis_pos_2025_cvs.csv                 검증 자료 1(2025년 품목별 편의점 매출)
       data/clean/knhanes_2024_product_counts.csv      검증 자료 3(제품별 마신 횟수. 맞추는 데 쓰지 않는다)
       data/clean/fis_pos_2025_brands.csv              검증 자료 2(품목 안의 브랜드별 연 매출. 맞추는 데 쓰지 않는다)
출력:  data/experiments/pilot/reliability.csv, reliability.md

맞추는 자료와 검증 자료를 나눈다.
    보정      종류별 금액 비중이 2024년 편의점 매출 비중과 같아지도록 종류마다 가중치를 준다(가중치 = 실제 비중 / 가상 비중).
    검증 1    보정한 비중을 2025년 비중과 견준다. 해가 바뀌어도 비중이 1%p 안팎만 달라져서 약한 검증이다.
    검증 3    제품의 순서가 실제로 마신 횟수의 순서와 같은가(국민건강영양조사, 탄산음료·맥주·소주). 제로와 일반이 나뉘는 제품 단위다.
              매출이 아니라 마신 횟수이고 모든 곳에서 마신 것이다. 5건 미만인 제품은 가장 뒤로 본다.
    검증 2    품목 안에서 브랜드의 순서가 실제와 같은가. 종류별 가중치는 품목 안의 순서를 바꾸지 못하므로 보정과 무관한 검증이다.

재는 것:
    같은 제품을 다시 고른 비율   같은 손님에게 같은 매대를 다시 보여줬을 때(기준 3번의 모든 짝)
    같은 종류를 다시 고른 비율
    어긋난 정도                  종류별 금액 비중 차이의 절댓값을 더해 반으로 나눈 값. 0이면 실제와 같고 100이면 전혀 다르다
    브랜드 순서 일치             실제 순서가 다른 브랜드 짝 가운데 가상 손님의 선택 횟수 순서가 같은 짝의 비율. 횟수가 같으면 반만 세고,
                                 둘 다 한 번도 고르지 않은 짝은 뺀다
"""

import csv
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "data" / "experiments" / "pilot"
CLEAN = ROOT / "data" / "clean"

FIS_KIND = {"탄산음료": "탄산", "과채음료": "주스", "액상차": "차", "액상커피": "커피", "두유": "우유·단백", "단백질음료": "우유·단백",
            "우유": "우유·단백", "발효유": "우유·단백", "탁주": "막걸리", "맥주": "맥주", "소주": "소주"}

# 우리 매대의 상품명에 들어 있는 글자 -> (품목, 화면에 나온 브랜드 이름). 화면의 10위 안에 없는 브랜드는 "목록 밖"으로 둔다.
BRANDS = [
    ("코카콜라", "탄산음료", "코카콜라"), ("펩시", "탄산음료", "펩시"), ("칠성사이다", "탄산음료", "칠성사이다"), ("밀키스", "탄산음료", "밀키스"),
    ("환타", "탄산음료", "환타"), ("스프라이트", "탄산음료", "스프라이트"), ("나랑드", "탄산음료", "나랑드"), ("마운틴듀", "탄산음료", "목록 밖"),
    ("칸타타", "액상커피", "칸타타"), ("티오피", "액상커피", "맥심"), ("바리스타", "액상커피", "바리스타룰스"), ("스벅", "액상커피", "스타벅스"),
    ("조지아", "액상커피", "조지아"),
    ("하늘보리", "액상차", "하늘보리"), ("옥수수수염", "액상차", "옥수수수염차"), ("더하다", "액상차", "더하다"), ("실론티", "액상차", "실론티"),
    ("립톤", "액상차", "립톤"),
    ("델몬트", "과채음료", "델몬트"), ("갈아만든배", "과채음료", "갈아만든배"), ("미닛", "과채음료", "미닛메이드"),
    ("서울)흰우유", "우유", "서울우유"), ("빙그레)바나나우유", "우유", "바나나맛우유"), ("맛있는우유", "우유", "맛있는우유GT"),
    ("카스", "맥주", "카스"), ("테라", "맥주", "테라"), ("아사히", "맥주", "아사히"), ("하이네켄", "맥주", "하이네켄"), ("클라우드", "맥주", "클라우드"),
    ("한맥", "맥주", "목록 밖"), ("칭따오", "맥주", "목록 밖"), ("호가든", "맥주", "호가든"), ("곰표", "맥주", "목록 밖"),
    ("참이슬", "소주", "참이슬"), ("처음처럼(", "소주", "처음처럼"), ("진로", "소주", "진로"), ("새로", "소주", "새로"),
]


# 우리 매대의 상품명에 들어 있는 글자 -> 국민건강영양조사의 표준 제품(scripts/knhanes_beverage.py products). 위에서부터 처음 맞는 것을 쓴다.
# 브랜드가 아니라 제품 단위다(제로와 일반이 나뉜다). 조사에서 5건 미만이라 내보내지 않은 제품은 "5건 미만"으로 두고 가장 뒤로 본다.
KNHANES_PRODUCTS = [
    ("칠성사이다제로", "칠성사이다 제로"), ("칠성사이다", "칠성사이다"), ("펩시제로", "펩시 제로"), ("펩시콜라", "펩시콜라"),
    ("코카콜라제로", "코카콜라 제로"), ("코카콜라", "코카콜라"), ("스프라이트제로", "스프라이트 제로"), ("스프라이트", "스프라이트"),
    ("환타", "환타"), ("밀키스", "밀키스"), ("나랑드", "나랑드사이다"), ("마운틴듀", "5건 미만"),
    ("카스라이트", "카스 라이트"), ("카스제로", "5건 미만"), ("카스", "카스"), ("테라", "테라"), ("아사히", "아사히"), ("하이네켄", "하이네켄"),
    ("하이트제로", "하이트제로"), ("칭따오", "칭따오"), ("클라우드논알콜", "5건 미만"), ("클라우드", "5건 미만"), ("호가든", "5건 미만"),
    ("곰표", "5건 미만"), ("한맥", "5건 미만"),
    ("참이슬", "참이슬"), ("처음처럼(", "처음처럼"), ("새로", "새로"), ("진로라이트", "5건 미만"),
]


def knhanes_of(name: str):
    for key, standard in KNHANES_PRODUCTS:
        if key in name:
            return standard if standard != "5건 미만" else f"(5건 미만) {key}"  # 5건 미만인 제품끼리는 한데 묶지 않는다
    return None


def order_agreement(sim: Counter, real: dict, names: set, kind: dict = None) -> tuple:
    """실제 순서가 다른 짝 가운데 가상 손님의 선택 횟수 순서가 같은 짝의 비율. 횟수가 같으면 반, 둘 다 0이면 뺀다."""
    agree = total = 0.0
    wrong = []
    for a, b in combinations(sorted(names), 2):
        ra, rb = real.get(a, 0), real.get(b, 0)
        if kind and kind[a] != kind[b]:  # 같은 종류 안에서만 견준다(소주와 맥주의 횟수를 견주지 않는다)
            continue
        if ra == rb or sim[a] + sim[b] == 0:
            continue
        total += 1
        score = 0.5 if sim[a] == sim[b] else float((sim[a] > sim[b]) == (ra > rb))
        agree += score
        if score < 1:
            first, second = (a, b) if ra > rb else (b, a)
            wrong.append(f"{first}>{second}({sim[first]}:{sim[second]})")
    return agree, total, wrong


def read(path: Path) -> list:
    return list(csv.DictReader(open(path, encoding="utf-8")))


def real_share(year: int, shelf: str) -> dict:
    total = defaultdict(float)
    for r in read(CLEAN / f"fis_pos_{year}_cvs.csv"):
        if r["매대"] == shelf:
            total[FIS_KIND[r["품목"]]] += float(r["편의점 매출(백만원, 곱한 값)"])
    return {k: 100 * v / sum(total.values()) for k, v in total.items()}


def gap(a: dict, b: dict) -> float:
    return sum(abs(a.get(k, 0) - b.get(k, 0)) for k in set(a) | set(b)) / 2


def brand_of(name: str):
    for key, item, brand in BRANDS:
        if key in name:
            return item, brand
    return None


def measure(path: Path, shelf: str, products: dict, ranks: dict, knhanes: dict) -> dict:
    rows = [r for r in read(path) if r["유효"] == "예" and r["조건"] == "기준"]
    by_visit = defaultdict(dict)
    for r in rows:
        by_visit[r["방문"]][r["반복"]] = r["고른 제품"]
    kind = lambda p: products[p]["종류"] if p in products else p
    pairs = [(a, b) for picks in by_visit.values() for a, b in combinations([picks[k] for k in sorted(picks)], 2)]
    bought = [r["고른 제품"] for r in rows if r["고른 제품"] in products]

    # 종류별 금액 비중(실제 자료에 있는 종류만)
    r24, r25 = real_share(2024, shelf), real_share(2025, shelf)
    money = Counter()
    for p in bought:
        if kind(p) in r25:
            money[kind(p)] += int(products[p]["가격(원)"])
    sim = {k: 100 * money[k] / sum(money.values()) for k in r25}
    weight = {k: (r24[k] / sim[k] if sim[k] else 0) for k in r25}  # 2024년 자료로 맞춘다
    fixed = {k: sim[k] * weight[k] for k in r25}
    fixed = {k: 100 * v / sum(fixed.values()) for k, v in fixed.items()}

    # 브랜드 순서(품목 안)
    count = defaultdict(Counter)
    on_shelf = defaultdict(set)
    for name in products:
        if brand_of(name):
            on_shelf[brand_of(name)[0]].add(brand_of(name)[1])
    for p in bought:
        if brand_of(p):
            count[brand_of(p)[0]][brand_of(p)[1]] += 1
    agree = total = 0.0
    detail = []
    for item, names in sorted(on_shelf.items()):
        for a, b in combinations(sorted(names), 2):
            if a not in ranks[item] or b not in ranks[item]:  # 실제 금액을 받지 못한 브랜드는 견주지 않는다
                continue
            ra, rb = -ranks[item][a], -ranks[item][b]  # 금액이 클수록 앞
            if ra == rb:
                continue
            ca, cb = count[item][a], count[item][b]
            if ca + cb == 0:  # 둘 다 한 번도 고르지 않았으면 순서를 말할 수 없다
                continue
            total += 1
            score = 0.5 if ca == cb else float((ca > cb) == (ra < rb))
            agree += score
            if score < 1:
                first, second = (a, b) if ra < rb else (b, a)
                detail.append(f"{first}>{second}({count[item][first]}:{count[item][second]})")
    # 제품 순서(국민건강영양조사의 제품별 마신 횟수). 같은 표준 제품에 걸리는 우리 제품들의 선택은 더한다.
    kn_sim, kn_names, kn_kind = Counter(), set(), {}
    for name in products:
        if knhanes_of(name):
            kn_names.add(knhanes_of(name))
            kn_kind[knhanes_of(name)] = "맥주" if products[name]["종류"] == "논알콜" else products[name]["종류"]
    for p in bought:
        if knhanes_of(p):
            kn_sim[knhanes_of(p)] += 1
    kn_agree, kn_total, kn_wrong = order_agreement(kn_sim, knhanes, kn_names, kn_kind)
    return {
        "물은 횟수": len(rows),
        "같은 제품을 다시 고른 비율(%)": round(100 * sum(a == b for a, b in pairs) / len(pairs), 1),
        "같은 종류를 다시 고른 비율(%)": round(100 * sum(kind(a) == kind(b) for a, b in pairs) / len(pairs), 1),
        "사지 않음(%)": round(100 * sum(r["고른 제품"] == "사지 않음" for r in rows) / len(rows), 1),
        "어긋난 정도: 보정 전, 2025년과": round(gap(sim, r25), 1),
        "어긋난 정도: 2024년으로 보정 후, 2025년과": round(gap(fixed, r25), 1),
        "브랜드 순서 일치(%)": round(100 * agree / total, 1) if total else "",
        "브랜드 짝 수": int(total),
        "제품 순서 일치(%)": round(100 * kn_agree / kn_total, 1) if kn_total else "",
        "제품 짝 수": int(kn_total),
        "순서가 틀린 제품 짝(실제 순서, 가상 횟수)": " ".join(kn_wrong),
        "순서가 틀린 짝(실제 순서, 가상 횟수)": " ".join(detail),
    }


LABEL = {"_r0": "0차: 관계 없이(서술과 매대만)", "": "1차: 욕구·상황 연결, 꼭 사는 손님", "_r2": "2차: 사지 않아도 됨", "_r3": "3차: 매대 보강(우유·생수)",
         "_r4": "4차: 상품명을 손님이 보는 이름으로", "_r5": "5차(진단): 행사 표시를 모두 뗌"}


def main() -> None:
    products = {p["상품명"]: p for p in read(ROOT / "data" / "ours" / "shelf_products.csv")}
    ranks = defaultdict(lambda: defaultdict(float))  # 품목 -> 브랜드 -> 연 매출(백만원). 제조사가 둘인 브랜드는 더한다
    for r in read(CLEAN / "fis_pos_2025_brands.csv"):
        if r["구분"] == "브랜드":
            ranks[r["품목"]][r["이름"]] += float(r["연 매출(백만원, 모든 채널)"])
    knhanes = {r["표준 제품"]: int(r["마신 횟수"]) for r in read(CLEAN / "knhanes_2024_product_counts.csv")}
    out = []
    for shelf in ("음료", "주류"):
        for suffix, label in LABEL.items():
            for path in sorted(PILOT.glob(f"{shelf}_cli{suffix}*.csv")):
                model = path.stem[len(f"{shelf}_cli{suffix}"):]  # 비어 있으면 기본 모델(opus-5-5), 아니면 "_haiku-5-5"처럼 모델 이름
                if model and not model.startswith("_") or model.startswith("_r") or "report" in model:
                    continue
                on_shelf = {k: v for k, v in products.items() if v["매대"] == shelf}
                out.append({"매대": shelf, "조건": label + (f" [{model[1:]}]" if model else ""), **measure(path, shelf, on_shelf, ranks, knhanes)})
    keys = list(out[0])
    with open(PILOT / "reliability.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(out)
    hidden = [k for k in keys if k.startswith("순서가 틀린")]
    short = [k for k in keys if k not in hidden]
    lines = ["# 신뢰도: 일관성과 현실 적합성", "", "만드는 법과 뜻은 `scripts/reliability.py`의 머리말에 있다.", "",
             "| " + " | ".join(short) + " |", "|" + "---|" * len(short)]
    lines += ["| " + " | ".join(str(r[k]) for k in short) + " |" for r in out]
    for k in hidden:
        lines += ["", f"## {k}", ""] + [f"- {r['매대']} {r['조건']}: {r[k] or '없음'}" for r in out]
    (PILOT / "reliability.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
