"""상황 목록, 집단별 상황 비중, 상황이 바꾸는 욕구를 2024 국민건강영양조사 기록에서 만든다.

실행:
    uv run --with duckdb python scripts/build_occasions.py

입력:  data/raw/knhanes/hn24_24rc_subset.parquet   (scripts/knhanes_beverage.py extract 로 만든다)
출력:  data/ours/occasions.csv            상황의 이름, 정의, 전체 비중
       data/ours/occasion_weights.csv     성별·연령대마다 각 상황의 비중(손님에게 상황을 배정하는 확률)
       data/ours/occasion_drink_mix.csv   상황마다 마신 음료 종류의 비율(검증의 기준값)
       data/ours/occasion_needs.csv       상황이 욕구를 얼마나 올리고 내리는가(-2 ~ +2)와 근거

생각:
- 상황을 마음 상태("졸릴 때")로 정하지 않고 기록에 있는 것(끼니인지 간식인지, 시간대, 장소, 누구와)으로 정한다.
- 상황의 비중은 사람이 정하지 않는다. 그 집단이 실제로 마신 자리 가운데 그 상황이 차지하는 비율이다.
- 상황이 욕구를 바꾸는 크기도 기록에서 구한다. 어떤 상황에서 어떤 종류의 음료를 평소보다 많이 마셨는지를 보고,
  그 종류가 채워주는 욕구를 그만큼 올린다(TYPE_NEEDS). 종류와 욕구의 연결은 우리의 판단이다.
- 기록으로 구할 수 없는 것은 "정의"(상황의 정의에서 바로 나오는 것)와 "가정"으로 따로 표시한다.
- 응답자를 반으로 나눠 따로 구한 값이 서로 닮았는지 본다(반쪽 검증). 닮지 않으면 우연이다.

세는 단위: 한 사람의 한 번의 식사·간식 자리에서 한 종류의 음료를 마신 것 1건. 19세 이상, 가중치 wt_ntr.
코드의 뜻은 자료 내용으로 짐작한 것이다(scripts/knhanes_beverage.py 머리말).
"""

import csv
import hashlib
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SUBSET = ROOT / "data" / "raw" / "knhanes" / "hn24_24rc_subset.parquet"
OURS = ROOT / "data" / "ours"
MIN_GROUP = 40  # 집단의 마신 자리가 이보다 적으면 연령대 전체의 비중을 쓴다

DRINK_TYPE = """
CASE
  WHEN N_KINDG1 = '22' AND N_FNAME3 LIKE '소주%' THEN '소주'
  WHEN N_KINDG1 = '22' AND N_FNAME3 LIKE '맥주%' THEN '맥주'
  WHEN N_KINDG1 = '22' AND N_FNAME3 LIKE '막걸리%' THEN '막걸리'
  WHEN N_KINDG1 = '22' THEN '기타 주류'
  WHEN N_KINDG1 = '21' AND N_FNAME3 LIKE '탄산음료,저칼로리%' THEN '탄산음료(저칼로리)'
  WHEN N_KINDG1 = '21' AND N_FNAME3 LIKE '탄산음료%' THEN '탄산음료'
  WHEN N_KINDG1 = '21' AND N_FNAME3 LIKE '커피,커피만%' THEN '커피(커피만)'
  WHEN N_KINDG1 = '21' AND N_FNAME3 LIKE '커피%' THEN '커피(당·프림 등 첨가)'
  WHEN N_KINDG1 = '21' AND (N_FNAME3 LIKE '과일음료%' OR N_FNAME3 LIKE '채소음료%') THEN '과일·채소음료'
  WHEN N_KINDG1 = '21' AND N_FNAME3 LIKE '%차%' THEN '차'
  WHEN N_KINDG1 = '21' THEN '기타 음료'
  WHEN N_FNAME3 IN ('우유', '요구르트', '유산균음료', '두유')
       AND (N_DNAME LIKE '%우유' OR N_DNAME LIKE '%두유%' OR N_DNAME LIKE '%요구르트%' OR N_DNAME LIKE '%요거트%') THEN '우유·두유·발효유'
END
"""

# (매대, 번호, 이름, 풀어 쓴 설명, 조건)  위에서부터 먼저 맞는 상황으로 본다.
#   snack: 끼니가 아닌 간식 자리인가   place: 집 / 일터 / 밖   alone: 혼자인가   early: 오전 11시 전인가
OCCASIONS = [
    ("음료", "D1", "일하다가 혼자 한 잔", "직장이나 학교에서 끼니 사이에 혼자 마신다", lambda s: s["snack"] and s["place"] == "일터" and s["alone"]),
    ("음료", "D2", "일터에서 함께 쉬면서", "직장이나 학교에서 끼니 사이에 동료와 마신다", lambda s: s["snack"] and s["place"] == "일터"),
    ("음료", "D3", "집에서 혼자 오전에", "집에서 오전에 끼니와 따로 혼자 마신다", lambda s: s["snack"] and s["place"] == "집" and s["alone"] and s["early"]),
    ("음료", "D4", "집에서 혼자 낮이나 저녁에", "집에서 낮이나 저녁에 끼니와 따로 혼자 마신다", lambda s: s["snack"] and s["place"] == "집" and s["alone"]),
    ("음료", "D5", "집에서 가족과 간식 자리", "집에서 끼니 사이에 가족과 마신다", lambda s: s["snack"] and s["place"] == "집"),
    ("음료", "D6", "밖에서 쉬거나 사람을 만나며", "카페, 음식점, 이동 중에 끼니와 따로 마신다", lambda s: s["snack"]),
    ("음료", "D7", "밖에서 식사와 함께", "음식점, 직장, 학교에서 식사에 곁들여 마신다", lambda s: s["place"] != "집"),
    ("음료", "D8", "집에서 식사와 함께", "집에서 식사에 곁들여 마신다", lambda s: True),
    ("주류", "L1", "밖에서 사람들과 식사하며", "음식점 등에서 식사하며 함께 마신다", lambda s: not s["snack"] and s["place"] != "집" and not s["alone"]),
    ("주류", "L2", "집에서 가족과 식사하며", "집에서 식사하며 함께 마신다", lambda s: not s["snack"] and not s["alone"]),
    ("주류", "L3", "식사와 따로 사람들과 한잔", "끼니가 아닌 자리에서 함께 마신다(2차, 집에서 한잔)", lambda s: not s["alone"]),
    ("주류", "L4", "혼자 마실 때", "집이나 밖에서 혼자 마신다", lambda s: True),
]

# 음료 종류가 채워주는 욕구(우리의 판단). 값은 채워주는 정도: 2 잘 채움, 1 조금 채움, -1 거스름.
TYPE_NEEDS = {
    "커피(커피만)": {"B01": 2, "N05": 1, "N06": 1},
    "커피(당·프림 등 첨가)": {"B01": 2, "N07": 1},
    "탄산음료": {"N09": 2, "N07": 2, "B03": 1, "N05": -1},
    "탄산음료(저칼로리)": {"N09": 2, "N05": 2, "B03": 1, "N06": -1},
    "과일·채소음료": {"N07": 2, "B04": 1},
    "차": {"B03": 2, "N05": 1, "N06": 1},
    "우유·두유·발효유": {"B04": 2},
    "소주": {"A02": 2, "N09": 2},
    "맥주": {"N09": 2, "A01": 1},
    "막걸리": {"N09": 1},
    "기타 주류": {"A05": 2},
}
SHELF_OF = lambda drink: "주류" if drink in ("소주", "맥주", "막걸리", "기타 주류") else "음료"

# 기록으로 구할 수 없어 따로 넣는 것: (상황, 욕구, 크기, 종류, 설명)
EXTRA = [
    ("L1", "A03", 2, "정의", "함께 마시는 자리"), ("L2", "A03", 2, "정의", "함께 마시는 자리"), ("L3", "A03", 2, "정의", "함께 마시는 자리"),
    ("L1", "A04", -1, "정의", "함께 마시는 자리"), ("L2", "A04", -1, "정의", "함께 마시는 자리"), ("L3", "A04", -1, "정의", "함께 마시는 자리"),
    ("L4", "A04", 2, "정의", "혼자 마시는 자리"), ("L4", "A03", -1, "정의", "혼자 마시는 자리"),
    ("D1", "N03", -1, "가정", "혼자 일터에서는 하나 더 받아도 들고 있기 번거롭다"),
    ("D6", "N03", -1, "가정", "밖에서 이동 중에는 하나 더 받아도 짐이 된다"),
    ("D2", "N03", 1, "가정", "함께 있으면 하나 더 받은 것을 나눌 수 있다"),
    ("D5", "N03", 1, "가정", "집에서 가족과 나누거나 두고 마실 수 있다"),
    ("D8", "N03", 1, "가정", "집에 두고 마실 수 있다"),
    ("L2", "N03", 1, "가정", "집에 두고 마실 수 있다"), ("L3", "N03", 1, "가정", "여럿이면 묶음이 쓸모 있다"),
]


def age_band(age: float) -> str:
    return "19-29" if age < 30 else "30-39" if age < 40 else "40-49" if age < 50 else "50-59" if age < 60 else "60-69" if age < 70 else "70+"


def scores(rows: list, shelf: str) -> dict:
    """상황마다 욕구가 평소보다 얼마나 올라가는지. 종류의 비율이 전체보다 높은 만큼 그 종류가 채우는 욕구를 올린다."""
    total, by_occ = defaultdict(float), defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["shelf"] == shelf:
            total[r["drink"]] += r["w"]
            by_occ[r["occ"]][r["drink"]] += r["w"]
    all_weight = sum(total.values())
    out = {}
    for occ, mix in by_occ.items():
        occ_weight = sum(mix.values())
        for drink in total:
            gap = mix[drink] / occ_weight - total[drink] / all_weight
            for need, degree in TYPE_NEEDS.get(drink, {}).items():
                out[(occ, need)] = out.get((occ, need), 0.0) + gap * degree
    return out


def drink_records(*, retail_foods: bool = False) -> list[dict]:
    food_filter = "AND N_MTYPE IN (12, 21)" if retail_foods else ""
    with duckdb.connect() as con:
        fetched = con.execute(f"""
            WITH raw AS (SELECT *, {DRINK_TYPE} AS drink FROM read_parquet(?) WHERE age >= 19 {food_filter})
            SELECT DISTINCT ID, sex, age, wt_ntr, drink, N_MEAL, N_MEAL_T, N_MEAL_P, N_MEAL_W
            FROM raw WHERE drink IS NOT NULL
        """, [str(SUBSET)]).fetchall()
    rows = []
    for pid, sex, age, w, drink, meal, time, place, companion in fetched:
        hour = int(time[:2]) if time and time[:2].isdigit() else 12
        sitting = {"snack": meal == 4, "place": "집" if place == 1 else "일터" if place == 2 else "밖", "alone": companion == 1, "early": 5 <= hour < 11}
        shelf = SHELF_OF(drink)
        occ = next(code for s, code, *_, rule in OCCASIONS if s == shelf and rule(sitting))
        rows.append({"id": pid, "sex": "남자" if sex == 1 else "여자", "band": age_band(age), "w": w, "drink": drink, "shelf": shelf, "occ": occ})
    return rows


def main() -> None:
    rows = drink_records()
    names = {code: name for _, code, name, *_ in OCCASIONS}
    needs = {r["번호"]: r["욕구"] for r in csv.DictReader(open(OURS / "needs.csv", encoding="utf-8"))}

    # 1. 상황 목록과 전체 비중
    weight, count = defaultdict(float), defaultdict(int)
    for r in rows:
        weight[(r["shelf"], r["occ"])] += r["w"]
        count[(r["shelf"], r["occ"])] += 1
    shelf_weight = {s: sum(v for (sh, _), v in weight.items() if sh == s) for s in ("음료", "주류")}
    with open(OURS / "occasions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["매대", "번호", "상황", "풀어 쓴 설명", "전체 비중(%)", "마신 자리 수", "근거"])
        for shelf, code, name, text, _ in OCCASIONS:
            share = 100 * weight[(shelf, code)] / shelf_weight[shelf]
            writer.writerow([shelf, code, name, text, round(share, 1), count[(shelf, code)], "2024 국민건강영양조사 식품섭취조사"])
            print(f"{shelf} {code} {name}: {share:.1f}% (n={count[(shelf, code)]})")

    # 2. 집단별 비중
    group = defaultdict(lambda: defaultdict(float))
    size = defaultdict(int)
    for r in rows:
        for key in ((r["shelf"], r["sex"], r["band"]), (r["shelf"], "전체", r["band"])):
            group[key][r["occ"]] += r["w"]
            size[key] += 1
    with open(OURS / "occasion_weights.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["매대", "성별", "연령대", "번호", "상황", "비중(%)", "근거로 쓴 마신 자리 수", "쓴 집단"])
        for shelf in ("음료", "주류"):
            for sex in ("남자", "여자"):
                for band in ("19-29", "30-39", "40-49", "50-59", "60-69", "70+"):
                    key = (shelf, sex, band)
                    used = key if size[key] >= MIN_GROUP else (shelf, "전체", band)
                    total = sum(group[used].values())
                    for s, code, name, *_ in OCCASIONS:
                        if s == shelf:
                            writer.writerow([shelf, sex, band, code, name, round(100 * group[used][code] / total, 1), size[used],
                                             "성별·연령대" if used == key else "연령대 전체(표본이 적어서)"])
    small = [k for k in size if k[1] != "전체" and size[k] < MIN_GROUP]
    print("표본이 적어 연령대 전체로 대신한 집단:", small)

    # 3. 상황마다 마신 종류의 비율
    mix = defaultdict(lambda: defaultdict(float))
    for r in rows:
        mix[(r["shelf"], r["occ"])][r["drink"]] += r["w"]
        mix[(r["shelf"], "전체")][r["drink"]] += r["w"]
    with open(OURS / "occasion_drink_mix.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["매대", "번호", "상황", "음료 종류", "비율(%)"])
        for (shelf, code), drinks in sorted(mix.items()):
            total = sum(drinks.values())
            for drink, w in sorted(drinks.items(), key=lambda x: -x[1]):
                writer.writerow([shelf, code, names.get(code, "전체"), drink, round(100 * w / total, 1)])

    # 4. 상황이 바꾸는 욕구 + 반쪽 검증
    half = lambda r: int(hashlib.md5(str(r["id"]).encode()).hexdigest(), 16) % 2
    out_rows = []
    for shelf in ("음료", "주류"):
        full = scores(rows, shelf)
        a = scores([r for r in rows if half(r) == 0], shelf)
        b = scores([r for r in rows if half(r) == 1], shelf)
        scale = 2 / max(abs(v) for v in full.values())
        keys = [k for k in full if k in a and k in b]
        mean_a, mean_b = sum(a[k] for k in keys) / len(keys), sum(b[k] for k in keys) / len(keys)
        cov = sum((a[k] - mean_a) * (b[k] - mean_b) for k in keys)
        corr = cov / (sum((a[k] - mean_a) ** 2 for k in keys) ** 0.5 * sum((b[k] - mean_b) ** 2 for k in keys) ** 0.5)
        strong = [k for k in keys if abs(full[k] * scale) >= 0.5]
        agree = sum(1 for k in strong if a[k] * b[k] > 0)
        print(f"{shelf} 반쪽 검증: 상관 {corr:.2f}, 크기 0.5 이상인 {len(strong)}개 가운데 방향이 같은 것 {agree}개")
        for (occ, need), value in sorted(full.items()):
            shift = round(value * scale, 1)
            if abs(shift) >= 0.3 and need in needs:
                same = "예" if a.get((occ, need), 0) * b.get((occ, need), 0) > 0 else "아니오"
                out_rows.append([shelf, occ, names[occ], need, needs[need], shift, "자료", "이 상황에서 마신 종류의 비율이 평소와 다른 만큼", same])
    for occ, need, shift, kind, text in EXTRA:
        out_rows.append([SHELF_OF("소주") if occ.startswith("L") else "음료", occ, names[occ], need, needs[need], shift, kind, text, ""])
    out_rows.sort(key=lambda r: (r[0], r[1], -abs(r[5])))
    with open(OURS / "occasion_needs.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["매대", "번호", "상황", "욕구 번호", "욕구", "바뀌는 크기(-2~+2)", "근거 종류", "설명", "반쪽 둘의 방향이 같은가"])
        writer.writerows(out_rows)
    for shelf, code, name, *_ in OCCASIONS:
        items = [f"{r[4]} {r[5]:+}" + ("" if r[6] == "자료" else f"({r[6]})") for r in out_rows if r[1] == code]
        top = sorted(mix[(shelf, code)].items(), key=lambda x: -x[1])[:3]
        total = sum(mix[(shelf, code)].values())
        print(f"  {code} {name} | 많이 마신 것: " + ", ".join(f"{d} {100 * w / total:.0f}%" for d, w in top) + " | " + ", ".join(items))


if __name__ == "__main__":
    main()
