"""제품 특징을 바꿔도 같은 손님·상황·글틀을 유지하고 종전 기준 매대의 답을 재사용한다."""

import asyncio
from dataclasses import replace
from hashlib import sha256

import pytest

from llm.base import set_llm
from llm.fake import FakeLLM
from shelftest import method, runner, store


def spec():
    return runner.Spec(chat_id="w7-test", concept_id="a", name="견본 과일음료", container="캔",
                       volume=250, price=1900, total=1, features={"form": "탄산", "flavor": "배"})


async def finish(s):
    run_id = runner.create(s)
    if task := runner.TASKS.get(run_id):
        await task
    return store.load_meta(run_id)


def digest(text):
    return sha256(text.encode()).digest()


def test_form_changes_only_printed_form_and_reuses_the_same_baseline():
    fake = FakeLLM()
    set_llm(fake)
    original = asyncio.run(finish(spec()))
    before = fake.calls[0]["user"]
    plan = runner._plan(original)
    old_system, old_user, _ = method.prompts(plan, plan.visits[0], method.BASELINE)
    assert digest(fake.calls[1]["user"]) == digest(old_user)
    assert digest(fake.calls[1]["system"]) == digest(old_system)
    cached = store.baselines(original["shelf_v"], original["model"])
    changed = replace(spec(), mode="improve", base_run_id=original["id"], change={"form": "무탄산"},
                      features={"form": "무탄산", "flavor": "배"})
    variant = asyncio.run(finish(changed))
    after = fake.calls[-1]["user"]
    assert len(fake.calls) == 3
    assert "무탄산" in after
    assert digest(before) == digest(after.replace("무탄산", "탄산"))
    assert original["participants"] == variant["participants"]
    assert variant["base_run_id"] == original["id"]
    assert variant["id"] != original["id"]
    assert asyncio.run(finish(changed))["id"] == variant["id"]
    assert store.baselines(original["shelf_v"], original["model"]) == cached
    assert [row.get("reused") for row in store.answers(variant["id"]) if row["cond"] == method.BASELINE] == [True]


@pytest.mark.parametrize("key", ["shelf_v", "model", "shopper_adapter"])
def test_rejects_different_shelf_or_responder(key):
    original = asyncio.run(finish(spec()))
    original[key] = "different"
    store.save_meta(original)
    with pytest.raises(ValueError, match="원래 안을 다시 테스트"):
        runner.create(replace(spec(), mode="improve", base_run_id=original["id"], price=1800))


def test_legacy_record_reopens_without_reusing_its_concept_answers():
    fake = FakeLLM()
    set_llm(fake)
    original = asyncio.run(finish(spec()))
    original.pop("concept_prompt_version")
    original.pop("shopper_adapter")
    original["concept"].pop("form")
    original["concept"].pop("flavor")
    original["fp"] = "old-format-key"
    store.save_meta(original)
    assert runner.view(original["id"])["status"] == "done"
    assert not runner._plan(original).with_concept.get("concept_prompt_version")
    with pytest.raises(ValueError, match="원래 안을 다시 테스트"):
        runner.create(replace(spec(), mode="improve", base_run_id=original["id"], change={"form": "무탄산"}))
    current = asyncio.run(finish(spec()))
    assert current["id"] != original["id"]
    assert current["concept_prompt_version"] == runner.CONCEPT_PROMPT_VERSION
    assert len(fake.calls) == 3
