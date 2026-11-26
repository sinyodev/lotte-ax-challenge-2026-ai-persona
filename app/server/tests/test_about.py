"""칠성이 소개: 고정된 말, 모델을 부르지 않는다."""

from agent import machine, phrases as P
from agent.note import Note


def test_cue():
    assert machine.wants_about(P.ABOUT_ASK)
    assert machine.wants_about("넌 뭘 할 수 있어?")
    assert not machine.wants_about("제로 탄산으로 무엇을 할 수 있을지 20대 여성 타깃으로 같이 생각해 보고 싶어요")
    assert not machine.wants_about("제로 탄산 신제품")


def test_chips_leave_out_the_one_shown():
    ids = [o.id for o in machine.about_choices(Note(), "about-talk").options]
    assert ids == ["about-flow", "about-screen", "recommend"]
    assert set(P.ABOUT) == {"about", *(i for i, _ in P.ABOUT_CHIPS)}


def test_no_banned_words():
    for text in P.ABOUT.values():
        assert not any(w in text for w in ("AI", "에이전트", "페르소나", "시뮬레이션", "프롬프트", "모델", "욕구", "실험"))
