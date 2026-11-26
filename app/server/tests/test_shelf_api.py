"""GET /api/shelf(지시서 13): 입체 매장의 매대에 올릴 제품 목록."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main
from tools.shelf_items import container_of

client = TestClient(main.app)
CONTAINERS = {"캔", "페트", "병", "팩", "컵"}


@pytest.fixture(autouse=True)
def no_onsite_tables(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path / "missing"))


def test_beverage_shelf_items_without_onsite_data():
    res = client.get("/api/shelf", params={"shelf": "음료"})
    assert res.status_code == 200
    body = res.json()
    assert body["shelf"] == "음료"
    items = body["items"]
    assert len(items) == 55
    ids = [i["id"] for i in items]
    assert len(set(ids)) == len(ids)
    for i in items:
        assert set(i) >= {"id", "name", "kind", "container", "volume", "pack", "price", "promo", "ours",
                          "sku", "is_own"}
        assert i["container"] in CONTAINERS
        assert i["price"] > 0
        assert i["promo"] != "행사 없음"
        assert isinstance(i["is_own"], bool) and i["ours"] == i["is_own"] and i["sku"] is None
    cider = next(i for i in items if i["name"] == "칠성사이다 캔 355ml")
    assert cider == {**cider, "kind": "탄산", "container": "캔", "volume": 355, "price": 2100, "promo": "2+1", "ours": True}
    coke = next(i for i in items if i["name"].startswith("코카콜라 제로"))
    assert coke["container"] == "페트" and coke["ours"] is False


def test_default_shelf_is_beverage_and_unknown_is_404():
    assert client.get("/api/shelf").json()["shelf"] == "음료"
    assert client.get("/api/shelf", params={"shelf": "과자"}).status_code == 404
    assert len(client.get("/api/shelf", params={"shelf": "주류"}).json()["items"]) == 32


def test_container_rule():
    assert container_of("", "칠성사이다 캔 355ml", "탄산") == "캔"
    assert container_of("", "펩시 제로슈거 라임 페트 500ml", "탄산") == "페트"
    assert container_of("", "스타벅스 카페라떼 컵 320ml", "커피") == "컵"
    assert container_of("", "제주삼다수 생수 2L", "물") == "페트"
    assert container_of("", "서울우유 흰 우유 900ml", "우유·단백") == "팩"
    assert container_of("병", "아무 이름", "소주") == "병"
