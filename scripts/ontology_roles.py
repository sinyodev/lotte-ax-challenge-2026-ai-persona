"""참가자의 ERD에 있는 개념 4개, 관계 4개, 사건 2개를 개발 자료에 적용한다."""

from contextlib import closing
import sqlite3

import reliability4 as study
import pilot


def evaluate(plan, cases, offers):
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE persona(uuid TEXT PRIMARY KEY, sex TEXT, age_band TEXT, province TEXT, description TEXT);
            CREATE TABLE need(id TEXT PRIMARY KEY, name TEXT, scope TEXT, goal TEXT, visible TEXT, evidence TEXT);
            CREATE TABLE occasion(id TEXT PRIMARY KEY, name TEXT, shelf TEXT, share_pct REAL, observations INTEGER);
            CREATE TABLE product(name TEXT, shelf TEXT, maker TEXT, own INTEGER, kind TEXT, ml INTEGER,
                price INTEGER, promo TEXT, sugar TEXT, caffeine TEXT, carbonation TEXT, PRIMARY KEY(name,shelf));
            CREATE TABLE wants(uuid TEXT REFERENCES persona, need TEXT REFERENCES need, strength INTEGER,
                PRIMARY KEY(uuid,need));
            CREATE TABLE fulfills(product TEXT, shelf TEXT, need TEXT REFERENCES need, degree TEXT, rule TEXT,
                PRIMARY KEY(product,shelf,need), FOREIGN KEY(product,shelf) REFERENCES product(name,shelf));
            CREATE TABLE shifts(occasion TEXT REFERENCES occasion, need TEXT REFERENCES need, delta REAL, evidence TEXT,
                PRIMARY KEY(occasion,need));
            CREATE TABLE faces(sex TEXT, age_band TEXT, occasion TEXT REFERENCES occasion, share_pct REAL,
                PRIMARY KEY(sex,age_band,occasion));
            CREATE TABLE visit(id TEXT PRIMARY KEY, uuid TEXT REFERENCES persona, occasion TEXT REFERENCES occasion, shelf TEXT);
            CREATE TABLE choice(visit TEXT REFERENCES visit, scenario TEXT, reason_index INTEGER, product TEXT,
                shelf TEXT, valid INTEGER, reason_need TEXT REFERENCES need, raw_reason TEXT, reason_sentence TEXT,
                PRIMARY KEY(visit,scenario,reason_index), FOREIGN KEY(product,shelf) REFERENCES product(name,shelf));
        """)
        shelf = study.method.SHELF
        needs = {n["번호"] for n in plan.plain["needs"]}
        db.executemany("INSERT INTO need VALUES(?,?,?,?,?,?)",
                       [(n["번호"], n["욕구"], n["범위"], n["바라는 것(위층)"], n["매대에서 확인되는 것"], n["근거 유형"])
                        for n in plan.plain["needs"]])
        for v in plan.visits:
            p = plan.by_uuid[v["uuid"]]
            db.execute("INSERT INTO persona VALUES(?,?,?,?,?)", (p.uuid, p.sex, p.band, p.text[2], p.text[4]))
            db.executemany("INSERT INTO wants VALUES(?,?,?)",
                           [(p.uuid, n, int(plan.plain["strength"][p.uuid][n])) for n in needs])
        occasions = [o for o in plan.plain["occasions"].values() if o["매대"] == shelf]
        db.executemany("INSERT INTO occasion VALUES(?,?,?,?,?)",
                       [(o["번호"], o["상황"], shelf, o["전체 비중(%)"], o["마신 자리 수"]) for o in occasions])
        db.executemany("INSERT INTO shifts VALUES(?,?,?,?)",
                       [(r["번호"], r["욕구 번호"], r["바뀌는 크기(-2~+2)"], r["근거 종류"])
                        for r in pilot.read("occasion_needs.csv") if r["매대"] == shelf and r["욕구 번호"] in needs])
        db.executemany("INSERT INTO faces VALUES(?,?,?,?)",
                       [(r["성별"], r["연령대"], r["번호"], r["비중(%)"])
                        for r in pilot.read("occasion_weights.csv") if r["매대"] == shelf])
        rules = {(r["상품명"], r["욕구 번호"]): r["적용한 규칙"] for r in pilot.read("fulfills.csv") if r["매대"] == shelf}
        for p in study.catalog.current():
            if p.shelf != shelf:
                continue
            db.execute("INSERT INTO product VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (p.key, shelf, p.row.get("제조사"), p.is_own, p.kind, p.volume, p.price, p.promo,
                        p.row.get("당"), p.row.get("카페인"), p.row.get("탄산")))
            db.executemany("INSERT INTO fulfills VALUES(?,?,?,?,?)",
                           [(p.key, shelf, n, degree, rules.get((p.key, n))) for n, degree in p.fulfills.items() if n in needs])
        # 가격과 행사가 변하는 컨셉은 매대 조건마다 다르다. 원안 제품표에는 변하지 않는 키만 먼저 넣는다.
        db.executemany("INSERT INTO product(name,shelf) VALUES(?,?)",
                       [(k, shelf) for k in sorted({v[0] for v in offers.values() if v[0]})])
        db.executemany("INSERT INTO visit VALUES(?,?,?,?)",
                       [(v["방문"], v["uuid"], v["상황 번호"], shelf) for v in plan.visits])
        for case, rows in cases.items():
            for key, r in rows.items():
                product = r["product"] if r["product"] != study.method.NO_PURCHASE else None
                for i, code in enumerate(r.get("needs") or [None]):
                    db.execute("INSERT INTO choice VALUES(?,?,?,?,?,?,?,?,?)",
                               (key, case, i, product, shelf, r["product"] is not None, code if code in needs else None,
                                code, r.get("sentence")))

        expected = {(case, k): r["product"] for case, rows in cases.items() for k, r in rows.items()}
        actual = {(case, k): ((product or study.method.NO_PURCHASE) if valid else None)
                  for case, k, valid, product in db.execute(
                      "SELECT scenario,visit,valid,product FROM choice WHERE reason_index=0")}
        if actual != expected or db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("원안으로 기록을 읽으면 방문·선택 또는 참조 무결성이 달라집니다.")
        counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in
                  ("persona", "need", "occasion", "product", "wants", "fulfills", "shifts", "faces", "visit", "choice")}
        grounded = db.execute("""
            SELECT count(*),count(c.reason_need),count(w.need),count(f.need),
                   sum(CASE WHEN f.degree IN ('잘 채움','조금 채움') THEN 1 ELSE 0 END), count(s.need)
            FROM choice c JOIN visit v ON v.id=c.visit
            LEFT JOIN wants w ON w.uuid=v.uuid AND w.need=c.reason_need
            LEFT JOIN fulfills f ON f.product=c.product AND f.shelf=c.shelf AND f.need=c.reason_need
            LEFT JOIN shifts s ON s.occasion=v.occasion AND s.need=c.reason_need
            WHERE c.scenario='dev-first' AND c.product IS NOT NULL AND c.raw_reason IS NOT NULL
        """).fetchone()
        covered = db.execute("""SELECT count(*) FROM visit v JOIN persona p ON p.uuid=v.uuid
                              JOIN faces f ON f.sex=p.sex AND f.age_band=p.age_band AND f.occasion=v.occasion""").fetchone()[0]
        reproduced = 0
        for uid, sex, age, expected in db.execute(
                "SELECT p.uuid,p.sex,p.age_band,v.occasion FROM visit v JOIN persona p ON p.uuid=v.uuid"):
            point = pilot.unit(uid, shelf, "shelf-test") * 100
            options = db.execute("SELECT occasion,share_pct FROM faces WHERE sex=? AND age_band=? ORDER BY rowid",
                                 (sex, age)).fetchall()
            cumulative = 0.
            assigned = None
            for assigned, share in options:
                cumulative += share
                if point <= cumulative:
                    break
            reproduced += assigned == expected
        return {"tables": counts, "reproduced_occasions": reproduced, "events": len(actual), "visits_with_faces": covered,
                "reason_mentions_for_purchases": grounded[0], "recognized_need": grounded[1], "with_wants": grounded[2],
                "with_fulfills": grounded[3], "positive_fulfills": grounded[4] or 0, "with_occasion_shift": grounded[5]}
