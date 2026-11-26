import csv

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import onsite
from main import app
from onsite.build import build, publish
from onsite.schema import CSV_COLUMNS, FILENAMES, JSON_NAMES


def sample_tables():
    tables = {name: pd.DataFrame(columns=columns) for name, columns in CSV_COLUMNS.items()}
    tables.update({"concepts": [{"name": "견본 과즙음료"}], "fgi": {},
                   "cleaning_report": [], "survey_summary": {}})
    columns = CSV_COLUMNS["pos_clean"]
    values = ["2024-02", "견본권역", "견본점", "0007", "견본", None, "음료", 2, 1400,
              None, False, True]
    tables["pos_clean"] = pd.DataFrame([values], columns=columns)
    return tables


def test_missing_data(tmp_path, monkeypatch):
    root = tmp_path / "아직 없음"
    monkeypatch.setenv("AX_ONSITE_DIR", str(root))
    assert not onsite.available()
    with pytest.raises(onsite.NoData):
        onsite.load("pos_clean")
    with pytest.raises(KeyError):
        onsite.load("../../또다른폴더")
    with pytest.raises(KeyError):
        onsite.load_json("pos_clean")
    with pytest.raises(ValueError, match="3-0"):
        build(root, root)
    client = TestClient(app)
    assert client.get("/api/onsite/status").json() == {"available": False, "built_at": None, "tables": []}
    assert client.get("/api/onsite/concepts").json() == []
    assert client.get("/api/onsite/cleaning-report").json() == []


def test_publish_reload_and_routes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AX_ONSITE_DIR", "out")
    tables = sample_tables()
    destination = onsite.directory()
    publish(destination, tables)
    row = onsite.load("pos_clean")[0]
    assert (row["sku"], row["units"], row["brand"]) == ("0007", 2, None)
    assert row["after_end"] is True and row["is_own"] is False
    assert list(onsite.frame("temperature").columns) == list(CSV_COLUMNS["temperature"])
    row["units"] = -1
    assert onsite.load("pos_clean")[0]["units"] == 2
    tables["pos_clean"].loc[0, "units"] = 3
    publish(destination, tables)
    assert onsite.load("pos_clean")[0]["units"] == 3
    tables["infra"] = pd.DataFrame()
    with pytest.raises(ValueError, match="infra"):
        publish(destination, tables)
    assert onsite.load("pos_clean")[0]["units"] == 3
    client = TestClient(app)
    status = client.get("/api/onsite/status").json()
    assert status["available"] and status["built_at"] and set(status["tables"]) == set(FILENAMES)
    for route, name in [("cleaning-report", "cleaning_report"), ("concepts", "concepts")]:
        assert client.get(f"/api/onsite/{route}").json() == tables[name]


RAW = onsite.DATA_ROOT / "raw" / "onsite"
SOURCE_PATTERNS = ("3-0_*.docx", "3-1_*.xlsx", "3-2_*.xlsx", "3-3_*.xlsx", "3-4_*.docx")


@pytest.mark.skipif(not all(any(RAW.glob(p)) for p in SOURCE_PATTERNS), reason="대회 원본이 있는 환경에서만 확인")
def test_provided_sources_match_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path))
    build(RAW, tmp_path)
    assert onsite.available()
    for name, columns in CSV_COLUMNS.items():
        with (tmp_path / FILENAMES[name]).open(encoding="utf-8-sig", newline="") as stream:
            assert tuple(next(csv.reader(stream))) == columns
        assert len(onsite.load(name)) > 0
    for name in JSON_NAMES:
        assert onsite.load_json(name)
    summary = onsite.load_json("survey_summary")
    assert summary["n"] == {"raw": 304, "clean": 276}
    for concept, expected in [("밀키스 화채", .55), ("쥬시모먼트", .50), ("레쓰비 프리즈", .43)]:
        assert abs(summary["concepts"][concept]["top2"]["raw"] - expected) <= .0051
        assert len(summary["concepts"][concept]["segments"]) == 8
    rules = {(r["source"], r["rule"]): r for r in onsite.load_json("cleaning_report")}
    assert rules["survey", "duplicate_hash"]["removed"] == 4
    assert rules["survey", "inattentive"]["removed"] == 21
    # 원본 상자 162행 중 앞선 삭제 규칙을 통과한 159행만 실제 환산한다.
    assert rules["pos", "box_24"]["flagged"] == 159
    # 현재 배포 원본에서 판매수량 < 0은 사전 집계(22)와 한 건 차이가 있다.
    assert rules["pos", "negative_units"]["removed"] == 21
    assert rules["pos", "duplicate_key"]["removed"] == 24
    assert rules["pos", "test_product"]["removed"] == 7
    fgi = onsite.load_json("fgi")
    assert any(m["mismatch"] and m["claimed"] == {"n": 12, "of": 15}
               and m["recount"] == {"score_4plus": 6, "of": 15} for m in fgi["moderator"])
    trend = onsite.load("trend")
    assert any(r["search_raw"] < 0 and r["search_index"] == 0 for r in trend)
    assert any(r["sns_raw"] < 0 and r["sns_mentions"] == 0 for r in trend)
    assert len(onsite.load("journeys_offline")) == 15
    assert len(onsite.load("journeys_online")) == 2698
