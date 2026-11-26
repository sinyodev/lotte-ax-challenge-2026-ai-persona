"""작은 합성 손님 표본으로 탐색, 타깃과 개선안의 배정을 확인한다."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import main
from llm.base import set_llm
from llm.fake import FakeLLM
from shelftest import explore, method, result, runner, store

OCCASIONS = {"D1": {"상황": "집에서 혼자"}, "D2": {"상황": "밖에서 식사"}}
PROFILE = "합성 손님의 비공개 서술"


def spec(**kwargs):
    return runner.Spec(**{"chat_id": "test-chat", "concept_id": "a", "name": "견본 음료", "container": "캔",
                          "volume": 250, "price": 1200, **kwargs})


@pytest.fixture
def panel(monkeypatch, tmp_path):
    people = [
        method.Person(f"sample-{i}-{j}", sex, age, int(age[:2]) + j, "", (None, None, None, None, PROFILE, ""))
        for i, (age, sex) in enumerate(explore.CELLS) for j in range(3)
    ]
    monkeypatch.setenv("AX_EXPLORE_PER_CELL", "2")
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path / "missing-onsite"))
    monkeypatch.setattr(method, "people", lambda age, sex: tuple(
        p for p in people if (age is None or p.band == age) and (sex is None or p.sex == sex)
    ))
    monkeypatch.setattr(method, "occasions", lambda: OCCASIONS)
    monkeypatch.setattr(method, "shelf_v", lambda: "test-shelf")
    monkeypatch.setattr(runner, "occasion_share", lambda a, s, code: 25 if code else None)
    monkeypatch.setattr(method, "placement", lambda name, storage:
                        {"storage": storage, "store_rate": 31.0} if storage == "냉동" else None)
    monkeypatch.setattr(result, "catalog_snapshot", lambda: [["견본 기존 상품", "견본 기존 상품", True]])

    def plan(age, sex, occasion, total, line, price, promo, *, participants=None, storage=None, season=None, launch=None):
        selected = list(method.people(age, sex) if participants is None else participants)[:total]
        visits = []
        for i, p in enumerate(selected):
            code = occasion if occasion and i < total // 2 else ("D1" if p.uuid.endswith("-0") else "D2")
            visits.append({"방문": f"T{i + 1:03}", "uuid": p.uuid, "연령대": p.band, "성별": p.sex,
                           "상황 번호": code, "상황": OCCASIONS[code]["상황"]})
        return method.Plan(visits, {}, {}, line, {p.uuid: p for p in selected})

    def prompts(test, visit, condition):
        names = ["견본 기존 상품"] if condition == method.BASELINE else ["견본 기존 상품", test.line]
        kind = "컨셉" if condition == method.CONCEPT else "기준"
        user = f"{visit['uuid']} {visit['상황 번호']} {kind} {PROFILE}"
        return "견본 손님", user, [{"상품명": name} for name in names]

    def answer(system, user, schema):
        asked = "new_product" in schema["properties"]
        picked = asked and user.startswith("sample-0-")
        return {"choice_number": 2 if picked else 1,
                "new_product": {"view": method.VIEWS[0] if picked else method.VIEWS[1], "barriers": [], "said": ""}}

    monkeypatch.setattr(method, "plan", plan)
    monkeypatch.setattr(method, "prompts", prompts)
    fake = FakeLLM({"shopper": answer})
    set_llm(fake)
    return people, fake


async def finish(s):
    run_id = runner.create(s)
    task = runner.TASKS.get(run_id)
    if task is not None:
        await task
    return run_id


def test_explore_interleaves_and_excludes_every_scheduled_person(panel, monkeypatch):
    people, fake = panel
    people.pop(0)  # 첫 칸은 정원만큼은 남고 타깃으로 뽑을 손님이 없다.
    people[:] = [p for p in people if p.uuid not in ("sample-7-0", "sample-7-1")]

    async def scenario():
        search = runner.create(spec(mode="explore", age="50-59", sex="남자", occasion_code="D1"))
        early = runner.view(search)
        assigned = store.load_meta(search)["participants"]
        assert early["requested"] == 16 and early["total"] == 15 and early["asked"] == 0
        assert [(p["age"], p["sex"]) for p in assigned[:8]] == list(explore.CELLS)
        assert [p["occasion"] for p in assigned] == ["D2", *["D1"] * 6, "D2", *["D2"] * 7]
        assert [c["total"] for c in early["explore"]["cells"]] == [2] * 7 + [1]
        assert all(c["n"] == 0 and c["rate"] is None for c in early["explore"]["cells"])
        assert PROFILE not in json.dumps([early, store.load_meta(search)], ensure_ascii=False)
        assert "uuid" not in json.dumps(early)
        assert runner.stop(search)  # 탐색의 응답은 0이지만 배정된 손님 전부를 제외한다.

        no_one = await finish(spec(age="19-29", sex="여자", total=9, explore_id=search))
        assert runner.view(no_one)["requested"] == 9 and runner.view(no_one)["total"] == 0
        target = await finish(spec(age="30-39", sex="여자", total=9, explore_id=search,
                                   target_basis="견본 근거", storage="냉동", occasion_code="D1"))
        target_meta = store.load_meta(target)
        assert target_meta["participants"] == [{"visit": "T001", "uuid": "sample-2-2", "age": "30-39",
                                                 "sex": "여자", "occasion": "D1"}]
        assert target_meta["shelf_products"] == result.catalog_snapshot()
        assert len(fake.calls) == 2 and [call["user"].split()[2] for call in fake.calls] == ["컨셉", "기준"]

        people.reverse()  # 다시 열어도 원래 타깃의 손님과 상황을 그대로 쓴다.
        change = runner.apply_change(spec(age="30-39", sex="여자", total=9, explore_id=search,
                                          target_basis="견본 근거", storage="냉동", occasion_code="D1",
                                          base_run_id=target), {"price": 1100})
        updated = await finish(change)
        updated_meta = store.load_meta(updated)
        assert updated_meta["participants"] == target_meta["participants"] and updated_meta["mode"] == "improve"
        assert len(fake.calls) == 3 and runner.view(updated)["usage"]["calls"] == 1

        monkeypatch.setenv("AX_EXPLORE_PER_CELL", "1")
        another = await finish(spec(mode="explore"))
        assert another != search
        another_target = await finish(spec(age="30-39", sex="여자", total=9, explore_id=another))
        assert another_target != target and runner.view(another_target)["total"] == 2
        return target

    target = asyncio.run(scenario())
    with TestClient(main.app) as client:
        body = client.get(f"/api/runs/{target}").json()
    assert body["placement"] == {"storage": "냉동", "store_rate": 31.0}
    assert body["target_basis"] == "견본 근거" and body["usage"]["calls"] == 2


def test_explore_population_weighting_and_recommendation(panel, tmp_path, monkeypatch):
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path))
    with (tmp_path / "population.csv").open("w", encoding="utf-8") as stream:
        stream.write("dimension,age_band,gender,region,share\n")
        stream.write("region,,,견본,1\n")
        for age in explore.AGES:
            for gender in explore.SEXES:
                share = 0.3 if (age, gender) == ("19~29세", "여성") else 0.1
                stream.write(f"age_gender,{age},{gender},,{share}\n")
    search = asyncio.run(finish(spec(mode="explore")))
    meta = store.load_meta(search)
    actual = runner.view(search)["explore"]
    assert actual["weighting"] == "population" and actual["overall_rate"] == 30.0
    assert actual["overlap"] and actual["suggested"] is None
    assert actual["cells"][0] == {"age": "19-29", "sex": "여자", "label": "20대 여자", "total": 2,
                                  "n": 2, "picked": 2, "rate": 100.0, "low": 34.2, "high": 100.0}
    assert sum(o["n"] for o in actual["occasions"]) == 16 and sum(o["picked"] for o in actual["occasions"]) == 2

    # 첫 칸만 응답한 도중에는 다른 집단을 0%로 포함하지 않는다.
    pairs, _ = result.concept_visits(store.answers(search))
    partial = explore.summarize(meta, [pair for pair in pairs if pair[1]["uuid"].startswith("sample-0-")])
    assert partial["overall_rate"] == 100.0 and partial["cells"][1]["rate"] is None
    assert partial["cells"][1]["low"] is None and partial["suggested"] is None
    assert explore.summarize(meta, [])["overall_rate"] is None

    # 표본을 늘리면 확실히 떨어진 구간일 때만 우세 집단을 제안한다.
    meta["participants"] = []
    strong = []
    for i, (age, sex) in enumerate(explore.CELLS):
        for j in range(40):
            v = f"T{i}-{j}"
            meta["participants"].append({"visit": v, "age": age, "sex": sex})
            strong.append((None, {"visit": v, "occasion": "D1", "product": meta["line"] if i == 0 else "기존"}))
    clear = explore.summarize(meta, strong)
    assert clear["suggested"] == {"age": "19-29", "sex": "여자", "label": "20대 여자"} and not clear["overlap"]
    meta["population_weights"] = None
    equal = explore.summarize(meta, strong)
    assert equal["weighting"] == "equal" and equal["overall_rate"] == 12.5
    zero = explore.summarize(meta, [(None, {**c, "product": "기존"}) for _, c in strong])
    assert zero["overall_rate"] == 0 and zero["suggested"] is None and zero["overlap"]
