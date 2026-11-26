"""합성 POS·자산·인프라로 결합 매대와 과거 결과를 검증한다."""

import asyncio
import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
import onsite
from onsite.schema import CSV_COLUMNS
from shelftest import catalog, method, result, runner, store
from tools import shelf


def _write(root: Path, table: str, rows: list[dict]) -> None:
    pending = root / f"{table}.tmp"
    with pending.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS[table])
        writer.writeheader()
        writer.writerows(rows)
    pending.replace(root / f"{table}.csv")


def _sale(sku: str, **values) -> dict:
    return {
        "sku": sku, "name": "구름커피 270ml PET", "brand": "구름커피", "category": "PET커피",
        "month": "2026-03", "region": "견본 지역", "channel": "편의점", "units": 4,
        "amount": 6000, "promo": "없음", "is_own": "false", "after_end": "false", **values,
    }


@pytest.fixture
def onsite_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path))
    return tmp_path


def test_exact_match_and_unmatched_variants_are_shared_by_api_comparison_and_needs(onsite_dir):
    _write(onsite_dir, "pos_clean", [
        _sale("syn-01", name="밀키스 오리지널 340mL CAN", brand="밀키스", category="탄산",
              is_own="true", amount=2400, promo="1+1"),
        _sale("syn-02", name="밀키스 오리지널 340mL PET", brand="밀키스", category="탄산", is_own="true"),
        _sale("syn-03", name="밀키스 오리지널 230mL 캔", brand="밀키스", category="탄산", is_own="true"),
        _sale("syn-04", name="밀키스 제로 340mL 캔", brand="밀키스", category="탄산", is_own="true"),
        _sale("syn-05", name="밀키스 오리지널 340mL 캔", brand="다른 브랜드", category="탄산"),
    ])
    _write(onsite_dir, "assets", [
        {"asset_id": "syn-01-a", "sku": "syn-01", "name": "밀키스 오리지널 340mL 캔",
         "brand": "밀키스", "pack": "340mL 슬림캔", "status": "운영"},
    ])
    items = TestClient(main.app).get("/api/shelf").json()["items"]
    by_sku = {p["sku"]: p for p in items if p["sku"]}
    assert len(items) == 59
    assert by_sku["syn-01"]["name"] == "밀키스 캔 340ml"
    public = next(p for p in catalog.public() if p.key == by_sku["syn-01"]["id"])
    assert (by_sku["syn-01"]["price"], by_sku["syn-01"]["promo"]) == (
        public.price, None if public.promo == catalog.NO_PROMO else public.promo,
    )
    assert [by_sku[f"syn-0{i}"]["container"] for i in range(1, 5)] == ["캔", "페트", "캔", "캔"]
    assert all(by_sku[f"syn-0{i}"]["ours"] is True and by_sku[f"syn-0{i}"]["is_own"] for i in range(1, 5))
    assert not by_sku["syn-05"]["is_own"]
    zero = shelf.by_name(by_sku["syn-04"]["name"])
    assert zero and zero.sku == "syn-04" and zero.is_own and zero.is_zero
    needs = shelf.need_count(shelf.needs()["N05"], "음료")
    assert needs.total == len(items) and zero.name in needs.names
    assert shelf.kind_count("탄산").total == len(items)


def test_price_promo_and_asset_status_are_deterministic(onsite_dir):
    rows = [
        _sale("syn-a", month="2026-02", units=10, amount=14000, promo="1+1"),
        _sale("syn-a", region="견본 동부", units=2, amount=3200, promo="2+1"),
        _sale("syn-a", region="견본 서부", units=2, amount=3600, promo="할인10%"),
        _sale("syn-a", region="견본 남부", units=1, amount=1775),
        _sale("syn-a", channel="대형마트", units=100, amount=990000),
        _sale("syn-b", name="잔잔커피 270ml PET", brand="잔잔커피"),
        _sale("syn-c", name="푸른커피 270ml PET", brand="푸른커피"),
        _sale("syn-d", name="노을커피 270ml PET", brand="노을커피"),
        _sale("syn-e", name="들꽃커피 270ml PET", brand="들꽃커피", after_end="true"),
        _sale("syn-f", name="파도커피 270ml PET", brand="파도커피", units=0, amount=0),
    ]
    _write(onsite_dir, "pos_clean", rows)
    _write(onsite_dir, "assets", [
        {"asset_id": "b-1", "sku": "syn-b", "name": "잔잔커피 270ml PET", "status": "단종",
         "ended": "2026-02-28"},
        {"asset_id": "b-2", "sku": "syn-b", "name": "잔잔커피 리뉴얼 270ml PET", "status": "아이디어"},
        {"asset_id": "c-1", "sku": "syn-c", "name": "푸른커피 270ml PET", "status": "개발중단"},
        {"asset_id": "d-1", "sku": "syn-d", "name": "노을커피 270ml PET", "status": "단종",
         "ended": "2026-09-01"},
        {"asset_id": "d-2", "sku": "syn-d", "name": "노을커피 175ml 캔", "status": "단종",
         "ended": "2026-03-01"},
    ])
    added = {p.sku: p for p in catalog.current() if p.added}
    assert set(added) == {"syn-a", "syn-d"}
    assert (added["syn-a"].price, added["syn-a"].promo) == (1510, "2+1")
    version = method.shelf_v()
    _write(onsite_dir, "pos_clean", rows[::-1])
    assert method.shelf_v() == version


def test_pos_catalog_reloads_after_file_changes_only(onsite_dir, monkeypatch):
    before = method.shelf_v()
    calls = []
    load = onsite.load

    def count_load(name):
        calls.append(name)
        return load(name)

    monkeypatch.setattr(onsite, "load", count_load)
    _write(onsite_dir, "pos_clean", [_sale("syn")])
    first = method.shelf_v()
    assert first != before
    assert len(result.catalog_snapshot()) == 56
    assert shelf.by_name("구름커피 270ml PET").price == 1500
    assert calls == ["pos_clean"]
    _write(onsite_dir, "pos_clean", [_sale("syn", amount=6400)])
    assert method.shelf_v() != first
    assert shelf.by_name("구름커피 270ml PET").price == 1600
    assert calls == ["pos_clean", "pos_clean"]
    _write(onsite_dir, "assets", [
        {"asset_id": "syn-1", "sku": "syn", "name": "구름커피 270ml PET", "status": "단종"},
    ])
    assert method.shelf_v() == before
    (onsite_dir / "pos_clean.csv").unlink()
    assert method.shelf_v() == before


def test_plan_keeps_supplied_people_shelf_ids_and_storage(onsite_dir, monkeypatch):
    _write(onsite_dir, "pos_clean", [_sale("syn")])
    _write(onsite_dir, "infra", [
        {"channel": "편의점", "frozen_rate": 0.3, "chilled_rate": 0.8},
        {"channel": "대형마트", "frozen_rate": 0.8, "chilled_rate": 1.0},
    ])
    participants = list(reversed(method.people("19-29", "여자")[:3]))
    monkeypatch.setattr(method, "people", lambda *_: pytest.fail("이미 전달된 명단으로 방문해야 한다."))
    line = method.line_name("레쓰비 프리즈", "팩", 170)
    plan = method.plan(None, None, "D7", 1, line, 1800, None, participants=participants)
    assert [v["uuid"] for v in plan.visits] == [p.uuid for p in participants]
    assert method.placement("레쓰비 프리즈") == {"storage": "냉동", "store_rate": 30.0}
    assert method.placement("쥬시모먼트") == {"storage": "냉장", "store_rate": 80.0}
    assert method.placement("레쓰비 프리즈", "상온") is None
    assert method.placement("다른 제품") is None
    _, control, order = method.prompts(plan, plan.visits[0], method.BASELINE)
    _, treatment, with_concept = method.prompts(plan, plan.visits[0], method.CONCEPT)
    ids = {p[0] for p in result.catalog_snapshot()}
    assert {p["상품명"] for p in order} == ids
    assert {p["상품명"] for p in with_concept} == ids | {line}
    assert "구름커피 270ml PET — 1,500원" in control and "구름커피 270ml PET — 1,500원" in treatment
    assert "냉동 코너" not in control and "냉동 코너" in treatment
    (onsite_dir / "infra.csv").unlink()
    assert method.placement("레쓰비 프리즈") == {"storage": "냉동", "store_rate": None}


def test_result_preserves_snapshot_and_legacy_public_shelf(onsite_dir):
    _write(onsite_dir, "pos_clean", [_sale("syn", is_own="true")])
    snapshot = result.catalog_snapshot()
    own_key, own_name, is_own = snapshot[-1]
    assert is_own and len(snapshot) == 56
    _write(onsite_dir, "pos_clean", [_sale("syn", is_own="false")])
    assert not result.catalog_snapshot()[-1][2]
    rows = [
        {"visit": "T001", "cond": method.BASELINE, "product": own_key},
        {"visit": "T001", "cond": method.CONCEPT, "product": "우리 컨셉"},
    ]
    meta = {"line": "우리 컨셉", "concept": {"name": "우리 컨셉"}, "shelf_products": snapshot}
    saved = result.summarize(meta, rows, {})
    assert saved["from"]["own"] == [{"name": own_name, "count": 1}]
    assert saved["products"] == 57

    legacy = {k: v for k, v in meta.items() if k != "shelf_products"}
    public_own = next(p for p in catalog.public() if p.shelf == method.SHELF and p.is_own)
    legacy_rows = [{**rows[0], "product": public_own.key}, rows[1]]
    old = result.summarize(legacy, legacy_rows, {})
    assert old["from"]["own"] == [{"name": public_own.name, "count": 1}]
    assert old["products"] == 56


def test_fake_milkis_run_saves_combined_shelf_for_future_view(onsite_dir):
    _write(onsite_dir, "pos_clean", [_sale("syn")])
    snapshot = result.catalog_snapshot()

    async def run():
        spec = runner.Spec(chat_id="syn-chat", concept_id="syn-concept", name="밀키스 화채",
                           container="캔", volume=250, price=1200, age="19-29", total=4)
        run_id = runner.create(spec)
        await runner.TASKS[run_id]
        return run_id

    run_id = asyncio.run(run())
    assert store.load_meta(run_id)["shelf_products"] == snapshot
    assert runner.view(run_id)["status"] == "done"
    assert runner.view(run_id)["placement"] is None
    (onsite_dir / "pos_clean.csv").unlink()
    assert len(result.catalog_snapshot()) == 55
    assert runner.view(run_id)["result"]["products"] == 57
