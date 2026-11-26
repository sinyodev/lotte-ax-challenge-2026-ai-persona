"""손님 8,000명에게 실제 조사 응답자 한 명의 답을 통째로 입히고, 거기서 욕구의 세기를 정한다.

실행 (두 단계):
    uv run --with openpyxl python scripts/assign_persona_needs.py extract
    uv run --with duckdb python scripts/assign_persona_needs.py assign

입력:  data/raw/krei-food-survey/raw_2025/(data_가중) 2025 식품소비행태조사_성인가구원.xlsx
       data/clean/personas_8000.parquet
중간:  data/raw/krei-food-survey/adult_2025_donors.csv   (응답자 단위. 저장소에 올리지 않는다)
출력:  data/ours/persona_profiles.csv   (손님마다 입힌 응답자의 답. 응답자 단위 값이라 저장소에 올리지 않는다)
       data/ours/persona_needs.csv      (손님마다 욕구 17개의 세기 0~3. 저장소에 올린다)
       data/ours/persona_needs_report.md (입힌 결과 점검)

방법:
- 손님과 성별·연령대가 같은 응답자 가운데 한 명을 가중치에 비례한 확률로 고른다.
  고르는 순서는 md5(손님 uuid + 씨앗)로 정하므로 다시 돌려도 같은 응답자가 붙는다.
- 문항별 비율을 따로 입히지 않고 한 사람의 답을 통째로 가져온다. "제로 탄산을 좋아하는데 제로 음료를
  먹어본 적 없는" 식의 모순이 생기지 않는다.
- 욕구의 세기는 아래 규칙으로 정한다(0 없음, 1 약함, 2 보통, 3 셈). 규칙은 우리의 판단이다.
  조사 문항이 그 욕구를 직접 묻지 않아 비슷한 문항으로 대신한 것은 NEEDS의 "대리"에 표시했다.

- 손님의 서술에 술 이야기가 나오면 술을 마시는 응답자 가운데서만 고른다. 처음에는 성별·연령대만 맞췄는데,
  서술에 술이 나오는 525명 가운데 90명(17%)에게 술을 마시지 않는 응답자가 붙어서 고쳤다.

한계: 성별·연령대(와 술 여부)만 맞춘다. 손님의 직업, 지역, 다른 서술과 응답자의 답은 어긋날 수 있다.
"""

import bisect
import csv
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "raw" / "krei-food-survey" / "raw_2025" / "(data_가중) 2025 식품소비행태조사_성인가구원.xlsx"
DONORS = ROOT / "data" / "raw" / "krei-food-survey" / "adult_2025_donors.csv"
PERSONAS = ROOT / "data" / "clean" / "personas_8000.parquet"
OURS = ROOT / "data" / "ours"
SEED = "lotte-ax-2026-11-17-donor"

COLUMNS = [
    "id", "psfwt", "SQ1", "SQ2", "A15_1", "A15_2", "A15_3", "A16", "A16_1", "A19_1", "A19_4",
    "A19_1_1", "A19_1_2", "A19_2_1", "A19_2_2", "H1_4", "H1_5", "H1_6", "H1_7", "H1_8",
    "BA2", "BA3", "BA4", "BA5", "BA5_1", "BA7", "C1", "A20",
    "A1_2_3_1", "A1_2_3_2", "A1_2_3_3",  # 저녁 식사를 가족과, 친구·동료와, 혼자 먹은 횟수(주 7회 중)
]

DRINK = {1: "100% 과일 주스", 2: "저과즙 음료", 3: "흰우유", 4: "가공우유", 5: "발효유", 6: "두유·아몬드유", 7: "가당 탄산음료",
         8: "제로 탄산음료", 9: "이온음료", 10: "녹차·곡물차", 11: "기능성 음료", 12: "탄산수", 13: "인스턴트·캔 커피",
         14: "커피전문점 커피", 15: "음료전문점 음료", 16: "기타", 17: "물 이외에는 마시지 않음"}
ALCOHOL = {1: "소주", 2: "맥주", 3: "막걸리", 4: "와인", 5: "양주", 6: "전통주", 7: "칵테일(하이볼 등)", 8: "무알콜 주류", 9: "기타"}
FREQ = {1: "매일", 2: "주 4~6일", 3: "주 2~3일", 4: "주 1일", 5: "2주에 1일", 6: "한 달에 1일", 7: "2~3달에 1일", 8: "그보다 드물게", 9: "마시지 않음", 10: "기타"}
ZERO = {1: "주 1회 이상", 2: "월 2~3회", 3: "월 1회", 4: "월 1회 미만", 9: "먹어본 적 없음"}

# (번호, 욕구, 근거로 쓴 문항, 대리 여부)
NEEDS = [
    ("N01", "익숙한 것 고르기", "H1(6) 새로운 음식을 좋아한다(거꾸로)", "대리"),
    ("N02", "돈을 적게 쓰기", "H1(7) 가격을 비교해 산다, H1(5) 가격보다 맛(거꾸로), BA7 소득", ""),
    ("N03", "덤으로 이득 보기", "H1(7) 가격을 비교해 산다, H1(8) 가격 대비 품질을 따진다", "대리"),
    ("N04", "양에 비해 싼 것", "H1(8) 가격 대비 품질을 따진다", "대리"),
    ("N05", "당과 열량 걱정 덜기", "A19 제로 음료·주류 빈도, BA2 다이어트 관심", ""),
    ("N06", "감미료와 첨가물 피하기", "A19-2 제로를 먹지 않는 이유(감미료 걱정, 부작용), BA5 건강 관심", ""),
    ("N07", "맛이 확실한 것 즐기기", "H1(5) 가격보다 맛, A19-2 제로를 먹지 않는 이유(맛)", ""),
    ("N08", "새로운 것 맛보기", "H1(6) 새로운 음식을 좋아한다, H1(4) 다양한 맛을 원한다", ""),
    ("N09", "음식과 어울리게 마시기", "A15 좋아하는 음료에 탄산이 있는가, A16 음주 빈도", "대리"),
    ("B01", "정신이 들게 하기", "A15 좋아하는 음료에 커피가 있는가", "대리"),
    ("B03", "달지 않게 깔끔하게 마시기(갈증 풀기)", "A15 좋아하는 음료에 차·탄산수가 있거나 물만 마시는가", ""),
    ("B04", "몸에 좋은 성분 챙기기", "BA5-1 건강에 시간·비용을 쓴다, BA4 규칙적 운동, A15 우유·두유·기능성 음료", ""),
    ("A01", "가볍게 마시기", "A16 음주 빈도, A16-1 좋아하는 술(무알콜), A19 제로 주류", ""),
    ("A02", "진하게 마시기", "A16-1 좋아하는 술(소주·양주), A16 음주 빈도", "대리"),
    ("A03", "여럿이 나눠 마시기", "A1-2 저녁을 친구·동료와 먹은 횟수, A20 개인 외식 여부", "대리"),
    ("A04", "혼자 한 캔으로 끝내기", "A1-2 저녁을 혼자 먹은 횟수", "대리"),
    ("A05", "조금 특별하게 마시기", "A16-1 좋아하는 술(와인·양주·전통주·칵테일), H1(6) 새로운 음식을 좋아한다", ""),
]


def num(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def level(score: float) -> int:
    """5점 척도(또는 그 평균)를 세기 0~3으로 바꾼다."""
    return 0 if score < 1.75 else 1 if score < 2.75 else 2 if score < 3.75 else 3


def strengths(d: dict) -> dict:
    g = lambda key: num(d[key])
    drinks = [g("A15_1"), g("A15_2"), g("A15_3")]
    first = drinks[0]
    drinks_alcohol = g("A16") not in (9, 0)
    often = g("A16") in (1, 2, 3, 4)            # 주 1일 이상
    rarely = g("A16") in (6, 7, 8)              # 한 달에 1일 이하
    zero_drink, zero_alcohol = g("A19_1"), g("A19_4")
    no_zero_reasons = {g("A19_2_1"), g("A19_2_2")}
    s = {}
    s["N01"] = 4 - level(g("H1_6")) if g("H1_6") else 2
    s["N01"] = max(1, min(3, s["N01"]))
    s["N02"] = min(3, level((g("H1_7") + 6 - g("H1_5")) / 2) + (1 if 0 < g("BA7") <= 3 else 0))
    s["N03"] = level((g("H1_7") + g("H1_8")) / 2)
    s["N04"] = level(g("H1_8"))
    s["N05"] = 3 if zero_drink == 1 or zero_alcohol == 1 else 2 if zero_drink in (2, 3) or zero_alcohol in (2, 3) or g("BA2") >= 4 else 1 if g("BA2") == 3 or zero_drink == 4 else 0
    s["N06"] = 3 if no_zero_reasons & {3, 4} else 0 if zero_drink in (1, 2) else 2 if g("BA5") >= 4 and zero_drink == 9 else 1
    s["N07"] = max(level(g("H1_5")), 3 if 2 in no_zero_reasons else 0)
    s["N08"] = level((g("H1_6") + g("H1_4")) / 2)
    s["N09"] = 3 if first in (7, 8) else 2 if set(drinks) & {7, 8} or often else 1
    s["B01"] = 3 if first in (13, 14) else 2 if set(drinks) & {13, 14} else 1
    s["B03"] = 3 if first in (10, 12, 17) else 2 if set(drinks) & {10, 12} else 1 if set(drinks) & {8, 9} else 0
    s["B04"] = min(3, (2 if g("BA5_1") >= 4 else 1 if g("BA5_1") == 3 else 0) + (1 if g("BA4") == 1 else 0) + (1 if set(drinks) & {3, 6, 11} else 0))
    if not drinks_alcohol:
        s.update({"A01": 0, "A02": 0, "A03": 0, "A04": 0, "A05": 0})
    else:
        fav = g("A16_1")
        s["A01"] = 3 if fav == 8 or zero_alcohol in (1, 2) else 2 if rarely or zero_alcohol in (3, 4) else 1
        s["A02"] = 3 if fav in (1, 5) and often else 2 if fav in (1, 5) else 1 if often else 0
        s["A03"] = 3 if g("A1_2_3_2") >= 2 else 2 if g("A1_2_3_2") == 1 or g("A20") == 1 else 1
        s["A04"] = 3 if g("A1_2_3_3") >= 4 else 2 if g("A1_2_3_3") >= 1 else 1
        s["A05"] = 3 if fav in (4, 5, 6, 7) else 2 if g("H1_6") >= 4 else 1
    return s


def extract() -> None:
    import openpyxl

    sheet = openpyxl.load_workbook(SOURCE, read_only=True)["Numeric"]
    rows = sheet.iter_rows(values_only=True)
    header = [str(c) if c is not None else "" for c in next(rows)]
    index = [header.index(c) for c in COLUMNS]
    count = 0
    with open(DONORS, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for row in rows:
            if row[header.index("psfwt")] is not None:
                writer.writerow([row[i] for i in index])
                count += 1
    print(f"응답자 {count:,}명 -> {DONORS.relative_to(ROOT)}")


def age_band(age: int) -> str:
    return "19-29" if age < 30 else "30-39" if age < 40 else "40-49" if age < 50 else "50-59" if age < 60 else "60-69" if age < 70 else "70+"


def assign() -> None:
    import duckdb

    pools = defaultdict(list)
    for d in csv.DictReader(open(DONORS, encoding="utf-8")):
        pools[("남자" if num(d["SQ1"]) == 1 else "여자", age_band(num(d["SQ2"])))].append(d)
    # 서술에 술 이야기가 나오는 손님에게는 술을 마시는 응답자만 붙인다(서술과 답이 어긋나지 않게).
    for key in list(pools):
        pools[key + ("술",)] = [d for d in pools[key] if num(d["A16"]) != 9]
    cumulative = {}
    for key, donors in pools.items():
        total, running = 0.0, []
        for d in donors:
            total += float(d["psfwt"])
            running.append(total)
        cumulative[key] = (running, total)

    personas = duckdb.sql(f"SELECT uuid, sex, age, age_band, pool, persona, culinary_persona FROM '{PERSONAS.as_posix()}' ORDER BY uuid").fetchall()
    profiles, needs_rows, mismatch = [], [], Counter()
    for uuid, sex, age, band, pool, persona, culinary in personas:
        text = (persona or "") + (culinary or "")
        says_alcohol = any(w in text for w in ("소주", "맥주", "막걸리", "와인", "하이볼", "위스키", "술자리", "반주"))
        key = (sex, band, "술") if says_alcohol else (sex, band)
        running, total = cumulative[key]
        point = int(hashlib.md5((uuid + SEED).encode()).hexdigest()[:12], 16) / 16 ** 12 * total
        d = pools[key][min(bisect.bisect_left(running, point), len(running) - 1)]
        s = strengths(d)
        mismatch["서술에 술이 나오는데 응답자는 술을 마시지 않음"] += says_alcohol and num(d["A16"]) == 9
        mismatch["서술에 술이 나오는 손님"] += says_alcohol
        profiles.append([
            uuid, sex, age, band, pool, d["id"],
            DRINK.get(num(d["A15_1"]), ""), DRINK.get(num(d["A15_2"]), ""), DRINK.get(num(d["A15_3"]), ""),
            FREQ.get(num(d["A16"]), ""), ALCOHOL.get(num(d["A16_1"]), ""), ZERO.get(num(d["A19_1"]), ""), ZERO.get(num(d["A19_4"]), ""),
            num(d["BA7"]), num(d["BA2"]), num(d["BA5"]), "예" if num(d["BA4"]) == 1 else "아니오",
        ])
        needs_rows.append([uuid, sex, band, pool, "예" if num(d["A16"]) != 9 else "아니오"] + [s[code] for code, *_ in NEEDS])

    with open(OURS / "persona_profiles.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["uuid", "성별", "나이", "연령대", "풀", "입힌 응답자 id", "좋아하는 음료 1순위", "2순위", "3순위", "음주 빈도",
                         "좋아하는 술", "제로 음료 빈도", "제로 주류 빈도", "소득 구간(1~12)", "다이어트 관심(1~5)", "건강 관심(1~5)", "규칙적 운동"])
        writer.writerows(profiles)
    with open(OURS / "persona_needs.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["uuid", "성별", "연령대", "풀", "술을 마심"] + [code for code, *_ in NEEDS])
        writer.writerows(needs_rows)

    # 점검 보고서
    lines = ["# 손님의 욕구 점검", "", "`scripts/assign_persona_needs.py`가 만든 파일이다. 손으로 고치지 않는다.", "",
             f"- 손님 {len(personas):,}명에게 2025 식품소비행태조사 성인 응답자 {sum(len(v) for k, v in pools.items() if len(k) == 2):,}명 가운데 한 명씩을 입혔다(성별·연령대가 같은 사람, 가중치에 비례).",
             f"- 한 번 이상 쓰인 응답자: {len({p[5] for p in profiles}):,}명",
             f"- 술을 마시는 손님: {sum(r[4] == '예' for r in needs_rows):,}명 ({100 * sum(r[4] == '예' for r in needs_rows) / len(needs_rows):.1f}%). 조사 전체에서는 72.2%다.",
             f"- 서술에 술 이야기가 나오는 손님 {mismatch['서술에 술이 나오는 손님']:,}명 가운데 입힌 응답자가 술을 마시지 않는 경우: {mismatch['서술에 술이 나오는데 응답자는 술을 마시지 않음']:,}명. 서술에 술이 나오면 술을 마시는 응답자만 붙였으므로 0이어야 한다.",
             "", "## 욕구별 세기 분포 (손님 수)", "", "| 번호 | 욕구 | 없음(0) | 약함(1) | 보통(2) | 셈(3) | 근거로 쓴 문항 | 대리 |", "|---|---|---|---|---|---|---|---|"]
    print(f"손님 {len(personas):,}명, 쓰인 응답자 {len({p[5] for p in profiles}):,}명, 어긋남 {dict(mismatch)}")
    for i, (code, name, basis, proxy) in enumerate(NEEDS):
        count = Counter(r[5 + i] for r in needs_rows)
        lines.append(f"| {code} | {name} | {count[0]} | {count[1]} | {count[2]} | {count[3]} | {basis} | {proxy} |")
        print(f"  {code} {name}: {[count[k] for k in range(4)]}")
    lines += ["", "## 연령대별로 달라지는가 (세기 2 이상인 손님의 비율 %)", "", "| 욕구 | 19-29 | 30-39 | 40-49 | 50-59 | 60-69 | 70+ |", "|---|---|---|---|---|---|---|"]
    bands = ["19-29", "30-39", "40-49", "50-59", "60-69", "70+"]
    for i, (code, name, *_ ) in enumerate(NEEDS):
        cells = []
        for band in bands:
            group = [r for r in needs_rows if r[2] == band]
            cells.append(f"{100 * sum(r[5 + i] >= 2 for r in group) / len(group):.0f}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
        print(f"  {name}: " + " ".join(cells))
    (OURS / "persona_needs_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"extract": extract, "assign": assign}[sys.argv[1] if len(sys.argv) > 1 else "assign"]()
