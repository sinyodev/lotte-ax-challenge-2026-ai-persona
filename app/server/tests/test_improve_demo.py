from types import SimpleNamespace

from agent.improve import demo_comparison
from shelftest import catalog


def _product(price, *, sku=None, kind="탄산", own=False, pack=1):
    return SimpleNamespace(price=price, sku=sku, shelf="음료", kind=kind, is_own=own, pack=pack)


def test_demo_price_uses_distinct_rival_prices_from_joined_shelf(monkeypatch):
    products = (
        _product(1200), _product(1500, sku="rival"), _product(1650), _product(1200), _product(1750),
        _product(1250, own=True), _product(1300, pack=2), _product(1320, kind="탄산수"), _product(0),
    )
    monkeypatch.setattr(catalog, "current", lambda: products)

    comparison = demo_comparison()

    assert comparison["priceStep"] == {
        "source": "joined-shelf", "step": 200, "medianGap": 150, "rivalCount": 5, "distinctPrices": 4,
    }
    lower, original, higher = comparison["pricePoints"]
    assert [lower["price"], higher["price"]] == [original["price"] - 200, original["price"] + 200]
    assert higher["selection"]["rate"] < original["selection"]["rate"] < lower["selection"]["rate"]


def test_demo_fallback_is_labelled_and_paired_counts_reconcile(monkeypatch):
    monkeypatch.setattr(catalog, "current", lambda: (_product(1200), _product(1500)))

    comparison = demo_comparison()

    assert comparison["demo"] is True
    assert comparison["priceStep"] == {"source": "demo", "step": 100}
    assert comparison == demo_comparison()
    original = comparison["base"]["selection"]
    assert original == comparison["pricePoints"][1]["selection"]
    for variant in comparison["variants"].values():
        selection, paired = variant["selection"], variant["paired"]
        assert selection["n"] == original["n"]
        assert selection["picked"] == original["picked"] + paired["gained"] - paired["lost"]
        assert 0 <= paired["gained"] <= original["n"] - original["picked"]
        assert 0 <= paired["lost"] <= original["picked"]
        assert paired["difference"] == round(100 * (selection["picked"] - original["picked"]) / original["n"], 1)
        assert paired["interval"][0] <= paired["difference"] <= paired["interval"][1]
        assert selection["interval"][0] <= selection["rate"] <= selection["interval"][1]
    assert comparison["variants"]["price"]["selection"] == comparison["pricePoints"][0]["selection"]
