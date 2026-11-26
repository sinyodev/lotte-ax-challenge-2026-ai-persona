"""NVIDIA Nemotron-Personas-Korea에서 손님 표본을 층화 추출한다.

실행:
    uv run --with duckdb python scripts/sample_personas.py

입력:  data/raw/nvidia-personas-korea/*.parquet  (원시 자료, 고치지 않는다)
출력:  data/clean/personas_8000.parquet          (뽑은 손님. 원본 컬럼 + age_band + pool)
       data/clean/personas_sample_report.md      (표본이 전체와 닮았는지 점검한 표)

방법:
- 연령대 x 성별로 층을 나누고 각 층에서 전체 비율대로 뽑는다(비례 배분).
- 층 안에서의 순서는 md5(uuid + 씨앗)로 정한다. 난수 발생기에 기대지 않으므로
  언제 어디서 돌려도 같은 손님이 뽑힌다.
- 뽑은 손님의 1/3은 개발용(dev), 2/3는 실험용(exp)으로 나눈다.
"""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "nvidia-personas-korea" / "*.parquet"
OUT_DIR = ROOT / "data" / "clean"
SAMPLE_SIZE = 8000
SEED = "lotte-ax-2026-11-16"

AGE_BAND = """
CASE
  WHEN age < 30 THEN '19-29'
  WHEN age < 40 THEN '30-39'
  WHEN age < 50 THEN '40-49'
  WHEN age < 60 THEN '50-59'
  WHEN age < 70 THEN '60-69'
  ELSE '70+'
END
"""

# 표본 점검에 쓰는 컬럼. 층으로 쓰지 않은 컬럼이라 비율이 저절로 맞는지 본다.
CHECK_COLUMNS = ["province", "marital_status", "education_level", "family_type", "housing_type", "occupation"]

# 서술에 음료 이야기가 얼마나 나오는지 세어 보는 낱말.
KEYWORDS = ["음료", "커피", "탄산", "콜라", "사이다", "제로", "주스", "우유", "맥주", "소주", "편의점", "물 한", "차 한"]

TEXT_COLUMNS = [
    "persona", "professional_persona", "sports_persona", "arts_persona", "travel_persona",
    "culinary_persona", "family_persona", "cultural_background", "hobbies_and_interests",
]


def allocate(strata: list[tuple[str, str, int]], total: int) -> dict[tuple[str, str], int]:
    """층별 인원을 비례 배분한다. 반올림 오차는 나머지가 큰 층부터 채운다."""
    population = sum(n for _, _, n in strata)
    exact = {(band, sex): total * n / population for band, sex, n in strata}
    alloc = {key: int(value) for key, value in exact.items()}
    leftover = total - sum(alloc.values())
    for key in sorted(exact, key=lambda k: exact[k] - alloc[k], reverse=True)[:leftover]:
        alloc[key] += 1
    return alloc


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE VIEW raw AS SELECT * FROM read_parquet('{RAW.as_posix()}')")

    population = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    columns = [row[0] for row in con.execute("DESCRIBE raw").fetchall()]

    # 1. 층별 인원
    con.execute(f"CREATE TABLE keys AS SELECT uuid, sex, {AGE_BAND} AS age_band FROM raw")
    strata = con.execute("SELECT age_band, sex, count(*) FROM keys GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
    alloc = allocate(strata, SAMPLE_SIZE)
    con.execute("CREATE TABLE alloc (age_band VARCHAR, sex VARCHAR, k INTEGER)")
    con.executemany("INSERT INTO alloc VALUES (?, ?, ?)", [(b, s, k) for (b, s), k in alloc.items()])

    # 2. 층 안에서 정해진 순서로 뽑기
    con.execute(
        f"""
        CREATE TABLE picked AS
        SELECT uuid, age_band, rn FROM (
          SELECT k.uuid, k.age_band, a.k,
                 row_number() OVER (PARTITION BY k.age_band, k.sex ORDER BY md5(k.uuid || '{SEED}')) AS rn
          FROM keys k JOIN alloc a USING (age_band, sex)
        ) WHERE rn <= k
        """
    )
    con.execute(
        """
        CREATE TABLE sample AS
        SELECT r.*, p.age_band, CASE WHEN p.rn % 3 = 0 THEN 'dev' ELSE 'exp' END AS pool
        FROM raw r JOIN picked p USING (uuid)
        """
    )
    out_path = OUT_DIR / f"personas_{SAMPLE_SIZE}.parquet"
    con.execute(f"COPY sample TO '{out_path.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    sample_size = con.execute("SELECT count(*) FROM sample").fetchone()[0]
    pools = dict(con.execute("SELECT pool, count(*) FROM sample GROUP BY 1").fetchall())

    lines = [
        "# 손님 표본 점검",
        "",
        "`scripts/sample_personas.py`가 만든 파일이다. 손으로 고치지 않는다.",
        "",
        f"- 원시 자료: NVIDIA Nemotron-Personas-Korea, {population:,}건, 컬럼 {len(columns)}개",
        f"- 표본: {sample_size:,}명 (개발용 {pools.get('dev', 0):,}명, 실험용 {pools.get('exp', 0):,}명)",
        f"- 층: 연령대 6개 x 성별 2개, 비례 배분. 씨앗 `{SEED}`",
        "",
        "## 층별 인원 (층으로 쓴 컬럼이라 비율이 맞는 것이 당연하다)",
        "",
        "| 연령대 | 성별 | 전체 | 전체 비율 | 표본 | 표본 비율 |",
        "|---|---|---|---|---|---|",
    ]
    for band, sex, n in strata:
        k = alloc[(band, sex)]
        lines.append(f"| {band} | {sex} | {n:,} | {100 * n / population:.2f}% | {k} | {100 * k / sample_size:.2f}% |")

    # 3. 층으로 쓰지 않은 컬럼에서 표본이 전체와 닮았는지
    lines += ["", "## 층으로 쓰지 않은 컬럼의 비율 비교", ""]
    summary = []
    for column in CHECK_COLUMNS:
        rows = con.execute(
            f"""
            WITH pop AS (SELECT {column} AS v, count(*) * 100.0 / {population} AS pct FROM raw GROUP BY 1),
                 smp AS (SELECT {column} AS v, count(*) * 100.0 / {sample_size} AS pct FROM sample GROUP BY 1)
            SELECT pop.v, pop.pct, coalesce(smp.pct, 0) FROM pop LEFT JOIN smp USING (v) ORDER BY pop.pct DESC
            """
        ).fetchall()
        max_gap = max(abs(p - s) for _, p, s in rows)
        summary.append((column, len(rows), max_gap))
        lines += [f"### {column} (값 {len(rows)}종, 가장 큰 차이 {max_gap:.2f}%p)", "", "| 값 | 전체 | 표본 | 차이 |", "|---|---|---|---|"]
        for value, pop_pct, smp_pct in rows[:8]:
            lines.append(f"| {value} | {pop_pct:.2f}% | {smp_pct:.2f}% | {smp_pct - pop_pct:+.2f}%p |")
        lines.append("")

    # 4. 서술에 음료 이야기가 얼마나 나오는가 (전체 기준)
    any_text = " || ' ' || ".join(f"coalesce({c}, '')" for c in TEXT_COLUMNS if c in columns)
    selects = []
    for i, word in enumerate(KEYWORDS):
        selects.append(f"avg(CASE WHEN culinary_persona LIKE '%{word}%' THEN 100.0 ELSE 0 END) AS c{i}")
        selects.append(f"avg(CASE WHEN ({any_text}) LIKE '%{word}%' THEN 100.0 ELSE 0 END) AS a{i}")
    keyword_row = con.execute(f"SELECT {', '.join(selects)} FROM raw").fetchone()
    lines += [
        "## 서술에 음료 관련 낱말이 나오는 비율 (전체 기준)",
        "",
        "욕구를 뽑을 단서가 서술에 얼마나 있는지 보는 값이다. 낱말이 들어 있다는 것만 센 것이라 뜻까지 본 것은 아니다.",
        "",
        "| 낱말 | 음식 서술(culinary_persona) | 서술 전체 |",
        "|---|---|---|",
    ]
    for i, word in enumerate(KEYWORDS):
        lines.append(f"| {word} | {keyword_row[2 * i]:.1f}% | {keyword_row[2 * i + 1]:.1f}% |")

    lengths = con.execute(
        "SELECT avg(length(culinary_persona)), min(length(culinary_persona)), max(length(culinary_persona)) FROM raw"
    ).fetchone()
    lines += ["", f"음식 서술의 길이: 평균 {lengths[0]:.0f}자, 최소 {lengths[1]}자, 최대 {lengths[2]}자", ""]

    (OUT_DIR / "personas_sample_report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"전체 {population:,}건, 컬럼 {len(columns)}개: {columns}")
    print(f"표본 {sample_size:,}명 -> {out_path.relative_to(ROOT)} ({out_path.stat().st_size / 1e6:.1f}MB), 풀: {pools}")
    for column, kinds, gap in summary:
        print(f"  {column}: 값 {kinds}종, 가장 큰 차이 {gap:.2f}%p")
    for i, word in enumerate(KEYWORDS):
        print(f"  '{word}': 음식 서술 {keyword_row[2 * i]:.1f}%, 서술 전체 {keyword_row[2 * i + 1]:.1f}%")
    print("--- 음식 서술 예시 3건 ---")
    for age, sex, occupation, text in con.execute(
        "SELECT age, sex, occupation, culinary_persona FROM sample ORDER BY md5(uuid) LIMIT 3"
    ).fetchall():
        print(f"[{age}세 {sex} {occupation}] {text}")


if __name__ == "__main__":
    main()
