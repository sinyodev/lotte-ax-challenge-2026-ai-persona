import csv
import json

from fastapi.testclient import TestClient
import pytest

import main
import onsite
from agent import find, proposal_purchase, steps
from agent.note import Note
from onsite.schema import CSV_COLUMNS


def test_observed_purchase_and_survey_intent_have_separate_sources():
    root = onsite.directory()
    root.mkdir()
    (root / "survey_summary.json").write_text(json.dumps({"concepts": {
        "밀키스 화채": {"top2": {"order_adjusted": .48, "weighted": .41}, "leading": False},
        "자료 없음": {"top2": {"order_adjusted": None, "weighted": None}, "leading": False},
    }}))
    with (root / "past_tests.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, CSV_COLUMNS["past_tests"])
        writer.writeheader()
        writer.writerows([
            {"product": "견본 탄산", "year": 2025, "category": "탄산", "intent_top2": .61, "trial_12m": .14},
            {"product": "구매 0건", "year": 2024, "category": "커피", "intent_top2": .45, "trial_12m": 0},
        ])
    with TestClient(main.app) as client:
        r = client.get("/api/onsite/purchase-outcomes")
        assert r.status_code == 200
        data = r.json()
    assert data["concepts"][0]["intent_top2"] == .48
    assert data["concepts"][0]["trial_12m"] is None and data["concepts"][1]["intent_top2"] is None
    assert data["history"][0]["actual_to_intent"] == pytest.approx(.14 / .61)
    assert data["history"][1]["trial_12m"] == data["history"][1]["actual_to_intent"] == 0
    lookup = steps.Lookup(tool="purchase_outcomes", arg="견본탄산")
    fact, = find.run(lookup.tool, lookup.arg, Note())
    assert "61.0%" in fact.text and "14.0%" in fact.text and "2025" in fact.source
    report = {"head": {"product": "밀키스 화채"}, "evidence": {"compare": []}}
    proposal_purchase.add({}, {"n": 10, "picked": 0}, report)
    current, history = report["evidence"]["compare"]
    assert "48.0%" in current["lines"][0] and "미측정" in current["lines"][1]
    assert "가상 매대" in current["lines"][2] and "0.0%" in current["lines"][2]
    assert "14.0%" in history["lines"][0] and len(history["lines"]) == 1
