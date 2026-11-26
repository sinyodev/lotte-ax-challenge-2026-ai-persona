"""저장한 개발 응답을 네 표로 읽어서 선택·재검사·판매·발견 집계가 보존되는지 확인한다."""

import argparse
from contextlib import closing
import json
import os
import sqlite3

import reliability4 as study


def compact_report(name):
    path = study.OUT / ".dev" / name / "responses.sqlite"
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        config = json.loads(source.execute("SELECT settings FROM manifest").fetchone()[0])
        source.execute("BEGIN")
        names = ["dev-first", "dev-repeat", *["dev-" + c for c in (*study.NEUTRAL_CASES, "brand")]]
        cases = {case: study.responses(source, case) for case in names}
    os.environ.update(AX_LLM=config["backend"], AX_SHOPPER_ROUND=str(config["round"]),
                      AX_MODEL_SHOPPER=config["model"], AX_EFFORT_SHOPPER=config["effort"])
    if study.method.shelf_v() != config["shelf"]:
        raise ValueError("수집 당시 매대와 달라서 조인을 재현할 수 없습니다.")
    plan, _ = study.make_plan("dev-first", config["people"], config["per_cell"])
    offers = {}
    for case in names:
        if case in ("dev-first", "dev-repeat"):
            offers[case] = (None, None, None)
        else:
            variant, _ = study.make_plan(case, config["people"], config["per_cell"])
            row = next(p for p in variant.with_concept["products"] if p["상품명"] == variant.line)
            offers[case] = (variant.line, int(row["가격(원)"]), row["행사"])
    from ontology_roles import evaluate

    original_roles = evaluate(plan, cases, offers)
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE person(id TEXT PRIMARY KEY, age TEXT NOT NULL, sex TEXT NOT NULL);
            CREATE TABLE visit(id TEXT PRIMARY KEY, person TEXT NOT NULL REFERENCES person(id), occasion TEXT, month INTEGER);
            CREATE TABLE product(id TEXT PRIMARY KEY, sku TEXT);
            CREATE TABLE choice(
                visit TEXT NOT NULL REFERENCES visit(id), scenario TEXT NOT NULL, valid INTEGER NOT NULL,
                product TEXT REFERENCES product(id), noticed TEXT, considered TEXT, concept TEXT REFERENCES product(id),
                price INTEGER, promo TEXT, reason_needs TEXT, PRIMARY KEY(visit,scenario));
        """)
        db.executemany("INSERT INTO product VALUES(?,?)",
                       [(p.key, p.sku) for p in study.catalog.current() if p.shelf == study.method.SHELF]
                       + [(k, None) for k in sorted({k for k, _, _ in offers.values() if k})])
        for v in plan.visits:
            db.execute("INSERT INTO person VALUES(?,?,?)", (v["uuid"], v["연령대"], v["성별"]))
            db.execute("INSERT INTO visit VALUES(?,?,?,?)", (v["방문"], v["uuid"], v["상황 번호"], v.get("visit_month")))
        for case, records in cases.items():
            for visit, row in records.items():
                item, trace = row["product"], row.get("journey")
                db.execute("INSERT INTO choice VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (visit, case, item is not None, None if item == study.method.NO_PURCHASE else item,
                            json.dumps(trace["noticed"]) if trace else None, json.dumps(trace["considered"]) if trace else None,
                            *offers[case], json.dumps(row["needs"]) if "needs" in row else None))
        report = {"study": name, "visits": len(plan.visits), "answers": sum(map(len, cases.values())), "arms": {}, "original_roles": original_roles}
        original, compact = {}, {}
        for case, records in cases.items():
            projected = {}
            sql = """SELECT v.id,p.age,p.sex,v.month,c.valid,k.id,c.noticed,c.considered,c.concept,c.price,c.promo,c.reason_needs
                     FROM choice c JOIN visit v ON c.visit=v.id JOIN person p ON v.person=p.id
                     LEFT JOIN product k ON c.product=k.id WHERE c.scenario=? ORDER BY v.id"""
            for key, age, sex, month, valid, item, noticed, considered, concept, price, promo, reasons in db.execute(sql, (case,)):
                if (json.loads(reasons) if reasons is not None else None) != records[key].get("needs"):
                    raise ValueError("선택의 이유 코드가 달라졌습니다.")
                if (concept, price, promo) != offers[case]:
                    raise ValueError("실험의 상품·가격·행사 조건이 달라졌습니다.")
                if concept and valid and records[key]["selected"] != (item == concept):
                    raise ValueError("신제품 선택 여부가 달라졌습니다.")
                row = {"age": age, "sex": sex, "visit_month": month,
                       "product": (item or study.method.NO_PURCHASE) if valid else None}
                if noticed is not None:
                    row["journey"] = {"noticed": json.loads(noticed), "considered": json.loads(considered)}
                projected[key] = row
            if projected.keys() != records.keys():
                raise ValueError("방문 조인 중 응답이 누락됐습니다.")
            for key, row in projected.items():
                raw = records[key]
                if any(row[k] != raw.get(k) for k in ("age", "sex", "visit_month", "product")):
                    raise ValueError("방문 속성 또는 구매 결과가 달라졌습니다.")
                for stage in ("noticed", "considered"):
                    if row.get("journey", {}).get(stage) != raw.get("journey", {}).get(stage):
                        raise ValueError("발견·비교 기록이 달라졌습니다.")
            original[case] = {k: r["product"] for k, r in records.items()}
            compact[case] = {k: r["product"] for k, r in projected.items()}
            report["arms"][case] = {"n": len(records), "verified": len(projected),
                                     "journey_measured": sum("journey" in r for r in projected.values())}
            if case == "dev-first" and len(records) == len(plan.visits):
                direct = study.period_fit(records.values(), training=True)
                normalized = study.period_fit(projected.values(), training=True)
                if any(direct[k] != normalized[k] for k in ("n", "matched_picks", "rho", "gap")):
                    raise ValueError("판매 비교 값이 달라졌습니다.")
                report["sales"] = {k: normalized[k] for k in ("matched_picks", "rho", "gap")}
            if offers[case][0] and any("journey" in r for r in projected.values()):
                from shelftest import journey

                direct, normalized = (journey.funnel(rows.values(), offers[case][0]) for rows in (records, projected))
                for k in ("visits", "noticed", "considered", "purchased"):
                    if direct[k] != normalized[k]:
                        raise ValueError("구매 여정의 단계별 인원수가 달라졌습니다.")
                report["arms"][case]["funnel"] = {k: normalized[k] for k in ("visits", "noticed", "considered", "purchased")}
        if len(cases["dev-repeat"]) == len(cases["dev-first"]) == len(plan.visits):
            retests = [study.reliability.retest(rows["dev-first"], rows["dev-repeat"]) for rows in (original, compact)]
            if retests[0] != retests[1]:
                raise ValueError("재검사 결과가 달라졌습니다.")
            report["retest"] = retests[0]["value"]
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("studies", nargs="+", choices=("luna-low-r9", "luna-low-r10"))
    for trial in parser.parse_args().studies:
        print(json.dumps(compact_report(trial), ensure_ascii=False, allow_nan=False, indent=2))
