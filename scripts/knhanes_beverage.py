"""2024 국민건강영양조사 식품섭취조사(24시간 회상)에서 음료·주류를 언제, 어디서, 누구와 마셨는지 집계한다.

실행 (두 단계):
    uv run --with pyreadstat --with pandas --with pyarrow --with "numpy<2" python scripts/knhanes_beverage.py extract
    uv run --with duckdb python scripts/knhanes_beverage.py tabulate
    uv run --with duckdb python scripts/knhanes_beverage.py products    # 제품별 마신 횟수(탄산음료, 맥주, 소주). 검증 자료로 쓴다

입력:  data/raw/knhanes/hn24_24rc/HN24_24RC.sav   (질병관리청에서 받은 원시자료. 54만 건, 6,802명)
중간:  data/raw/knhanes/hn24_24rc_subset.parquet  (필요한 변수만. 개인 단위라 저장소에 올리지 않는다)
출력:  data/clean/knhanes_2024_beverage_occasions.csv  (음료 종류별 가중 비율. 개인 단위 자료는 내보내지 않는다)

세는 단위: 한 사람이 한 번의 식사·간식 자리(끼니 구분 + 시각)에서 한 종류의 음료를 마신 것 1건.
가중치: wt_ntr (영양조사 가중치). 19세 이상만 쓴다.

코드의 뜻 (2026-11-17, 이용지침서를 아직 받지 못해 자료의 내용을 보고 짐작한 것. 지침서로 확인해야 한다):
    N_KINDG1  21 = 음료류, 22 = 주류
    N_MEAL    1 아침, 2 점심, 3 저녁, 4 간식
    N_MEAL_P  1 가정, 2 직장·학교, 5 (미상), 7 음식점, 11 (미상), 98 기타
    N_MTYPE   1 가정식, 5 음식업소 음식, 12 일반식품(조리 없이 먹는 것), 14 단체급식, 21 편의식품
    N_MEAL_W  1 혼자, 2 가족과, 3 가족이 아닌 사람과
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "raw" / "knhanes" / "hn24_24rc" / "HN24_24RC.sav"
SUBSET = ROOT / "data" / "raw" / "knhanes" / "hn24_24rc_subset.parquet"
OUT = ROOT / "data" / "clean" / "knhanes_2024_beverage_occasions.csv"

COLUMNS = [
    "ID", "sex", "age", "occp", "incm", "wt_ntr", "N_DAY", "N_MEAL", "N_MEAL_T", "N_MEAL_P", "N_MTYPE",
    "N_MEAL_W", "N_DNAME", "N_DCODE", "N_FNAME", "N_FNAME3", "N_PRODUCT", "N_CNAME", "N_KINDG1", "NF_INTK",
]

# 3차 식품코드명을 음료 종류로 묶는다. 여기 없는 이름은 "기타 음료" 또는 "기타 주류"가 된다.
DRINK_TYPE = """
CASE
  WHEN N_KINDG1 = '22' AND N_FNAME3 LIKE '소주%' THEN '소주'
  WHEN N_KINDG1 = '22' AND N_FNAME3 LIKE '맥주%' THEN '맥주'
  WHEN N_KINDG1 = '22' AND N_FNAME3 LIKE '막걸리%' THEN '막걸리'
  WHEN N_KINDG1 = '22' THEN '기타 주류'
  WHEN N_FNAME3 LIKE '탄산음료,저칼로리%' THEN '탄산음료(저칼로리)'
  WHEN N_FNAME3 LIKE '탄산음료%' THEN '탄산음료'
  WHEN N_FNAME3 LIKE '커피,커피만%' THEN '커피(커피만)'
  WHEN N_FNAME3 LIKE '커피%' THEN '커피(당·프림 등 첨가)'
  WHEN N_FNAME3 LIKE '과일음료%' OR N_FNAME3 LIKE '채소음료%' THEN '과일·채소음료'
  WHEN N_FNAME3 LIKE '%차%' THEN '차'
  WHEN N_FNAME3 LIKE '%이온%' OR N_FNAME3 LIKE '%스포츠%' THEN '이온·스포츠음료'
  ELSE '기타 음료'
END
"""

TIME_BAND = """
CASE
  WHEN hh BETWEEN 5 AND 8 THEN '1 아침(05~09시)'
  WHEN hh BETWEEN 9 AND 10 THEN '2 오전(09~11시)'
  WHEN hh BETWEEN 11 AND 13 THEN '3 점심(11~14시)'
  WHEN hh BETWEEN 14 AND 16 THEN '4 오후(14~17시)'
  WHEN hh BETWEEN 17 AND 20 THEN '5 저녁(17~21시)'
  ELSE '6 밤(21~05시)'
END
"""

AGE_BAND = """
CASE WHEN age < 30 THEN '19-29' WHEN age < 40 THEN '30-39' WHEN age < 50 THEN '40-49'
     WHEN age < 60 THEN '50-59' WHEN age < 70 THEN '60-69' ELSE '70+' END
"""

LABELS = {
    "끼니": {"1": "아침", "2": "점심", "3": "저녁", "4": "간식"},
    "장소": {"1": "가정", "2": "직장·학교", "5": "미상(5)", "7": "음식점", "11": "미상(11)", "98": "기타"},
    "동반": {"1": "혼자", "2": "가족과", "3": "가족이 아닌 사람과"},
    "먹은 형태": {"1": "가정식", "5": "음식업소 음식", "12": "일반식품", "14": "단체급식", "21": "편의식품"},
}


def extract() -> None:
    import pyreadstat

    df, _ = pyreadstat.read_sav(str(SOURCE), usecols=COLUMNS)
    df.to_parquet(SUBSET)
    print(f"{len(df):,}건, {df.ID.nunique():,}명 -> {SUBSET.relative_to(ROOT)}")


def tabulate() -> None:
    import duckdb

    con = duckdb.connect()
    con.execute(f"CREATE VIEW raw AS SELECT * FROM read_parquet('{SUBSET.as_posix()}') WHERE age >= 19")
    # 자리: 한 사람의 한 번의 식사·간식 (끼니 구분 + 시각)
    con.execute(
        f"""
        CREATE TABLE sitting AS
        SELECT ID, N_MEAL, N_MEAL_T,
               bool_or(N_KINDG1 NOT IN ('21', '22')) AS with_food
        FROM raw GROUP BY 1, 2, 3
        """
    )
    con.execute(
        f"""
        CREATE TABLE drink AS
        SELECT DISTINCT r.ID, r.sex, {AGE_BAND} AS age_band, r.wt_ntr AS w,
               {DRINK_TYPE} AS drink,
               cast(r.N_MEAL AS INTEGER)::VARCHAR AS meal,
               cast(r.N_MEAL_P AS INTEGER)::VARCHAR AS place,
               cast(r.N_MEAL_W AS INTEGER)::VARCHAR AS companion,
               cast(r.N_MTYPE AS INTEGER)::VARCHAR AS mtype,
               CASE WHEN r.N_DAY IN ('토요일', '일요일') THEN '주말' ELSE '평일' END AS day_kind,
               (SELECT {TIME_BAND} FROM (SELECT try_cast(substr(r.N_MEAL_T, 1, 2) AS INTEGER) AS hh)) AS time_band,
               CASE WHEN s.with_food THEN '음식과 함께' ELSE '음료만' END AS with_food
        FROM raw r JOIN sitting s USING (ID, N_MEAL, N_MEAL_T)
        WHERE r.N_KINDG1 IN ('21', '22')
        """
    )
    people = con.execute("SELECT count(DISTINCT ID) FROM raw").fetchone()[0]
    drinkers = con.execute("SELECT count(DISTINCT ID) FROM drink").fetchone()[0]
    print(f"19세 이상 {people:,}명 중 음료·주류를 마신 사람 {drinkers:,}명, 마신 자리 {con.execute('SELECT count(*) FROM drink').fetchone()[0]:,}건")
    print("3차 식품코드명:", con.execute(
        "SELECT string_agg(f || '(' || c || ')', ', ' ORDER BY c DESC) FROM (SELECT N_FNAME3 f, count(*) c FROM raw WHERE N_KINDG1 IN ('21','22') GROUP BY 1)"
    ).fetchone()[0])

    axes = [("시간대", "time_band"), ("끼니", "meal"), ("장소", "place"), ("동반", "companion"),
            ("먹은 형태", "mtype"), ("요일", "day_kind"), ("음식 동반", "with_food")]
    rows = []
    for axis, column in axes:
        for group_kind, group_sql in [("전체", "'전체'"), ("연령대", "age_band"), ("성별", "sex::VARCHAR")]:
            for drink, group, value, pct, n in con.execute(
                f"""
                SELECT drink, {group_sql} AS g, {column} AS v,
                       round(100 * sum(w) / sum(sum(w)) OVER (PARTITION BY drink, {group_sql}), 1),
                       sum(count(*)) OVER (PARTITION BY drink, {group_sql})
                FROM drink GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
                """
            ).fetchall():
                rows.append((drink, group_kind, group, axis, LABELS.get(axis, {}).get(value, value), pct, int(n)))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["음료 종류", "집단 종류", "집단", "축", "값", "가중 비율(%)", "집단의 마신 자리 수"])
        writer.writerows(rows)
    print(f"-> {OUT.relative_to(ROOT)} ({len(rows):,}줄)")

    for axis, _ in axes:
        print(f"\n== {axis} (전체, 가중 %)")
        table = {}
        for drink, kind, group, a, value, pct, n in rows:
            if kind == "전체" and a == axis:
                table.setdefault((drink, n), []).append(f"{value} {pct}")
        for (drink, n), items in sorted(table.items(), key=lambda x: -x[0][1]):
            print(f"  {drink} (n={n}): " + ", ".join(items))

    print("\n== 제조회사가 적힌 음료·주류 (상위 15)")
    for name, n in con.execute(
        "SELECT trim(N_CNAME), count(*) FROM raw WHERE N_KINDG1 IN ('21','22') AND trim(N_CNAME) NOT IN ('', '888') GROUP BY 1 ORDER BY 2 DESC LIMIT 15"
    ).fetchall():
        print(f"  {name}: {n}")
    print("\n== 롯데칠성음료 제품 (상위 25)")
    for name, n in con.execute(
        "SELECT trim(N_PRODUCT), count(*) FROM raw WHERE N_CNAME LIKE '%롯데칠성%' GROUP BY 1 ORDER BY 2 DESC LIMIT 25"
    ).fetchall():
        print(f"  {name}: {n}")


# 제품명을 표준 이름으로 묶는 규칙. 위에서부터 처음 맞는 것을 쓴다. (종류, 표준 제품, 3차 식품코드명의 앞머리, 제품명 정규식)
PRODUCT_RULES = [
    ("탄산", "코카콜라 제로", "탄산음료", r"코카콜라.*(제로|라이트)|제로코카콜라"),
    ("탄산", "코카콜라", "탄산음료", r"^코카콜라$"),
    ("탄산", "펩시 제로", "탄산음료", r"펩시.*제로"),
    ("탄산", "펩시콜라", "탄산음료", r"^펩시콜라$"),
    ("탄산", "칠성사이다 제로", "탄산음료", r"칠성.*제로|제로칠성"),
    ("탄산", "칠성사이다", "탄산음료", r"^칠성사이다$"),
    ("탄산", "스프라이트 제로", "탄산음료", r"스프라이트제로|제로스프"),
    ("탄산", "스프라이트", "탄산음료", r"^스프라이트$"),
    ("탄산", "환타", "탄산음료", r"^환타"),
    ("탄산", "밀키스 제로", "탄산음료", r"밀키스제로"),
    ("탄산", "밀키스", "탄산음료", r"^밀키스$"),
    ("탄산", "나랑드사이다", "탄산음료", r"나랑드"),
    ("탄산", "웰치스 제로", "탄산음료", r"웰치.*제로"),
    ("탄산", "맥콜", "탄산음료", r"^맥콜$"),
    ("맥주", "카스 라이트", "맥주", r"카스라이트"),
    ("맥주", "카스 0.0", "맥주", r"카스0"),
    ("맥주", "카스", "맥주", r"^카스"),
    ("맥주", "테라", "맥주", r"^(테라|TERRA)(맥주|생맥주)?$"),
    ("맥주", "켈리", "맥주", r"(?i)켈리|캘리|kelly"),
    ("맥주", "아사히", "맥주", r"(?i)아사히|asahi"),
    ("맥주", "하이네켄", "맥주", r"하이네켄"),
    ("맥주", "하이트제로", "맥주", r"하이트제로"),
    ("맥주", "하이트", "맥주", r"^하이트맥주$"),
    ("맥주", "클라우드", "맥주", r"^클라우드맥주$"),
    ("맥주", "크러시", "맥주", r"크러시|크러쉬"),
    ("맥주", "칭따오", "맥주", r"^칭따오(맥주)?$"),
    ("맥주", "호가든", "맥주", r"^호가든$"),
    ("맥주", "버드와이저", "맥주", r"버드와이저"),
    ("맥주", "필라이트", "맥주", r"필라이트"),
    ("맥주", "곰표 밀맥주", "맥주", r"곰표"),
    ("소주", "새로", "소주", r"새로"),
    ("소주", "진로 제로슈거", "소주", r"진로.*제로"),
    ("소주", "참이슬", "소주", r"^참이슬"),
    ("소주", "처음처럼", "소주", r"^처음처럼$"),
    ("소주", "진로", "소주", r"^진로(소주|이즈백)$"),
    ("소주", "좋은데이", "소주", r"좋은데이"),
    ("소주", "대선", "소주", r"^대선"),
]
PRODUCT_OUT = ROOT / "data" / "clean" / "knhanes_2024_product_counts.csv"
MIN_COUNT = 5  # 이보다 적은 제품은 내보내지 않는다(표본이 작아 뜻이 없고, 개인 단위에 가까워진다)


def products() -> None:
    """제품명이 적힌 기록을 표준 제품으로 묶어 마신 횟수를 센다. 탄산음료, 맥주, 소주만 한다.

    커피는 타 마시는 믹스커피가 대부분이고 차·주스는 건수가 적어 쓰지 않는다. 편의점만이 아니라 모든 곳에서 마신 것이다.
    세는 단위: 한 사람이 한 번의 자리(끼니 구분 + 시각)에서 그 제품을 마신 것 1건.
    """
    import re
    from collections import defaultdict

    import duckdb

    rows = duckdb.sql(
        f"""SELECT DISTINCT ID, N_MEAL, N_MEAL_T, N_FNAME3, trim(N_PRODUCT), wt_ntr FROM read_parquet('{SUBSET.as_posix()}')
            WHERE age >= 19 AND trim(coalesce(N_PRODUCT, '')) <> ''
              AND (N_FNAME3 LIKE '탄산음료%' OR N_FNAME3 LIKE '맥주%' OR N_FNAME3 LIKE '소주%')"""
    ).fetchall()
    count, people, weight, total, unmatched = defaultdict(int), defaultdict(set), defaultdict(float), defaultdict(int), defaultdict(int)
    for person, _, _, food, name, w in rows:
        kind = "탄산" if food.startswith("탄산음료") else food[:2]
        total[kind] += 1
        for k, standard, head, pattern in PRODUCT_RULES:
            if food.startswith(head) and re.search(pattern, name):
                count[(k, standard)] += 1
                people[(k, standard)].add(person)
                weight[(k, standard)] += w
                break
        else:
            unmatched[kind] += 1
    kept = sorted(((k, c) for k, c in count.items() if c >= MIN_COUNT), key=lambda x: (x[0][0], -x[1]))
    with open(PRODUCT_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["종류", "표준 제품", "마신 횟수", "마신 사람 수", "가중 비율(%, 종류 안에서 내보낸 제품끼리)", "출처"])
        for (kind, standard), c in kept:
            share = 100 * weight[(kind, standard)] / sum(weight[k] for k, _ in kept if k[0] == kind)
            writer.writerow([kind, standard, c, len(people[(kind, standard)]), round(share, 1), "2024 국민건강영양조사 식품섭취조사(제품명이 적힌 기록)"])
    for kind in total:
        print(f"{kind}: 제품명이 적힌 기록 {total[kind]}건, 표준 제품으로 묶지 못한 것 {unmatched[kind]}건")
    print(f"{MIN_COUNT}건 이상인 제품 {len(kept)}개 -> {PRODUCT_OUT.relative_to(ROOT)}")
    for (kind, standard), c in kept:
        print(f"  {kind} {standard}: {c}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "tabulate"
    {"extract": extract, "tabulate": tabulate, "products": products}[step]()
