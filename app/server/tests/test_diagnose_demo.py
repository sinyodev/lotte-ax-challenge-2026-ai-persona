import asyncio
import csv
import json

import pytest

import onsite
from agent import diagnose, machine
from onsite.schema import CSV_COLUMNS, FILENAMES
from shelftest import catalog


def _write(table, rows):
    with (onsite.directory() / FILENAMES[table]).open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS[table])
        writer.writeheader()
        writer.writerows(rows)


def _product(price, *, kind="탄산", pack=1, ours=False, volume=500, sku=None):
    return catalog.Product("비교용 견본", {"매대": "음료", "종류": kind, "묶음 수량": str(pack),
                                             "우리 제품": "예" if ours else "아니오", "가격(원)": str(price),
                                             "용량(ml)": str(volume), "모양": "페트"}, {}, sku)


def test_diagnosis_aggregates_summer_wtp_and_only_single_rival_sodas(monkeypatch):
    root = onsite.directory()
    root.mkdir()
    for filename in FILENAMES.values():
        (root / filename).touch()
    search = []
    for year, indices in ((2025, [10, 20, 90, 30, 44, 20]), (2026, [100, 20, 30, 35, 25, 10])):
        # 5월 최고치는 W2의 전년 동기간 판정에 쓰이지만 여름 최고치에는 들어가지 않는다.
        search.extend({"month": f"{year}-{month:02}", "keyword": "수박화채", "search_index": value}
                      for month, value in zip(range(5, 11), indices, strict=True))
    _write("trend", search)
    _write("assets", [
        {"name": "수박 맛 견본 음료", "brand": "밀키스", "status": "단종", "launched": "2019-06-01"},
        {"name": "수박 맛 개발 견본", "brand": "밀키스", "status": "개발중단", "launched": "2022-06-01"},
    ])
    wtp = {"p25": 1100, "median": 1600, "p75": 2200, "n": 41}
    (root / "survey_summary.json").write_text(json.dumps({"concepts": {"밀키스 화채": {"wtp": wtp}}}), encoding="utf-8")
    monkeypatch.setattr(catalog, "current", lambda: (
        _product(1300, volume=300), _product(1900, sku="syn"), _product(2300),
        _product(500, ours=True), _product(9999, pack=2), _product(8999, kind="주스"),
    ))
    result = diagnose.demo_diagnosis()
    assert "2025년 90, 2026년 35" in result["trend"]
    assert "피크아웃" not in result["trend"]
    assert "2019년" in result["history"] and "2022년" not in result["history"]
    assert "사유 기록 없음" in result["history"]
    assert all(term in result["price"] for term in ("500mL PET", "응답자 41명", "1,600원", "1,100원~2,200원", "200원 높아요"))
    assert "타사 단품 탄산 3종은 1,300원~2,300원" in result["competition"]
    assert "500mL PET는 2종이 1,900원~2,300원" in result["competition"]
    assert "상온" in result["distribution"] and "자료 없음" in result["distribution"]
    assert result["alternative"] == "자료 없음"


def test_missing_data_still_shows_concept_conditions():
    result = diagnose.demo_diagnosis()
    assert all("자료 없음" in line for line in result.values())
    assert "1,800원" in result["price"]
    assert "상온" in result["distribution"]


@pytest.mark.parametrize(("text", "ids", "n", "view", "mode", "said"), [
    ("밀키스 화채 데모를 보여줘", [], 1, "room", "fgd", "창작 대본"),
    ("", ["w7-demo-fgi"], 2, "room", "fgi", "집단 심층 인터뷰"),
    ("FGI랑 FGD가 어떻게 달라요?", [], 3, "room", "fgd", "1차에 각자 답한 뒤"),
    ("경쟁 가격을 비교해 줘", [], 4, "diagnosis", "fgd", "최대 지불의향가격"),
    ("탄산을 빼면 어때?", [], 5, "compare", "fgd", "제형 변경안"),
    ("수박화채 맛을 옅게 하면?", [], 6, "compare", "fgd", "맛을 은은하게"),
    ("전체 시장규모도 알아봐 줘", [], 7, "room", "fgd", "이 데모에서는"),
])
def test_demo_chat_turn_opens_the_correct_view(text, ids, n, view, mode, said):
    async def collect():
        return [event async for event in machine.turn("w7-demo-test", text, ids, n)]

    stage, say, card, actions = asyncio.run(collect())
    assert stage.current == card.stage == "result"
    assert said in say.text
    assert (card.id, card.kind, card.status) == ("w7-room", "group", "ready")
    payload = card.payload
    assert (payload["view"], payload["mode"], payload["turn"]) == (view, mode, n)
    assert payload["demo"] and payload["comparison"]["demo"]
    if "맛을 옅게" in text:
        assert payload["comparison"]["focus"] == "flavor"
    assert len(actions.actions) == 3


def test_saved_quote_sets_the_variant_and_keeps_its_source():
    say, card, _ = diagnose.demo_turn("개선안 만들기", ["w7-quote/fgd-2-p3"], 2)
    assert "FGD 2차" in say.text
    assert card.payload["quoteId"] == "fgd-2-p3"
    assert card.payload["comparison"]["focus"] == "price"
