"""탐색 결과가 다음 질문과 여정 분모에 실제로 반영되는지 확인한다."""

import asyncio
from types import SimpleNamespace

import pytest

from llm.base import LLMError
from shelftest import journey as j, method


def test_patterns_are_joint_channel_counts_without_outcomes(monkeypatch):
    visits = [{"store_type": "편의점", "seconds": 9, "compared": 1, "bought": b} for b in (True, False)]
    visits += [{"store_type": "편의점", "seconds": 40, "compared": 4},
               {"store_type": "마트", "seconds": 80, "compared": 5},
               {"store_type": "편의점", "seconds": None, "compared": 4}]
    monkeypatch.setattr(j.onsite, "load", lambda _: visits)
    assert j.patterns() == [((9, 1), 2), ((40, 4), 1)]
    hist = j.patterns()
    assert j.visit_pattern(hist, "A", "D1", 7) in {(9, 1), (40, 4)}
    assert j.signature(hist) != j.signature(hist[:1])


@pytest.mark.parametrize("seen, shortlisted", [([0], []), ([1, 1], []), ([True], []), ([1], [2]), ([1, 2], [1, 2])])
def test_stage1_rejects_invalid_candidates(seen, shortlisted):
    with pytest.raises(method.BadAnswer):
        j.selections({"noticed": seen, "considered": shortlisted}, [1, 2], 1)


@pytest.mark.parametrize("seen, shortlisted, pick, feedback_fails", [
    ([1], [], 0, False), ([1, 2], [1], 0, False), ([2], [2], 1, False), ([2], [2], 1, True)])
def test_choice_and_feedback_are_gated_and_failure_preserves_purchase(monkeypatch, seen, shortlisted, pick, feedback_fails):
    rows = [{"상품명": "물"}, {"상품명": "신규음료"}]
    plan = SimpleNamespace(line="신규음료", storage=None, with_concept={})
    monkeypatch.setattr(method, "prompts", lambda *_: ("결정", "손님\n[음료 매대]\n1. 물\n2. 신규음료", rows))
    monkeypatch.setattr(j.pilot, "label", lambda p, *_: p["상품명"])
    monkeypatch.setattr(method, "display", lambda x: x)
    prompts = []
    async def ask(system, user, schema, parse):
        prompts.append(user)
        if "noticed" in schema["required"]:
            return parse({"noticed": seen, "considered": shortlisted})
        if "choice_number" in schema["required"]:
            assert "새 제품" not in user and ("신규음료" in user) == (2 in shortlisted)
            return parse({"choice_number": pick, "reason_sentence": "고릅니다."})
        if feedback_fails:
            raise LLMError("실패")
        return parse({"view": "이번에 산다", "barriers": [], "said": "고르겠어요."})
    row = asyncio.run(j.answer(plan, {"shelf_seconds": 28, "comparison_limit": 1}, method.CONCEPT, ask))
    assert row["number"] == (2 if pick else 0)
    assert len(prompts) == 1 + bool(shortlisted) + (2 in shortlisted)
    assert bool(row["journey"].get("feedback_missing")) == feedback_fails
    f = j.funnel([row, {"product": None}], plan.line)
    assert f["visits"] == 1 and f["noticed"] == (2 in seen) and f["considered"] == (2 in shortlisted)
    assert f["purchased"] == bool(pick) and (f["purchased_per_considered"] is None) == (2 not in shortlisted)


def test_online_funnel_requires_same_sku_strict_time_and_excludes_bots():
    def event(session, sku, timestamp, label, bot=False):
        return {"session": session, "sku": sku, "ts_kst": timestamp, "event": label, "is_bot": bot}

    stages = ["노출", "클릭", "상세보기", "장바구니", "구매"]
    rows = [event(1, "a", str(i), label) for i, label in enumerate(stages)]
    rows += [event(1, "b", "1", "노출"), event(2, "a", "1", "노출"), event(2, "b", "2", "클릭"),
             event(3, "c", "1", "클릭"), event(3, "c", "1", "노출"), event(3, "c", "2", "상세보기"),
             event(99, "d", "1", "노출", bot=True)]
    measured = j.online_reference(rows[::-1])
    assert measured["sessions"] == 3 and measured["stages"] == dict(zip(stages, [3, 1, 1, 1, 1]))
    assert measured["purchased_per_exposed"] == pytest.approx(1 / 3)
