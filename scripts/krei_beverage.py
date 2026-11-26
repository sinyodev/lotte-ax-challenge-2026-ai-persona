"""2025 식품소비행태조사 성인 가구원 원시자료에서 음료·주류·제로식품 문항을 집계한다.

실행:
    uv run --with openpyxl python scripts/krei_beverage.py

입력:  data/raw/krei-food-survey/raw_2025/(data_가중) 2025 식품소비행태조사_성인가구원.xlsx
출력:  data/clean/krei_2025_beverage_distributions.csv   (집단별 가중 비율. 응답자 단위 자료는 내보내지 않는다)
       data/clean/krei_2025_beverage_codebook.csv        (쓴 문항의 이름과 보기)

쓰는 문항:
    A15_1~3   가장 좋아하는 음료 1~3순위
    A16       술을 마시는 빈도 (무알콜 주류 포함)
    A16_1     가장 좋아하는 술
    A19_1     제로 음료를 먹는 빈도        A19_4   제로 주류를 먹는 빈도
    A19_1_1~2 제로식품을 먹은 이유 1~2순위   A19_2_1~2 먹지 않은 이유 1~2순위
가중치: psfwt
"""

import csv
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "raw" / "krei-food-survey" / "raw_2025" / "(data_가중) 2025 식품소비행태조사_성인가구원.xlsx"
OUT_DIR = ROOT / "data" / "clean"

QUESTIONS = ["A15_1", "A15_2", "A15_3", "A16", "A16_1", "A19_1", "A19_4", "A19_1_1", "A19_1_2", "A19_2_1", "A19_2_2"]
DEMOGRAPHICS = ["SQ1", "SQ2", "SQ2_range"]
WEIGHT = "psfwt"


def age_band(age: float) -> str:
    if age < 30:
        return "19-29"
    if age < 40:
        return "30-39"
    if age < 50:
        return "40-49"
    if age < 60:
        return "50-59"
    if age < 70:
        return "60-69"
    return "70+"


def main() -> None:
    wb = openpyxl.load_workbook(SOURCE, read_only=True)

    # 문항 이름과 보기
    labels = {}
    for sheet in wb.worksheets:
        if sheet.title.lower().startswith("variable"):
            for name, label in sheet.iter_rows(min_row=2, max_col=2, values_only=True):
                if name:
                    labels[str(name)] = str(label)
    codes = defaultdict(dict)
    for sheet in wb.worksheets:
        if sheet.title.startswith("CodeBook"):
            current = None
            for name, value, label in sheet.iter_rows(min_row=2, max_col=3, values_only=True):
                if name:
                    current = str(name)
                if current and value is not None:
                    codes[current][str(value).split(".")[0]] = str(label)

    wanted = QUESTIONS + DEMOGRAPHICS + [WEIGHT]
    for name in wanted:
        print(f"{name}: {labels.get(name)} | 보기 {dict(list(codes.get(name, {}).items())[:20])}")

    # 응답 읽기
    sheet = wb["Numeric"]
    rows = sheet.iter_rows(values_only=True)
    header = [str(c) if c is not None else "" for c in next(rows)]
    index = {name: header.index(name) for name in wanted}
    people = []
    for row in rows:
        if row[index[WEIGHT]] is None:
            continue
        people.append({name: row[i] for name, i in index.items()})
    print(f"응답자 {len(people):,}명")

    sex_label = codes.get("SQ1", {})
    results = []  # (문항, 집단 종류, 집단, 보기, 가중 비율, 응답자 수)

    def tabulate(question: str, group_name: str, group_of) -> None:
        totals = defaultdict(float)
        counts = defaultdict(float)
        sizes = defaultdict(int)
        for person in people:
            value = person[question]
            if value is None or value == "":
                continue
            group = group_of(person)
            weight = float(person[WEIGHT])
            totals[group] += weight
            sizes[group] += 1
            counts[(group, str(value).split(".")[0])] += weight
        for (group, value), weight in sorted(counts.items()):
            label = codes.get(question, {}).get(value, value)
            results.append((question, group_name, group, label, round(100 * weight / totals[group], 2), sizes[group]))

    def everyone(person):
        return "전체"

    def by_sex(person):
        key = str(person["SQ1"]).split(".")[0]
        return sex_label.get(key, key)

    def by_age(person):
        return age_band(float(person["SQ2"]))

    def by_sex_age(person):
        return f"{by_sex(person)} {by_age(person)}"

    for question in QUESTIONS:
        tabulate(question, "전체", everyone)
        tabulate(question, "성별", by_sex)
        tabulate(question, "연령대", by_age)
        tabulate(question, "성별x연령대", by_sex_age)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "krei_2025_beverage_distributions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["문항", "문항 설명", "집단 종류", "집단", "보기", "가중 비율(%)", "집단 응답자 수"])
        for question, group_name, group, label, pct, size in results:
            writer.writerow([question, labels.get(question, ""), group_name, group, label, pct, size])
    with open(OUT_DIR / "krei_2025_beverage_codebook.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["문항", "문항 설명", "값", "보기"])
        for question in wanted:
            for value, label in codes.get(question, {}).items():
                writer.writerow([question, labels.get(question, ""), value, label])

    # 화면에 요약
    def show(question: str, group_name: str, top: int = 20) -> None:
        print(f"\n== {question} {labels.get(question)} [{group_name}]")
        table = defaultdict(list)
        for q, g, group, label, pct, size in results:
            if q == question and g == group_name:
                table[group].append((pct, label, size))
        for group, items in table.items():
            items.sort(reverse=True)
            text = ", ".join(f"{label[:14]} {pct:.1f}" for pct, label, _ in items[:top])
            print(f"  {group} (n={items[0][2]}): {text}")

    show("A15_1", "전체")
    show("A15_1", "연령대", top=5)
    show("A16", "전체")
    show("A16_1", "전체")
    show("A16_1", "성별x연령대", top=4)
    show("A19_1", "전체")
    show("A19_1", "연령대")
    show("A19_4", "전체")
    show("A19_4", "연령대")
    show("A19_1_1", "전체")
    show("A19_2_1", "전체")


if __name__ == "__main__":
    main()
