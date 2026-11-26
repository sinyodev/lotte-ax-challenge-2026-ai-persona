"""같은 9차 방문의 관계와 매대 번호가 실제 11차 호출에서도 일치하는지 확인한다."""

import asyncio
import json

from llm.base import set_llm
from llm.fake import FakeLLM
from shelftest import interview, method, runner, store


def test_json_reaches_shopper_and_preserves_shelf_links(monkeypatch):
    monkeypatch.setenv("AX_LLM", "codex")
    monkeypatch.setenv("AX_MODEL_SHOPPER", "gpt-6-luna")
    monkeypatch.setenv("AX_EFFORT_SHOPPER", "low")
    monkeypatch.setenv("AX_SHOPPER_ROUND", "11")

    def answer(system, user, schema):
        assert "B01" in system
        if "choice_number" not in schema["properties"]:  # blind-v1: 고른 뒤의 새 상품 물음
            assert "[이미 고른 것]" in user and "이번에 산다" not in schema["properties"]["new_product"]["properties"]["view"]["enum"]
            return {"new_product": {"view": "다음에 살 수도 있다", "barriers": ["가격이 비쌈"], "said": "궁금해요."}}
        payload = json.loads(user)
        # 고르는 물음에서는 새 상품을 짚지 않는다(번호도, 따로 묻는 칸도 없다)
        assert "새_상품_번호" not in payload and "new_product" not in schema["properties"]
        return {"choice_number": 0, "reason_needs": ["B01"], "reason_other": "", "reason_sentence": "평소대로요."}

    fake = FakeLLM({"shopper": answer})
    set_llm(fake)
    spec = runner.Spec(chat_id="json", concept_id="coffee", name="견본 커피", container="캔", volume=250,
                       price=1700, promo="1+1", occasion_code="D1", total=2, features={"flavor": "진한 맛"})

    async def run():
        run_id = runner.create(spec)
        await runner.TASKS[run_id]
        return run_id

    run_id = asyncio.run(run())
    meta = store.load_meta(run_id)
    assert meta["shopper_round"] == 11
    assert meta["choice_method"] == runner.CHOICE_METHOD
    assert len(fake.calls) == 6  # 손님마다 기준 1번, 컨셉 매대에서 고르기 1번, 새 상품에 대한 생각 1번
    concept_rows = [r for r in store.answers(run_id) if r["cond"] == method.CONCEPT]
    assert [(r["product"], r["view"], r["barriers"]) for r in concept_rows] == [
        (method.NO_PURCHASE, "다음에 살 수도 있다", ["가격이 비쌈"])] * 2
    monkeypatch.setenv("AX_SHOPPER_ROUND", "9")
    assert meta["shelf_v"] != method.shelf_v()
    plan = runner._plan(meta)
    assert plan.round_number == 11
    visit = plan.visits[0]
    for condition, ctx in ((method.BASELINE, plan.plain), (method.CONCEPT, plan.with_concept)):
        _, user, order = method.prompts(plan, visit, condition)
        assert user in [c["user"] for c in fake.calls]
        payload = json.loads(user)
        assert payload["상황별_욕구_변화"]["B01"] == {"변화": 1.6, "근거": "자료"}
        assert payload["평소_욕구"]["B01"] == int(ctx["strength"][visit["uuid"]]["B01"])
        assert visit["uuid"] not in user
        if condition == method.CONCEPT:
            item = next(x for x in payload["매대"] if x["이름"] == plan.line)
            assert (item["이름"], item["가격_원"], item["행사"], item["맛"]) == (plan.line, 1700, "1+1", "진한 맛")
        for need, groups in payload["욕구별_상품_번호"].items():
            actual = {n: degree for degree, numbers in groups.items() for n in numbers}
            expected = {}
            for number, row in enumerate(order, 1):
                degrees = ctx["fulfills"].get(row["상품명"], {})
                if need in degrees:
                    expected[number] = degrees[need]
            assert actual == expected
    visitor = interview.find(run_id, visit["방문"])
    assert "평소_욕구" in json.loads(visitor.profile) and "매대" not in json.loads(visitor.profile)
