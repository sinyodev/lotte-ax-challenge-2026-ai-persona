"""새로움 욕구(N08) 보정: 지어낸 작은 표로 확인한다."""

from collections import Counter
import hashlib

import pytest

from calibrate import novelty


def table(n=200, band="19-29"):
    # 패널처럼 센 분포: 3점 35%, 2점 50%, 1점 14%, 0점 1%
    levels = [3] * int(n * .35) + [2] * int(n * .5) + [1] * int(n * .14)
    levels += [0] * (n - len(levels))
    return {f"u{i:04d}": {"uuid": f"u{i:04d}", "연령대": band, "N08": str(v), "N01": "2"}
            for i, v in enumerate(levels)}


@pytest.mark.parametrize("mode", ["survey", "strict"])
def test_distribution_matches_target(mode):
    rows = table(1000)
    out = novelty.apply(rows, mode)
    counts = Counter(int(r["N08"]) for r in out.values())
    for level, share in novelty.levels("19-29", mode).items():
        assert abs(counts[level] / 1000 - share) <= 0.002
    assert sum(counts.values()) == 1000


def test_order_is_kept():
    rows = table(300)
    out = novelty.apply(rows, "survey")
    # 원래 N08이 더 높은 사람이 보정 뒤에 더 낮아지지 않는다.
    for a in rows:
        for b in list(rows)[::17]:
            if int(rows[a]["N08"]) > int(rows[b]["N08"]):
                assert int(out[a]["N08"]) >= int(out[b]["N08"])
    # 같은 원점수 안에서는 md5(uuid) 순으로 높은 단계를 받는다.
    same = sorted((u for u in rows if rows[u]["N08"] == "2"), key=lambda u: hashlib.md5(u.encode()).hexdigest())
    got = [int(out[u]["N08"]) for u in same]
    assert got == sorted(got, reverse=True)


def test_deterministic_and_original_untouched():
    rows = table(200)
    before = {k: dict(v) for k, v in rows.items()}
    assert novelty.apply(rows, "strict") == novelty.apply(dict(reversed(list(rows.items()))), "strict")
    assert rows == before
    out = novelty.apply(rows, "survey")
    assert all(out[k]["N01"] == rows[k]["N01"] for k in rows)


def test_old_bands_use_fifties():
    assert novelty.levels("70+", "survey") == novelty.levels("50-59", "survey")
    out = novelty.apply(table(100, "60-69"), "survey")
    assert Counter(int(r["N08"]) for r in out.values())[3] == round(100 * novelty.TARGET["50-59"]["5"])


def test_off_keeps_everything(monkeypatch):
    rows = table(50)
    assert novelty.apply(rows, "off") is rows
    assert novelty.signature("off") == ""
    monkeypatch.setenv("AX_NOVELTY", "nope")
    with pytest.raises(ValueError):
        novelty.mode()


def test_shelf_version(monkeypatch):
    from shelftest import method
    monkeypatch.setenv("AX_LLM", "codex")
    monkeypatch.delenv("AX_EFFORT_SHOPPER", raising=False)
    monkeypatch.setenv("AX_NOVELTY", "off")
    base = method.shelf_v(11)
    monkeypatch.delenv("AX_NOVELTY")
    if novelty.DEFAULT == "off":
        assert method.shelf_v(11) == base
    versions = {base}
    for mode in ("survey", "strict"):
        monkeypatch.setenv("AX_NOVELTY", mode)
        versions.add(method.shelf_v(11))
    assert len(versions) == 3
    monkeypatch.setenv("AX_NOVELTY", "survey")
    v4 = method.shelf_v(4)
    monkeypatch.setenv("AX_NOVELTY", "off")
    assert method.shelf_v(4) == v4


def test_plan_calibrates_only_gpt_round(monkeypatch):
    from shelftest import method
    monkeypatch.setenv("AX_NOVELTY", "strict")
    original = method.base_ctx()["strength"]
    p11 = method.plan(None, None, None, 2, "견본", 1000, None, round_number=11)
    p9 = method.plan(None, None, None, 2, "견본", 1000, None, round_number=9)
    assert p9.plain["strength"] is original
    assert p11.plain["strength"] is not original
    assert p11.with_concept["strength"] is p11.plain["strength"]
    assert max(int(r["N08"]) for r in p11.plain["strength"].values() if r.get("N08")) <= 2
    monkeypatch.setenv("AX_NOVELTY", "off")
    assert method.plan(None, None, None, 2, "견본", 1000, None, round_number=11).plain["strength"] is original


def _concept_plan(round_number=11):
    from types import SimpleNamespace
    ctx = {"products": [{"상품명": "X", "가격(원)": "1800", "행사": "행사 없음"}],
           "needs": [{"번호": "N08"}, {"번호": "N09"}], "fulfills": {}}
    return SimpleNamespace(line="X", round_number=round_number, with_concept=ctx)


@pytest.mark.parametrize("value, expected", [("well", "잘 채움"), ("partly", "조금 채움"), ("none", None)])
def test_concept_novelty_relation(monkeypatch, value, expected):
    from tools import shelf_items
    monkeypatch.setenv("AX_CONCEPT_NOVELTY", value)
    concept = {"volume": 500, "container": "페트", "kind": "탄산", "appeal": "여름 한정"}
    plan = shelf_items.enrich_concept(_concept_plan(), concept)
    assert plan.with_concept["fulfills"]["X"].get("N08") == expected
    assert plan.with_concept["products"][0]["소구점"] == "여름 한정"  # 사실 표기는 남는다
    # 4차는 그대로 잘 채움.
    assert shelf_items.enrich_concept(_concept_plan(4), concept).with_concept["fulfills"]["X"]["N08"] == "잘 채움"


def test_concept_novelty_shelf_version(monkeypatch):
    from shelftest import method
    from tools import shelf_items
    monkeypatch.setenv("AX_LLM", "codex")
    monkeypatch.delenv("AX_EFFORT_SHOPPER", raising=False)
    monkeypatch.setenv("AX_NOVELTY", "strict")
    monkeypatch.setenv("AX_CONCEPT_NOVELTY", "well")
    well = method.shelf_v(11)
    versions = {well}
    for value in ("partly", "none"):
        monkeypatch.setenv("AX_CONCEPT_NOVELTY", value)
        versions.add(method.shelf_v(11))
    assert len(versions) == 3
    monkeypatch.delenv("AX_CONCEPT_NOVELTY")
    if shelf_items.CONCEPT_NOVELTY_DEFAULT == "well":
        assert method.shelf_v(11) == well
    monkeypatch.setenv("AX_CONCEPT_NOVELTY", "bad")
    with pytest.raises(ValueError):
        shelf_items.concept_novelty()
