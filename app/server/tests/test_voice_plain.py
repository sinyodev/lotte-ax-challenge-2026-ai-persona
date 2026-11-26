"""바로 알아듣게(참가자의 검수, 11-25): 판정 이름, 칸 이름, 뜻 흐린 말을 거르고, 글틀과 근거 줄이 사람의 말인지 본다."""

from __future__ import annotations

import asyncio

import pytest

from agent import machine
from agent import phrases as P
from agent import voice
from agent.voice import Facts, check
from events import Activity


@pytest.mark.parametrize("text,why", [
    ("수박화채 흐름은 피크아웃이에요.", "피크아웃"),
    ("계절성 수요라서 여름에 팔아요.", "계절성 수요"),
    ("최근 소식 세 건도 실마리로 썼어요.", "실마리"),
    ("여름철 짧게 즐기는 느낌으로 냈어요.", "느낌으로"),
    ("밖에서 식사할 때 입가심으로 마시는 음용 상황으로 정했어요.", "칸 이름"),
    ("기획자의 생각을 살려 아이디어를 냈어요.", "칸 이름"),
    ("밀키스 화채를 20대 타깃의 여름 한정 제품으로 기획할게요.", "칸 이름"),
])
def test_jargon_and_field_labels_fail(text, why):
    got = check(text, Facts(turn="open", title="t", received=["밀키스 화채 20대"]))
    assert any(why in w for w in got), got


def test_plain_sentences_pass():
    facts = Facts(turn="ideas", title="t", received=["아이디어 세 개를 냈다", "올해 검색은 작년 7월의 39% 수준"],
                  question=True, suggest="컨셉으로", names=["20대"])
    for text in ["아이디어 세 개를 냈어요. 20대가 밖에서 식사할 때 마시는 여름 한정 음료예요. 마음에 드는 것을 골라 컨셉으로 만들어 볼까요?",
                 "올해 검색은 작년 7월의 39% 수준이에요. 그래서 여름에만 짧게 파는 제품으로 잡았어요. 이 방향으로 아이디어를 낼까요?"]:
        assert check(text, facts) == []


def test_ideas_basis_is_a_sentence_without_field_names():
    text = P.ideas_basis("20대", "밖에서 식사할 때 입가심", ["여름 한정"], 3)
    assert text == "20대가 밖에서 식사할 때 입가심으로 마시는 여름 한정 음료로 냈어요. 최근 기사 3건도 참고했어요."
    assert P.ideas_basis(None, "혼자 마실 때", [], 0) == "혼자 마시는 음료로 냈어요."
    assert P.ideas_basis("30대", None, ["아침에 마시는 탄산을 만들고 싶어요."], 0) == "30대가 마시는 음료로 냈어요."
    assert P.ideas_basis("20대", None, ["20대 타깃"], 0) == "20대가 마시는 음료로 냈어요."
    assert P.ideas_basis(None, None, [], 2) == "말씀하신 제품에서 바로 냈어요. 최근 기사 2건도 참고했어요."
    assert P.when_phrase("20대", "집에서 가족과 간식 자리") == "20대가 집에서 가족과 간식 자리에서 마실 때"
    for t in (text, P.when_phrase("20대", "일하다가 혼자 한 잔")):
        assert not voice.FIELD_LABEL.search(t)


def test_risk_is_told_in_plain_words():
    from agent.research import plain_risk

    v = {"keyword": "수박화채", "stage": ["피크아웃", "계절성 수요"],
         "reasons": ["2026년 최고 검색 지수는 31로, 지난해 같은 기간 최고치(80)의 39%예요.",
                     "두 해 모두 7월에 검색이 가장 많았어요. 각 해의 낮은 달과 높은 달의 검색 지수는 5~80, 4~31였어요."]}
    text, required = plain_risk(v)
    assert text == "수박화채는 해마다 7월에 가장 많이 찾아요. 올해 검색은 작년 7월의 39% 수준이에요."
    assert required == ["39%"]
    assert check(text, Facts(turn="open", title="t", found=[text])) == []


def test_done_activity_names_what_was_done(monkeypatch):
    assert P.act_done(P.ACT_IDEAS) == "아이디어를 냈어요"
    assert all(not v.endswith("중") for v in P.ACT_DONE.values())

    async def fake_turn(*a, **k):
        for ev in [Activity(id="a", label=P.ACT_READ, status="running"),
                   Activity(id="a", label=P.ACT_LOOK, status="running"),
                   Activity(id="a", label=P.ACT_IDEAS, status="running"),
                   Activity(id="a", label=P.ACT_LOOK, status="running"),
                   Activity(id="a", label=P.ACT_LOOK, status="done"),
                   Activity(id="b", label=P.ACT_LOOK, status="running"),
                   Activity(id="b", label=P.ACT_LOOK, status="done")]:
            yield ev

    monkeypatch.setattr(machine, "_turn", fake_turn)

    async def collect():
        return [e async for e in machine.turn("x", "t", [], 1)]

    done = [e.label for e in asyncio.run(collect()) if e.status == "done"]
    assert done == ["아이디어를 냈어요", "찾아봤어요"]
