"""칠성이의 말: 말로 바꾼 숫자, 검사기, 다시 쓰기와 글틀 (지시서 07의 4절 평가 세트). 모델을 부르지 않는다."""

from __future__ import annotations

import asyncio

import pytest

from agent import phrases as P
from agent import voice
from agent.voice import Facts, Turn, check
from llm.base import LLMError, LLMTimeout, set_llm
from llm.fake import FakeLLM
from tools import spoken

# ---------- 말로 바꾼 숫자의 경계값 ----------


@pytest.mark.parametrize("ratio,said", [
    (1.0, "비슷하게"), (1.09, "비슷하게"),
    (1.1, "조금 더"), (1.26, "조금 더"), (1.49, "조금 더"),
    (1.5, "두 배 가까이"), (1.8, "두 배 가까이"), (1.99, "두 배 가까이"),
    (2.0, "두 배 넘게"), (2.4, "두 배 넘게"), (2.49, "두 배 넘게"),
    (2.5, "세 배 가까이"), (2.9, "세 배 가까이"),
    (3.0, "세 배 넘게"), (3.4, "세 배 넘게"),
    (3.5, "네 배 가까이"),
    (4.0, "네 배 넘게"), (4.45, "네 배 넘게"),  # 제로 탄산 20대의 4.45배(카드에는 4.5배)
    (4.5, "다섯 배 가까이"),
    (9.6, "열 배 가까이"),
])
def test_times(ratio, said):
    assert spoken.times(ratio) == said


@pytest.mark.parametrize("pct,said", [
    (0, "열에 하나도 안 되게"), (4.4, "열에 하나도 안 되게"),
    (4.5, "열에 하나"), (14.4, "열에 하나"), (14.5, "열에 둘"),
    (34.4, "열에 셋"), (35, "열에 넷"), (41, "열에 넷"), (44.4, "열에 넷"),
    (44.5, "절반쯤"), (45, "절반쯤"), (50, "절반쯤"), (55, "절반쯤"), (55.4, "절반쯤"),
    (55.5, "절반 넘게"), (56, "절반 넘게"), (64, "절반 넘게"),
    (65, "열에 일곱"), (74, "열에 일곱"), (75, "열에 여덟"), (84, "열에 여덟"),
    (85, "열에 아홉"), (87, "열에 아홉"), (94, "열에 아홉"), (94.5, "거의 다"), (95, "거의 다"), (100, "거의 다"),
])
def test_share(pct, said):
    assert spoken.share(pct) == said


def test_when_words():
    assert spoken.when_word("시간대", "5 저녁(17~21시)") == "저녁에"
    assert spoken.when_word("장소", "가정") == "집에서"
    assert spoken.when_word("장소", "직장·학교") == "일터나 학교에서"
    assert spoken.when_word("음식 동반", "음식과 함께") == "밥 먹을 때"
    assert spoken.when_word("장소", "모르는 값") is None


# ---------- 검사기: 지침 4절의 전과 후 ----------

# 4절의 문장들. 숫자 검사를 위해 그 차례에 받았을 사실(이름)을 함께 준다.
NAMES = ["20대", "30대", "제로 탄산", "단백질 음료"]
BEFORE = [
    ("어떤 제품을 생각하세요? 한 줄로 적어 주시면 거기서 시작할게요.", False),
    ("기록에서 출발점 세 개를 골랐어요. 근거는 오른쪽에 있어요. 어느 것으로 시작할까요?", True),
    ("탄산음료로 볼게요. 먼저 최근 소식을 찾아봤어요. 오른쪽에 출처와 함께 적어 두었어요. 이제 누가 마실지 정해요. "
     "기록을 보면 탄산음료는 20대가 다른 음료보다 1.8배, 30대가 1.2배 자주 마셔요. 타깃을 누구로 볼까요?", True),
    ("기록에는 말차 라떼가 따로 없어서 가장 가까운 '차'의 기록으로 볼게요.", False),
    ("30대는 기록이 적어서 참고만 해 주세요.", False),
    ("20대로 볼게요. 20대는 제로 탄산을 저녁에(41%), 집에서(55%) 가장 많이 마셔요. 그리고 열 번에 아홉 번(87%)은 "
     "음식과 함께예요. 어느 상황을 겨냥할까요?", True),
    ('이 상황에서는 "몸에 좋은 성분 챙기기"와 "음식과 어울리게 마시기"가 커져요. 그래서 핵심 니즈를 '
     '"식사에 어울리며 몸에 좋은 성분도 챙기기"로 잡았어요. 이 니즈로 아이디어 세 개를 냈어요. 컨셉으로 만들 것을 골라 주세요.', False),
    ("고르신 아이디어로 컨셉 2장을 만들었어요. 가격은 매대의 비슷한 제품 가격의 가운데로 잡았어요. 이대로 확정할까요?", True),
    ("컨셉 2장을 확정했어요. 다음은 매대 테스트예요. 세븐일레븐 음료 매대에 올려서 손님이 고르는지 볼 수 있어요.", False),
    ("웹에서는 찾지 못했어요. 가진 자료로 진행할게요.", False),
    ("아이디어를 내다가 막혔어요. 다시 하기를 누르면 한 번 더 낼게요.", False),
    ("저는 음료와 식품의 신제품을 함께 기획해요. 어떤 제품을 생각하세요?", True),
    ("이 일은 아직 준비하고 있어요.", False),
]
AFTER = [
    ("어떤 제품을 생각하고 계세요?", "ask", True),
    ("요즘 눈에 띄는 게 세 가지 있어요. 제로 탄산은 20대가 유독 많이 마시고, 단백질 음료는 편의점에서 작년보다 더 팔렸어요. "
     "어떤 게 끌리세요?", "recommend", True),
    ("탄산음료로 기획해 볼게요. 탄산음료는 20대가 유독 즐겨 마셔요. 국민건강영양조사를 찾아보니 다른 음료보다 두 배 가까이 "
     "자주 마시더라고요. 20대부터 잡아 볼까요?", "target", True),
    ("말차 라떼만 따로 본 조사는 못 찾아서, 차를 마시는 사람들 쪽으로 찾아봤어요.", "target", False),
    ("30대는 조사된 사람이 적어서 참고만 해 주세요.", "target", False),
    ("20대는 제로 탄산을 주로 저녁에 집에서 마셔요. 열에 아홉은 밥 먹을 때고요. 저녁 식사 자리를 노려 볼까요?", "occasion", True),
    ('저녁 먹을 때는 음식이랑 잘 어울리는지, 몸에 좋은 게 들었는지를 더 따지더라고요. 그래서 "밥이랑 어울리면서 몸도 챙기는 '
     '제로 탄산"으로 아이디어 세 개를 내 봤어요. 마음에 드는 걸 골라 주세요.', "ideas", False),
    ("두 개 다 컨셉 보드로 만들었어요. 가격은 편의점에서 비슷한 제품이 팔리는 값에 맞췄어요. 고칠 데 있으면 말씀해 주세요.",
     "concepts", False),
    ("아이디어를 내다가 문제가 생겼어요. 다시 해 볼까요?", "failed", True),
    ("저는 음료랑 식품 신제품만 도와드릴 수 있어요. 어떤 제품을 생각하고 계세요?", "scope", True),
    ("이건 아직 준비 중이에요.", "not_ready", False),
    ("제안서 양식으로 정리했어요.", "download", False),
    ("아직 컨셉 보드가 없어요. 컨셉 보드부터 만들어 볼까요?", "download", True),
]
# 4절의 "후" 가운데 하나는 지시서 07의 쓰지 않는 말("이제")이 들어 있어 검사에 걸린다. 글틀에서는 그 말을 뺐다.
AFTER_CONFLICT = [
    ("두 컨셉으로 정했어요. 이제 편의점 매대에 올려서 손님들이 집어 가는지 볼 수 있어요.", "쓰지 않는 말: 이제",
     "두 컨셉으로 정했어요. 편의점 매대에 올려서 손님들이 집어 가는지 볼 수 있어요."),
]


def facts_for(turn: str, question: bool) -> Facts:
    return Facts(turn=turn, title=turn, question=question, max_sentences=4 if turn in ("recommend", "target") else 3,
                 allow_start=turn == "recommend", names=NAMES,
                 found=["두 배 가까이", "열에 아홉"], answer_to="물음" if turn == "failed" else None)


@pytest.mark.parametrize("text,question", BEFORE)
def test_before_sentences_fail(text, question):
    assert check(text, facts_for("any", question)), text


@pytest.mark.parametrize("text,turn,question", AFTER)
def test_after_sentences_pass(text, turn, question):
    assert check(text, facts_for(turn, question)) == [], text


@pytest.mark.parametrize("text,why,ours", AFTER_CONFLICT)
def test_after_sentences_with_banned_words(text, why, ours):
    assert check(text, facts_for("any", False)) == [why]
    assert check(ours, facts_for("any", False)) == []  # 글틀은 그 말을 뺀 것


def test_numbers_not_in_facts_fail():
    f = Facts(turn="target", title="t", found=["20대가 다른 음료보다 네 배 넘게 자주 마신다"], max_sentences=4)
    assert check("20대가 다른 음료보다 네 배 넘게 자주 마셔요.", f) == []
    assert "받지 않은 숫자: 4.5" in check("20대가 다른 음료보다 4.5배 자주 마셔요.", f)
    assert "받지 않은 숫자: 30" in check("30대도 많이 마셔요.", f)
    assert "받지 않은 숫자: 세 배" in check("20대가 세 배 넘게 마셔요.", f)
    assert "받지 않은 숫자: 열에 여덟" in check("열에 여덟은 집에서 마셔요.", f)


def test_other_rules():
    f = Facts(turn="occasion", title="t", question=True, names=["20대"])
    assert "마지막 문장을 권하는 물음으로 끝내 주세요" in check("20대로 할게요.", f)
    assert "물음이 마지막 문장이 아니에요" in check("어때요? 20대로 할게요.", Facts(turn="x", title="x"))
    assert "느낌표" in check("좋아요!", Facts(turn="x", title="x"))
    assert any(w.startswith("칭찬") for w in check("좋은 선택이에요.", Facts(turn="x", title="x")))
    assert any(w.startswith('"매대"') for w in check("세븐일레븐 음료 매대에 올려요.", Facts(turn="x", title="x")))
    assert check("편의점 음료 매대에 올려요.", Facts(turn="x", title="x")) == []
    assert "쓰지 않는 말: 시작할까요" in check("이걸로 시작할까요?", Facts(turn="x", title="x"))
    assert check("이걸로 시작할까요?", Facts(turn="x", title="x", allow_start=True, ask="어느 것으로 할지")) == []
    assert any("묻지 말아" in w for w in check("다음 걸로 가 볼까요?", Facts(turn="x", title="x")))  # 보탤 것이 없으면 묻지 않는다
    assert "쓰지 않는 말: AI" in check("AI가 골랐어요.", Facts(turn="x", title="x"))
    assert "쓰지 않는 말: 살펴봤" in check("요즘 소식을 살펴봤어요.", Facts(turn="x", title="x"))
    assert check("국민건강영양조사를 찾아보니 그렇더라고요.", Facts(turn="x", title="x")) == []  # 지시서 09: "찾아보니"로 말한다
    assert any("풀어서" in w for w in check('"음식과 어울리게 마시기"가 커져요.',
                                          Facts(turn="x", title="x", avoid=["음식과 어울리게 마시기"])))
    assert any("국민건강영양조사" in w for w in check("20대가 즐겨 마셔요.", Facts(turn="x", title="x", names=["20대"],
                                                                         source="국민건강영양조사")))


# ---------- 글틀도 같은 검사를 통과한다 ----------


def _open_turns() -> list[Turn]:
    from agent import find
    from agent.note import Note, Slot
    from agent.voice import Addition, Bit
    from tools.consumer import Group

    founds = []
    for kind, shelf_kind, product in (("탄산음료(저칼로리)", "탄산", "제로 탄산"), ("차", "차", "말차 라떼"),
                                      ("막걸리", "막걸리", "막걸리"), ("맥주", "맥주", "맥주")):
        for group in (None, Group(age="19-29", label="20대"), Group(age="30-39", label="30대 직장인")):
            note = Note(product=Slot(product, "planner"), kind=kind, shelf_kind=shelf_kind, group=group,
                        same_kind=product != "말차 라떼", shelf="주류" if kind in ("막걸리", "맥주") else "음료",
                        thoughts=["아침 밥 먹을 때 마시는 탄산"])
            for tool, arg in (("who", ""), ("when", ""), ("when", "아침"), ("when", "밤"), ("with_food", ""),
                              ("by_job", ""), ("shelf", ""), ("shelf", "당과 열량 걱정 덜기"), ("sales", "")):
                founds += find.run(tool, arg, note)
    assert len(founds) > 60
    bits = [Bit("기획할 제품", "제로 탄산으로 기획해 볼게요.", ["제로 탄산"]),
            Bit("생각", "'아침용' 쪽으로 가 볼게요.", ["아침용"])]
    adds = [None, Addition("묻기", "이 방향으로 아이디어를 내 볼까요?", ask=True),
            Addition("권하기", "고칠 데 있으면 말씀해 주세요.")]
    out = []
    for f in founds + [None]:
        for k in range(3):
            for add in adds:
                out.append(voice.open_turn(product="제로 탄산", received=bits[:k], found=f, addition=add,
                                           thoughts=["아침용"]))
    return out


def test_templates_pass_the_same_check():
    turns = _open_turns()
    assert len(turns) > 100
    for t in turns:
        assert check(t.fallback, t.facts) == [], (t.facts.turn, t.fallback)
    class R:  # consumer.Start 모양
        def __init__(self, product, kind, origin, extra):
            self.product, self.kind, self.origin, self.extra, self.id = product, kind, origin, extra, product

    rec = voice.recommend_turn([R("제로 탄산", "탄산음료(저칼로리)", "record", {"age": "19-29", "ratio": 4.45}),
                                R("탄산음료", "탄산음료", "record", {"age": "19-29", "ratio": 1.8}),
                                R("단백질 음료", "기타 음료", "sales", {"pct": 5.6})])
    assert check(rec.fallback, rec.facts) == []


def test_fixed_sentences_pass_the_check():
    plain = Facts(turn="x", title="x", ask="물을 것")
    for text in [P.SESSION_LOST, P.ASK_PRODUCT, P.OUT_OF_SCOPE, P.NOT_READY, P.MISREAD, P.PICK_IDEAS,
                 *P.FAILED.values()]:
        assert check(text, plain) == [], text


# ---------- 다시 쓰기와 글틀 ----------

def _turn() -> Turn:
    from agent.voice import Addition, Bit

    class F:  # agent.find.Found 모양
        fact = "제로 탄산은 20대가 다른 음료보다 네 배 넘게 자주 마신다"
        sentence = "국민건강영양조사를 찾아보니 제로 탄산은 20대가 다른 음료보다 네 배 넘게 자주 마시더라고요."
        said_source = "국민건강영양조사"
        names = ["20대", "제로 탄산"]
        caution = None

    return voice.open_turn(product="제로 탄산", received=[Bit("기획할 제품을 '제로 탄산'으로 받아 적었다",
                                                             "제로 탄산으로 기획해 볼게요.", ["제로 탄산"])],
                           found=F(), addition=Addition("20대 쪽으로 아이디어를 내 보자고 권한다",
                                                        "20대 쪽으로 아이디어를 내 볼까요?", ask=True), thoughts=[])


TURN = _turn()
GOOD = "제로 탄산으로 기획해 볼게요. 국민건강영양조사를 찾아보니 20대가 다른 음료보다 네 배 넘게 자주 마시더라고요. 20대부터 잡아 볼까요?"


def _speak(answers) -> tuple[voice.Spoken, FakeLLM]:
    fake = FakeLLM({"voice": answers})
    set_llm(fake)
    return asyncio.run(voice.speak(TURN)), fake


def test_good_text_is_used():
    out, fake = _speak([{"text": GOOD}])
    assert out.text == GOOD and not out.fallback and out.attempts == 1
    assert fake.calls[0]["model"] == "sonnet" and fake.calls[0]["timeout"] == 30.0


def test_bad_then_good_rewrites_once_with_reasons():
    bad = "먼저 최근 소식을 찾아봤어요. 국민건강영양조사를 보면 20대가 4.5배 자주 마셔요. 20대로 볼게요?"
    out, fake = _speak([{"text": bad}, {"text": GOOD}])
    assert out.text == GOOD and not out.fallback and out.attempts == 2
    retry = fake.calls[1]["user"]
    assert "지난번에 쓴 말: " + bad in retry
    assert "받지 않은 숫자: 4.5" in retry and "쓰지 않는 말: 먼저" in retry and "쓰지 않는 말: 로 볼게요" in retry


def test_bad_twice_falls_back_to_template():
    bad = {"text": "20대가 4.5배 자주 마셔요! 20대로 볼게요?"}
    out, fake = _speak([bad, bad])
    assert out.fallback and out.text == TURN.fallback and out.attempts == 2
    assert len(out.reasons) == 2 and any("받지 않은 숫자: 4.5" in r for r in out.reasons[0])


def test_timeout_falls_back_at_once():
    out, fake = _speak(LLMTimeout("30초가 넘었어요"))
    assert out.fallback and out.text == TURN.fallback and len(fake.calls) == 1


def test_call_failure_retries_then_falls_back():
    out, fake = _speak(LLMError("답을 읽지 못했어요"))
    assert out.fallback and len(fake.calls) == 2


def test_voice_model_env(monkeypatch):
    monkeypatch.setenv("AX_VOICE_MODEL", "haiku")
    _, fake = _speak([{"text": GOOD}])
    assert fake.calls[0]["model"] == "haiku"


def test_prompt_carries_guide_and_facts():
    system = voice.system_prompt(TURN.facts)
    assert "docs/chilseong-voice.md" in voice.GUIDE_PATH.read_text(encoding="utf-8").splitlines()[0]
    assert "## 4. 전과 후" in system and "## 3. 원칙" in system and "## 1. 누가 누구에게 말하나" in system
    assert "## 5. 열린 대화에서" in system and "## 2." not in system
    assert '{"text": "..."}' in system and "3문장 안" in system
    user = voice.user_prompt(TURN.facts)
    assert "네 배 넘게" in user and "4.4" not in user and "/Users" not in user


def test_pick_claim():
    from tools.web import Claim

    claims = [Claim("42%로 높아요", "가", "https://a", "2026-10-01", None),
              Claim("오래된 이야기", "나", "https://b", "2024-01-01", "오래된 글이에요"),
              Claim("과일 맛이 이어져요", "다", "https://c", "2026-07-01", None)]
    assert voice.pick_claim(claims).text == "과일 맛이 이어져요"
    assert voice.pick_claim(claims[:2]).text == "42%로 높아요"
    assert voice.pick_claim(claims[1:2]) is None
