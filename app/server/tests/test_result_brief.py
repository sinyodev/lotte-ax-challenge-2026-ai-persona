"""지시서 32의 A: 테스트 결과의 요약 구역(agent/result_brief.py). 모델을 부르지 않는다. 결과와 가상 소비자는 손으로 만든다."""

from __future__ import annotations

from agent import result_brief as RB
from agent.result_brief import Ctx, Visitor


def res(picked=49, n=300, rank=1, products=68, own=(("자사 아이스티", 3), ("자사 보리차", 2)), own_n=13, rival_n=29, none=7,
        barriers=(("맛이 끌리지 않음", 38), ("늘 마시는 것이 있음", 36), ("가격이 비쌈", 32))):
    own_rows = [{"name": a, "count": b} for a, b in own]
    if own_n > sum(b for _, b in own):
        own_rows.append({"name": "자사 기타", "count": own_n - sum(b for _, b in own)})
    return {"n": n, "picked": picked, "rank": rank if picked else None, "products": products, "low": 12.5, "high": 20.9,
            "from": {"own": own_rows if picked else [], "rival": [{"name": "경쟁 콜라", "count": rival_n}] if picked else [],
                     "none": none if picked else 0, "pending": 0},
            "barriers": [{"label": a, "count": b} for a, b in barriers], "quotes": {"picked": [], "passed": []}}


VISITORS = [Visitor("T001", "42세 남자, 회사원", [], True, True),
            Visitor("T002", "44세 남자, 교사", ["맛이 끌리지 않음"], False, False),
            Visitor("T003", "41세 남자, 기사", ["가격이 비쌈"], False, None)]


def ctx(r, improve=None, offers=None):
    view = {"id": "run-x", "concept": {"name": "밀키스 화채"}, "who": {"label": "40대 남자 손님"}}
    return Ctx(run_id="run-x", view=view, res=r, visitors=VISITORS, top_existing=("핫식스", 9), improve=improve,
               offers=offers or {})


def ids(b):
    return [a["id"] for a in b["actions"]]


def test_headline_range_and_points():
    b = RB.brief(ctx(res()))
    assert b["headline"] == "40대 남자 300명 중 49명이 골랐고, 매대 68개 가운데 1위예요"
    assert b["range"] == "범위 37~63명"
    assert [p["key"] for p in b["points"]] == ["how", "from", "why"]
    assert b["points"][1]["text"].startswith("고른 49명 중 29명은 원래 경쟁사 제품을, 13명은 우리 제품을")
    assert "자사 아이스티(3명)" in b["points"][1]["text"]
    assert b["points"][2]["text"] == "고르지 않은 251명이 가장 많이 든 까닭은 '맛이 끌리지 않음'(38명), 다음은 '늘 마시는 것이 있음'(36명)이에요."
    text = str(b)
    for w in ("손님", "구매", "원래 사던", "오차 범위"):
        assert w not in text.replace("가상 소비자를 인터뷰할게요", ""), w


def test_actions_price_interview_report():
    b = RB.brief(ctx(res()))
    assert ids(b) == ["improve", "interview-barrier/T002", "report"]
    improve, interview, report = b["actions"]
    assert improve["reason"] == "가격이 비싸다고 한 가상 소비자가 32명이에요." and improve["do"]["ids"] == ["improve"]
    assert interview["do"] == {"say": "더 물어볼 곳", "to": "w7-group", "ids": ["open", "run-x", "barrier:맛이 끌리지 않음"]}
    assert report["reason"] is None and report["do"]["ids"] == ["report"]


def test_actions_use_offer_ids_from_chat():
    b = RB.brief(ctx(res(), offers={"improve": ("after-result-12", "개선안 보기")}))
    assert b["actions"][0]["do"] == {"say": "개선안 보기", "to": "after-result-12", "ids": ["improve"]}


def test_price_already_run_is_not_recommended_again():
    imp = {"base_run": "run-x", "items": [{"id": "A", "kind": "price", "run_id": "run-p"}]}
    b = RB.brief(ctx(res(), improve=imp))
    assert "improve" not in ids(b) and ids(b)[0] == "improve-compare"


def test_price_rule_by_rank_or_share():
    # 가격이 네 번째지만 지나친 사람의 10% 이상이면 권한다
    r = res(barriers=(("맛이 끌리지 않음", 60), ("늘 마시는 것이 있음", 50), ("지금 상황에 안 맞음", 40), ("가격이 비쌈", 26)))
    assert "improve" in ids(RB.brief(ctx(r)))
    r = res(barriers=(("맛이 끌리지 않음", 60), ("늘 마시는 것이 있음", 50), ("지금 상황에 안 맞음", 40), ("가격이 비쌈", 5)))
    assert "improve" not in ids(RB.brief(ctx(r)))


def test_own_and_weak_rules_and_limit():
    r = res(own=(("자사 아이스티", 10),), own_n=20, rival_n=20, none=9, barriers=(("가격이 비쌈", 40),))
    assert ids(RB.brief(ctx(r))) == ["improve", "interview-own/T001", "report"]
    weak = res(picked=0, barriers=(("맛이 끌리지 않음", 100), ("가격이 비쌈", 80)))
    b = RB.brief(ctx(weak))
    assert ids(b) == ["concept-board", "improve", "report"] and b["actions"][0]["do"] == {"stage": "concept"}
    assert [p["key"] for p in b["points"]] == ["how", "why"]  # 고른 사람이 없으면 "평소 고르던 것"은 그리지 않는다
    assert b["headline"] == "40대 남자 300명 중 밀키스 화채를 고른 가상 소비자는 없었어요"
    assert len(b["actions"]) <= 3
    assert RB.lower_half(res(rank=35)) and not RB.lower_half(res(rank=34))  # 기존 67개 중 34개(50.7%) / 33개
