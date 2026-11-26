"""2024 국민건강영양조사 식품섭취조사에서 칠성이가 찾아볼 집계 둘을 더 만든다 (지시서 09의 3절).

실행 (저장소 맨 위에서):
    uv run --project app/server python scripts/knhanes_extra.py

입력:  data/raw/knhanes/hn24_24rc_subset.parquet  (knhanes_beverage.py extract가 만든 것. 개인 단위라 저장소에 올리지 않는다. 읽기만 한다)
출력:  집계만 저장한다. 응답자 한 명 한 명의 값은 내보내지 않는다.
    data/clean/knhanes_2024_cofoods.csv         음료 종류마다(전체, 연령대별) 같은 끼니에 함께 먹은 음식의 순서
    data/clean/knhanes_2024_beverage_by_job.csv 음료 종류마다 직업 구분별로 다른 음료보다 몇 배 자주 마시는지

음료 종류의 구분(DRINK_TYPE), 연령대(AGE_BAND), 가중치(wt_ntr), 19세 이상만 쓰는 것은 knhanes_beverage.py를 그대로 쓴다.

끼니: 한 사람의 한 번의 식사·간식 자리(끼니 구분 N_MEAL + 시각 N_MEAL_T). knhanes_beverage.py의 "자리"와 같다.

함께 먹은 음식
- 그 음료를 마신 끼니에서, 음료·주류 식품(N_KINDG1 21, 22)이 하나라도 든 음식은 빼고 나머지 음식 이름(N_DNAME)을 센다.
- 음식 이름은 비슷한 것끼리 묶는다(NAME_RULES. 감자튀김과 후렌치후라이, 케첩과 케찹, 후라이드치킨과 양념치킨은 치킨).
- 양념, 김치, 장아찌·절임, 생채소처럼 곁들이는 것은 "곁들임"으로 표시한다(SIDE_*). 말에는 주된 음식을 쓰게 한다.
  곁들임을 가리는 음식 코드(N_DCODE의 둘째·셋째 자리 15 김치, 16 젓갈, 17 장아찌·절임, 18 양념, 26 생채소)는
  코드에 든 음식 이름을 보고 짐작한 것이다. 이용지침서로 확인해야 한다.
- 비율은 가중(wt_ntr) 비율이다: (그 음식을 함께 먹은 끼니의 가중치 합) ÷ (그 음료를 마신 끼니의 가중치 합).
- 함께 먹은 끼니 수가 5 미만인 줄은 내보내지 않는다. 집단마다 위에서 20개까지만 내보낸다.

직업 구분(occp)
- 국민건강영양조사의 직업 재분류 코드 1~7을 쓴다(OCCP). 코드의 뜻은 조사의 직업 재분류를 따라 적었고 이용지침서로 확인해야 한다.
- 몇 배 = (그 음료를 마신 끼니 가운데 그 직업의 가중 몫) ÷ (모든 음료를 마신 끼니 가운데 그 직업의 가중 몫).
  음료와 주류는 따로 나눈다(음료는 음료끼리, 주류는 주류끼리). 직업을 모르는 사람(빈 값)은 뺀다.
- 그 직업이 그 음료를 마신 끼니가 30건 미만인 줄은 내보내지 않는다.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import duckdb

from knhanes_beverage import AGE_BAND, DRINK_TYPE, ROOT, SUBSET

COFOODS_OUT = ROOT / "data" / "clean" / "knhanes_2024_cofoods.csv"
BY_JOB_OUT = ROOT / "data" / "clean" / "knhanes_2024_beverage_by_job.csv"
SOURCE = "2024 국민건강영양조사 식품섭취조사"
MIN_COFOOD = 5
TOP_COFOOD = 20
MIN_JOB = 30

OCCP = {
    "1": "관리자·전문가",
    "2": "사무 종사자",
    "3": "서비스·판매 종사자",
    "4": "농림어업 종사자",
    "5": "기능원·기계조작 종사자",
    "6": "단순노무 종사자",
    "7": "일하지 않는 사람(주부, 학생 등)",
}

# 음식 이름 묶기: (묶은 이름, 정규식). 위에서부터 처음 맞는 것을 쓴다. 맞는 것이 없으면 쉼표·괄호 앞의 이름을 그대로 쓴다.
NAME_RULES = [
    ("감자튀김", r"후렌치\s*후라이|프렌치\s*프라이|감자튀김|웨지감자"),
    ("케첩", r"케찹|케첩"),
    ("치킨무", r"치킨무"),
    ("햄버거", r"버거"),
    ("치킨", r"치킨|닭강정"),
    ("피자", r"피자"),
    ("피클", r"피클"),
    ("밥", r"^(쌀밥|흰쌀밥|백미밥|햇반|햇반쌀밥|즉석밥|공기밥|흰밥|잡곡밥|현미밥|보리밥|흑미밥|현미잡곡밥)$"),
    ("라면", r"라면$|^컵라면"),
    ("김밥", r"김밥$"),
    ("샌드위치", r"샌드위치"),
    ("떡볶이", r"떡볶이"),
    ("돈까스", r"^(치즈)?돈[까가]스$"),
    ("김치", r"김치$|^깍두기$"),
    ("족발", r"족발"),
    ("삼겹살구이", r"삼겹살"),
]
# 곁들임: 음식 코드의 둘째·셋째 자리(짐작) 또는 이름
SIDE_CODES = {"15", "16", "17", "26"}
SIDE_CODE_SAUCE = "18"  # 양념. 다만 카레·짜장은 주된 음식이다
MAIN_IN_SAUCE = re.compile(r"카레|짜장")
SIDE_NAMES = re.compile(
    r"케첩|케찹|간장|와사비|고추냉이|쌈장|소금|마요네즈|고추장|초장|소스|머스타드|머스터드|드레싱|양념장|"
    r"단무지|치킨무|피클|장아찌|김치|깍두기|편마늘|마늘|양파|고추|후추|설탕|식초|참기름|들기름|쌈무|무절임|물$"
)


def group_name(dish: str) -> str:
    dish = dish.strip()
    for name, pattern in NAME_RULES:
        if re.search(pattern, dish):
            return name
    return re.split(r"[,(]", dish)[0].strip() or dish


MAIN_GROUPS = {"감자튀김", "햄버거", "치킨", "피자", "밥", "라면", "김밥", "샌드위치", "떡볶이", "돈까스", "족발", "삼겹살구이"}


def is_side(dish: str, code: str) -> bool:
    if group_name(dish) in MAIN_GROUPS:
        return False
    part = (code or "")[1:3]
    if part in SIDE_CODES:
        return True
    if part == SIDE_CODE_SAUCE and not MAIN_IN_SAUCE.search(dish):
        return True
    return bool(SIDE_NAMES.search(dish))


def load(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"CREATE VIEW raw AS SELECT * FROM read_parquet('{SUBSET.as_posix()}') WHERE age >= 19")
    # 음료를 마신 끼니: (사람, 끼니, 시각, 음료 종류)마다 하나. 가중치는 사람의 가중치
    con.execute(
        f"""
        CREATE TABLE drink AS
        SELECT DISTINCT r.ID, r.N_MEAL, r.N_MEAL_T, r.wt_ntr AS w, {AGE_BAND} AS age_band,
               cast(r.occp AS INTEGER)::VARCHAR AS job, r.N_KINDG1 AS shelf, {DRINK_TYPE} AS drink
        FROM raw r WHERE r.N_KINDG1 IN ('21', '22')
        """
    )


def cofoods(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    # 그 끼니에 먹은 음식(음료·주류 식품이 하나라도 든 음식은 뺀다)
    con.execute(
        """
        CREATE TABLE dish AS
        SELECT ID, N_MEAL, N_MEAL_T, trim(N_DNAME) AS dish, any_value(N_DCODE) AS code
        FROM raw GROUP BY 1, 2, 3, 4
        HAVING NOT bool_or(N_KINDG1 IN ('21', '22')) AND trim(N_DNAME) <> ''
        """
    )
    names = {d: (group_name(d), is_side(d, c)) for d, c in con.execute("SELECT DISTINCT dish, code FROM dish").fetchall()}
    con.execute("CREATE TABLE dish_name (dish VARCHAR, food VARCHAR, side BOOLEAN)")
    con.executemany("INSERT INTO dish_name VALUES (?, ?, ?)", [(d, f, s) for d, (f, s) in names.items()])
    # 묶은 이름 하나가 곁들임과 주된 음식에 걸치면 끼니 수가 많은 쪽을 따른다
    con.execute(
        """
        CREATE TABLE food AS
        SELECT DISTINCT d.ID, d.N_MEAL, d.N_MEAL_T, n.food FROM dish d JOIN dish_name n USING (dish)
        """
    )
    side_of = dict(con.execute(
        """
        SELECT food, sum(CASE WHEN side THEN c ELSE 0 END) * 2 > sum(c)
        FROM (SELECT n.food, n.side, count(*) c FROM dish d JOIN dish_name n USING (dish) GROUP BY 1, 2) GROUP BY 1
        """
    ).fetchall())
    rows: list[tuple] = []
    for group_kind, group_sql in [("전체", "'전체'"), ("연령대", "k.age_band")]:
        result = con.execute(
            f"""
            WITH k AS (SELECT DISTINCT ID, N_MEAL, N_MEAL_T, w, age_band, drink FROM drink),
            base AS (SELECT drink, {group_sql} AS g, count(*) AS n, sum(w) AS sw FROM k GROUP BY 1, 2),
            hit AS (
                SELECT k.drink, {group_sql} AS g, f.food, count(*) AS n, sum(k.w) AS sw
                FROM k JOIN food f USING (ID, N_MEAL, N_MEAL_T) GROUP BY 1, 2, 3
            )
            SELECT hit.drink, hit.g, hit.food, hit.n, round(100 * hit.sw / base.sw, 1), base.n
            FROM hit JOIN base USING (drink, g)
            WHERE hit.n >= {MIN_COFOOD}
            ORDER BY 1, 2, 4 DESC, 5 DESC, 3
            """
        ).fetchall()
        rank: dict[tuple[str, str], int] = {}
        for drink, g, food, n, pct, base_n in result:
            key = (drink, g)
            rank[key] = rank.get(key, 0) + 1
            if rank[key] > TOP_COFOOD:
                continue
            rows.append((drink, group_kind, g, rank[key], food, "곁들임" if side_of.get(food) else "주된 음식",
                         int(n), pct, int(base_n), SOURCE))
    with open(COFOODS_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["음료 종류", "집단 종류", "집단", "순위", "음식", "구분", "함께 먹은 끼니 수",
                         "가중 비율(%)", "그 음료를 마신 끼니 수", "출처"])
        writer.writerows(rows)
    return rows


def by_job(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    result = con.execute(
        """
        WITH k AS (SELECT * FROM drink WHERE job IS NOT NULL),
        kind AS (SELECT shelf, drink, job, count(*) n, sum(w) sw FROM k GROUP BY 1, 2, 3),
        kind_all AS (SELECT shelf, drink, sum(sw) sw FROM kind GROUP BY 1, 2),
        shelf_job AS (SELECT shelf, job, sum(w) sw FROM k GROUP BY 1, 2),
        shelf_all AS (SELECT shelf, sum(w) sw FROM k GROUP BY 1)
        SELECT kind.drink, kind.job, kind.n,
               100 * kind.sw / kind_all.sw AS share, 100 * shelf_job.sw / shelf_all.sw AS base
        FROM kind JOIN kind_all USING (shelf, drink) JOIN shelf_job USING (shelf, job) JOIN shelf_all USING (shelf)
        WHERE kind.n >= ?
        ORDER BY 1, share / base DESC
        """,
        [MIN_JOB],
    ).fetchall()
    rows = [(drink, job, OCCP.get(job, job), int(n), round(share, 1), round(base, 1), round(share / base, 2), SOURCE)
            for drink, job, n, share, base in result]
    with open(BY_JOB_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["음료 종류", "직업 구분 코드", "직업 구분", "마신 끼니 수", "가중 비율(%)",
                         "모든 음료에서의 가중 비율(%)", "몇 배", "출처"])
        writer.writerows(rows)
    return rows


def main() -> None:
    con = duckdb.connect()
    load(con)
    co = cofoods(con)
    print(f"-> {COFOODS_OUT.relative_to(ROOT)} ({len(co):,}줄)")
    for drink, kind, g, rank, food, side, n, pct, base_n, _ in co:
        if kind == "전체" and rank <= 8 and drink in ("탄산음료(저칼로리)", "탄산음료", "맥주"):
            print(f"  {drink} (끼니 {base_n}): {rank}. {food} [{side}] {n}끼니 {pct}%")
    jobs = by_job(con)
    print(f"-> {BY_JOB_OUT.relative_to(ROOT)} ({len(jobs):,}줄)")
    for drink, _, name, n, share, base, ratio, _ in jobs:
        if drink in ("탄산음료(저칼로리)", "탄산음료", "커피(커피만)"):
            print(f"  {drink} {name}: {n}끼니 {share}% / {base}% = {ratio}배")


if __name__ == "__main__":
    main()
