"""칠성이의 고정된 글과 화면의 글. 화면에 나오는 문장은 여기에만 있다.

docs/chilseong-voice.md를 따른다. 대화의 말은 보통 모델이 지침을 보고 쓰고(agent/voice.py),
모델의 말이 검사에 두 번 걸리거나 시간이 넘으면 글틀로 말한다. 글틀의 문장은 찾아본 것(agent/find.py)과
한 일(agent/machine.py)이 저마다 하나씩 들고 오고, 같은 검사를 통과해야 한다(tests/test_voice.py).
숫자를 말로 바꾸는 것은 tools/spoken.py가 한다. 카드의 글은 정확한 숫자를 그대로 쓴다(말만 어림).
말에도 카드에도 "자료", "기록"을 쓰지 않는다(지시서 09). 출처의 이름과 사실만 적는다. "매대" 앞에는 "편의점"을 붙인다.
"""

from __future__ import annotations

import re

from tools import spoken
from tools.consumer import josa

RECORD_NAME = "국민건강영양조사"

# ---------- 고정된 말(모델을 부르지 않는다) ----------

SESSION_LOST = "대화가 끊겼어요. 새 대화로 다시 시작해 주세요."
ASK_PRODUCT = "어떤 제품을 생각하고 계세요?"
OUT_OF_SCOPE = "저는 음료랑 식품 신제품만 도와드릴 수 있어요. 어떤 제품을 생각하고 계세요?"
NOT_READY = "이건 아직 준비 중이에요."
MISREAD = "제가 잘못 알아들었어요. 다시 말씀해 주시겠어요?"
PICK_IDEAS = "어느 아이디어로 컨셉 보드를 만들까요?"
# 칠성이가 스스로 낸 아이디어의 사양(11-25): 컨셉의 가격이 아이디어에 제안한 권장 소비자가일 때
IDEA_PRICE_FACT = "가격은 아이디어에 제안한 권장 소비자가로 했다(매대에 올릴 규격의 값, 매대의 같은 용기 가격 범위 안)"
IDEA_PRICE = "가격은 아이디어에 적어 둔 권장 소비자가로 했어요."
# 과제의 컨셉을 말한 대화에서 아이디어를 낼 때: 그 컨셉을 첫 아이디어로 함께 올린다(11-25)
TASK_IDEA_FACT = "기획자가 말한 과제의 컨셉 '{name}'을(를) 과제의 사양 그대로 첫 아이디어로 함께 올렸다"
TASK_IDEA = "말씀하신 '{name}'{jo} 첫 아이디어로 함께 올렸어요."
# 규격이 둘 이상인 기획자의 아이디어는 규격마다 카드 하나로 올린다(11-25 참가자의 검수)
TASK_IDEA_SPLIT_FACT = "기획자가 말한 과제의 컨셉 '{name}'을(를) 규격마다({packs}) 아이디어 하나씩 올렸다"
TASK_IDEA_SPLIT = "말씀하신 '{name}'{jo} 규격마다 하나씩 올렸어요."
MY_IDEA_SPLIT_FACT = "기획자의 아이디어 '{name}'을(를) 규격마다({packs}) 하나씩 보드에 올렸다"
MY_IDEA_SPLIT = "'{name}'{jo} 규격마다 하나씩 보드에 올렸어요."
# 컨셉 보드를 확정할 때 보드가 둘 이상이면 어느 보드인지 고르게 한다
PICK_CONFIRM = "어느 보드로 확정할까요?"
# 내려받기(지시서 14의 3절)
DOWNLOAD_READY = "제안서 양식으로 정리했어요."
DOWNLOAD_NO_CONCEPTS = "아직 컨셉 보드가 없어요. 컨셉 보드부터 만들어 볼까요?"

# 하다가 막혔을 때(지침 4절)
FAILED = {
    "ideas": "아이디어를 내다가 문제가 생겼어요. 다시 해 볼까요?",
    "edit_idea": "아이디어를 고치다가 문제가 생겼어요. 다시 해 볼까요?",
    "my_idea": "아이디어를 받아 적다가 문제가 생겼어요. 다시 해 볼까요?",
    "concepts": "컨셉 보드를 만들다가 문제가 생겼어요. 다시 해 볼까요?",
    "edit_concept": "컨셉을 고치다가 문제가 생겼어요. 다시 해 볼까요?",
}

# 카드의 덧말
SMALL_SAMPLE = "조사된 사람이 적어서 참고만 해 주세요"
BY_CHILSEONG = "칠성이가 정했어요"
CHANNEL_NOTE = "여기서 테스트해요"

# 칠성이 소개: 첫 화면의 "칠성이는 무엇을 할 수 있나요?"와 그 뒤의 물음 칩. 모델을 부르지 않는 고정된 말이다.
# 처음 온 사람에게 주는 사용 안내다: 칠성이의 역할, 일이 진행되는 순서, 칠성이에게 시키는 법, 화면 보는 법.
# 특징이나 신뢰도 자랑을 넣지 않는다. 실제로 되는 것만 적고, 화면이 바뀌면 여기도 고친다.
ABOUT_ASK = "칠성이는 무엇을 할 수 있나요?"  # 화면의 copy.home.concept.suggestions와 같아야 한다
ABOUT_CHIPS = [("about-flow", "어떤 순서로 진행되나요?"), ("about-talk", "어떻게 시키면 되나요?"), ("about-screen", "화면은 어떻게 보나요?")]
ABOUT = {
    "about": """저는 상품기획팀 막내 사원 칠성이예요. 음료 신제품을 기획하실 때 조사하고, 안을 내고, 테스트를 돌리는 일을 제가 맡아요. 기획자님은 말로 시키고, 제가 내놓은 것 가운데 고르고 정하시면 돼요.

일은 두 부분이에요.

1부 컨셉 기획
생각하시는 제품을 한 문장으로 말씀해 주시면, 누가 언제 왜 마시는지를 제가 찾아 아이디어와 컨셉을 내요. 마음에 드는 컨셉을 확정하시면 1부가 끝나요.

2부 매대 테스트
확정한 컨셉을 편의점 음료 매대에 올려요. 타깃 손님이 구매하는지 보고, 구매하지 않은 이유로 컨셉을 고쳐 다시 물은 뒤 보고서로 정리해요.

지금 하실 일은 하나예요. 아래 입력창에 "제로 탄산 신제품을 검토하고 싶어요"처럼 적어 주세요. 떠오르는 것이 없으면 추천받기를 눌러 주세요.""",
    "about-flow": """여섯 단계로 진행돼요. 단계마다 제가 준비하고, 기획자님이 정해요.

1. 아이디어 회의
제가 타깃, 음용 상황, 니즈를 찾아 제안하고 아이디어를 내요. 기획자님은 마음에 드는 아이디어를 골라요.

2. 컨셉 보드
고른 아이디어를 제가 이름, 용기와 용량, 가격이 있는 컨셉으로 만들어요. 기획자님은 고칠 곳을 말하고 하나를 확정해요. 여기서 제안서를 내려받을 수 있어요.

3. 매대 테스트
누구에게 물을지 제가 보여 드리고, 기획자님이 시작하기를 눌러요. 몇 분이 걸리고, 기다리는 동안에도 대화할 수 있어요.

4. 테스트 결과
몇 명이 구매했는지, 왜 구매하지 않았는지를 제가 정리해요. 궁금하면 손님 한 명을 불러 직접 물어볼 수 있어요.

5. 개선안 테스트
제가 고칠 안을 둘이나 셋 내요. 기획자님이 고른 안으로 다시 물어요.

6. 결과 보고서
테스트 결과까지 담은 보고서를 내려받아요.

지금 어느 단계인지는 위쪽 표시줄에 보여요.""",
    "about-talk": """동료에게 말하듯 적어 주시면 돼요. 정해진 명령어는 없어요.

· 시작할 때: "20대가 저녁에 마실 제로 탄산"처럼 아는 만큼만 적어 주세요. 빠진 것은 제가 하나씩 여쭤봐요.
· 고를 때: 제 말 아래에 뜨는 버튼을 누르세요. 같은 말을 글로 적어도 돼요.
· 바꾸고 싶을 때: "타깃을 30대 남성으로 바꿔 줘", "가격을 1,800원으로 해 줘", "다른 아이디어 보여 줘"처럼 말씀해 주세요.
· 궁금할 때: "왜 이 타깃이야?", "근거가 뭐야?"처럼 언제든 물어보세요.
· 막막할 때: 추천받기를 누르면 제가 출발점 셋을 권해요.

컨셉 확정이나 테스트 시작처럼 큰일은 제가 먼저 확인을 받고 진행해요.""",
    "about-screen": """화면은 세 곳만 보시면 돼요.

· 왼쪽 대화: 저와 이야기하는 곳이에요. 제 말 아래에 고를 수 있는 버튼이 떠요.
· 오른쪽 작업대: 제가 찾은 근거와 만든 것(아이디어, 컨셉, 테스트 결과)이 카드로 쌓여요. 대화가 길어져도 지금까지 정한 것은 여기서 한눈에 보여요.
· 위쪽 표시줄: 지금 단계가 보여요. 눌러서 앞 단계로 돌아갈 수 있어요.

근거에는 어디서 온 것인지 표시가 붙어요. 소비자 기록, 매대, 웹에서 찾은 것, 제 제안 가운데 하나예요.

맨 왼쪽에서는 새 대화를 열거나 지난 대화를 다시 볼 수 있어요.""",
}

# 칩과 버튼(한 줄. 설명을 붙이지 않는다. 할 일인 버튼은 "~하기")
CHIP_RECOMMEND = "추천받기"
BTN_RETRY = "다시 해 보기"
BTN_IDEAS = "아이디어 내기"
BTN_IDEAS_AGAIN = "아이디어 다시 내기"
BTN_IDEAS_THOUGHT = "이 방향으로 아이디어 내기"
BTN_MORE_IDEAS = "다른 아이디어 보기"
BTN_MAKE_CONCEPTS = "컨셉으로 만들기"
BTN_PICK_IDEAS = "아이디어 선택하기"  # 아이디어가 둘 이상일 때: 누르면 카드에서 고르는 차례가 열린다(참가자의 검수 11-25)
BTN_CONFIRM = "이 컨셉으로 확정하기"
SPEC_COUNT = {2: "두", 3: "세", 4: "네", 5: "다섯"}


def btn_make_all_specs(k: int) -> str:
    """기획자의 같은 아이디어를 규격별로 나눈 카드 k개를 한 번에 컨셉 보드로 만드는 버튼."""
    return f"{SPEC_COUNT.get(k, str(k))} 규격 모두 컨셉으로 만들기"


def board_label(k: int, pack: str) -> str:
    """보드를 고를 때의 이름: '보드 2 PET 500ml'."""
    return f"보드 {k} {pack}".strip()
BTN_SHELF = "매대에 올려 보기"
BTN_DOWNLOAD = "제안서로 내려받기"


def btn_target(group: str) -> str:
    return f"타깃을 {group}{josa(group, '으로/로')} 하기"


# 하는 일 한 줄(짧은 이름)
ACT_READ = "말씀 읽는 중"
ACT_LOOK = "찾아보는 중"
ACT_WEB = "요즘 소식 찾는 중"
ACT_IDEAS = "아이디어 내는 중"
ACT_EDIT_IDEA = "아이디어 고치는 중"
ACT_CONCEPTS = "컨셉 보드 만드는 중"
ACT_ANALYSIS = ("검색 추이 보는 중", "소비자가 내겠다는 값 세는 중", "비슷한 과거 사례 찾는 중", "분석 정리하는 중")  # 컨셉을 확정한 차례
ACT_EDIT_CONCEPT = "컨셉 고치는 중"

# 끝난 뒤 말 위에 남는 이름(과거형). "~는 중"이 끝난 차례에 남지 않게 한다.
ACT_DONE = {
    ACT_READ: "말씀을 읽었어요",
    ACT_LOOK: "찾아봤어요",
    ACT_WEB: "요즘 소식을 찾았어요",
    ACT_IDEAS: "아이디어를 냈어요",
    ACT_EDIT_IDEA: "아이디어를 고쳤어요",
    ACT_CONCEPTS: "컨셉 보드를 만들었어요",
    ACT_EDIT_CONCEPT: "컨셉을 고쳤어요",
}


def act_done(label: str) -> str:
    return ACT_DONE.get(label, label)

# 카드의 제목과 브리프 칸의 이름
CARD_BRIEF = "기획 브리프"
CARD_EVIDENCE = "찾아본 것"  # 화면에 "근거"를 내지 않는다(지시서 11)
CARD_IDEAS = "아이디어"
CARD_CONCEPTS = "컨셉 보드"
FIELD_LABELS = {"product": "제품", "channel": "채널", "target": "타깃", "occasion": "음용 상황", "need": "핵심 니즈"}
SUMMARY_TITLE = "확정한 컨셉"


def channel(shelf: str) -> str:
    return f"편의점 {shelf} 매대"


# 컨셉 카드의 제품 특징(지시서 12, 약속 v1.4). 이 순서, 이 이름으로 그린다
SPEC_LABELS = {
    "type": "제품 유형",
    "flavor": "맛",
    "pack": "용기와 용량",
    "sugar_caffeine": "당, 카페인",
    "carbonation": "탄산",
    "storage": "보관",
    "target": "타깃",
    "occasion": "음용 상황",
    "channel": "판매 채널",
    "price": "목표 판매가",
    "rivals": "경쟁 제품",
    "own": "자사 유사 제품",
    "pod": "차별점",
}
CARBONATION = ["약함", "보통", "강함"]


def spec_channel(shelf: str) -> str:
    return "편의점 음료 매대(냉장)" if shelf == "음료" else f"편의점 {shelf} 매대"


def pack(container: str, volume: int) -> str:
    return f"{volume}ml {container}"


def rival_line(name: str, price: int, promo: str | None) -> str:
    return f"{name} {price:,}원" + (f" {promo}" if promo else "")


# ---------- 2부 매대 테스트(지시서 15) ----------

SHELF_NO_CONCEPTS = "먼저 컨셉 보드부터 만들어 볼까요?"
SHELF_PICK = "어느 컨셉을 편의점 매대에 올려 볼까요?"  # 임시
SHELF_STARTED = "편의점 매대에 올렸어요. 100명이 다녀가면 먼저 온 결과를 알려 드릴게요. 그동안 다른 이야기를 하셔도 돼요."
SHELF_STARTED_SMALL = "편의점 매대에 올렸어요. 손님이 다 다녀가면 결과를 알려 드릴게요."  # 임시: 인원이 100명보다 적을 때
SHELF_CANCELLED = "알겠어요. 테스트는 하지 않을게요."  # 임시
SHELF_NO_RUN = "아직 편의점 매대에 올린 컨셉이 없어요. 올려 볼까요?"  # 임시
SHELF_ONLY_DRINK = "지금은 편의점 음료 매대에서만 테스트할 수 있어요."  # 임시
SHELF_GONE = "그 테스트를 찾지 못했어요. 다시 매대에 올려 볼까요?"  # 임시
SHELF_EARLY_AT = 100  # 이만큼 다녀가면 먼저 온 결과를 볼 수 있다
# 버튼과 카드(화면의 카드 버튼은 이 말을 대화로 보낸다. web/src/copy.ts와 같아야 한다)
BTN_SHELF_START = "테스트 시작하기"
BTN_SHELF_CANCEL = "그만두기"
BTN_EARLY_RESULT = "먼저 온 결과 보기"
BTN_RESULT = "결과 보기"
BTN_STOPPED_RESULT = "지금까지의 결과 보기"  # 멈춘 테스트의 카드(11-25)
# 멈춘 테스트를 지금까지의 답으로 해석할 때(11-25). 숫자는 코드가 넣는다
STOPPED_EMPTY = "테스트를 멈췄어요. 아직 답한 손님이 없어서 볼 결과가 없어요."  # 임시
FEW_ANSWERS = "아직 결론을 내기에는 답이 적어요."  # 임시
STOPPED_MIN_N = 30  # 멈춘 테스트에서 이보다 적게 답했으면 결론을 내지 않는다(탐색의 MIN_AXIS_N과 같다)
CARD_SHELF_RUN = "매대 테스트"
CARD_RESULT = "테스트 결과"
ACT_SHELF = "매대에 올리는 중"
ACT_RESULT = "결과 정리하는 중"  # 지시서 17의 D: 세는 일은 금방 끝난다
SHELF_CONFIRM_TITLE = "이대로 매대에 올릴까요?"  # 확인 카드의 제목
SHELF_ROWS = {"concept": "컨셉", "who": "손님"}  # 확인 카드의 줄 이름


# ---------- 2부: 한 손님에게 묻기, 개선안, 결과 보고서(지시서 17) ----------

# 한 손님에게 묻기
INTERVIEW_TO = "visitor"  # 결과 카드의 "이 손님 인터뷰하기"가 보내는 metadata.reply.to
INTERVIEW_NOT_FOUND = "그 손님을 찾지 못했어요."
BTN_OTHER_INTERVIEW = "다른 인터뷰 하기"
INTERVIEW_BYE = "인터뷰를 마쳤어요."
INTERVIEW_ASKS = [("ask-price", "얼마면 구매하시겠어요?"), ("ask-change", "어떤 점이 바뀌면 구매하시겠어요?"),
                  ("ask-usual", "평소에는 어떤 음료를 구매하시나요?")]
INTERVIEW_NEXT = ("interview-next", "다른 손님 인터뷰하기")  # 지시서 18의 C: 지금 손님을 보내고 다음 손님을 부른다
INTERVIEW_END = ("interview-end", "인터뷰 마치기")
INTERVIEW_END_CUES = ("그만 묻", "그만 물어", "그만할게", "그만 할게", "손님 보내", "보내 드려", "보내드려",
                      "인터뷰 마치", "인터뷰 끝")
ACT_INTERVIEW = "손님이 답하는 중"  # 임시


def interview_called(called: str) -> str:
    """"24세 대학생 손님을 모셨어요. 궁금한 것을 물어보세요." """
    return f"{called} 손님을 모셨어요. 궁금한 것을 물어보세요."


# 집단 인터뷰
GROUP_TO = "w7-group"
GROUP_TITLE = "가상 소비자 인터뷰"
GROUP_METHODS = {"fgi": "집단 심층 인터뷰(FGI)", "fgd": "집단 토론(FGD)"}
GROUP_NO_RUN = "이 대화의 현재 매대 테스트 결과를 먼저 열어 주세요."
GROUP_NO_CHOICE = "이 매대 테스트에서 물을 질문과 가상 소비자를 다시 골라 주세요."
GROUP_NO_SESSION = "이 매대 테스트에서 마친 인터뷰 기록을 다시 골라 주세요."
GROUP_SETUP = "매대에서 확인한 선택을 바탕으로 질문을 골랐어요. 무엇을 누구에게 물어볼까요?"
GROUP_DONE = "인터뷰를 마쳤어요. 작업대에서 개선안에 반영할 발언을 골라 주세요."
GROUP_ERROR = "인터뷰를 마치지 못했어요. 질문과 참석자를 다시 골라 시작할 수 있어요."
GROUP_QUOTE_CHOICE = "이 발언으로 어떤 조건을 바꿔 볼까요? 한 가지를 골라 주세요."
GROUP_QUOTE_SAVED = "고른 발언을 원문 그대로 개선안에 붙였어요. 같은 가상 소비자에게 다시 물어볼 수 있어요."
GROUP_QUOTE_ALREADY = "이 발언은 이미 개선안에 붙어 있어요."
GROUP_QUOTE_CLOSED = "이 테스트에서 개선안을 이미 채택했어요. 현재 컨셉 보드를 다시 테스트해 주세요."
GROUP_CHANGE_CHOICES = {
    "price": "가격 낮추기", "larger": "용량 늘리기", "smaller": "용량 줄이기", "promo": "행사 변경하기",
    "still": "탄산 빼기", "light_fizz": "탄산 약하게 하기", "fizz": "탄산 넣기",
    "sweet": "단맛 줄이기", "mild": "향 줄이기", "appeal": "매대에 맛과 용량 표시하기",
}


def group_quote_reason(who: str, change: str) -> str:
    return f"{who} 가상 소비자의 발언을 근거로 ‘{change}’{josa(change, '을/를')} 비교해요."


def group_reopen(mode: str) -> str:
    return f"{GROUP_METHODS[mode]} 다시 열기"


def group_container_choice(container: str) -> str:
    return f"{container} 용기로 바꾸기"


# 개선안
BTN_ASK_SHOPPER = "손님 인터뷰하기"  # 결과 뒤: 아직 안 부른 손님 한 명을 부른다(지시서 18의 C)
BTN_ASK_GROUP = "더 물어볼 곳"


# 테스트 결과를 알리는 말: 현황(도는 중이면 몇 명이 답했고 언제 끝나는지) → 알게 된 것 → 다음. 숫자는 코드가 넣는다.
RESULT_DONE = "테스트가 끝났어요."
RESULT_NEXT_DONE = "고르지 않은 까닭을 더 물어보거나 개선안을 볼 수 있어요."
RESULT_NEXT_NONE = "고르지 않은 까닭을 물어보거나 컨셉을 고쳐 볼 수 있어요."


def result_progress(asked: int, total: int) -> str:
    """"300명 중 102명이 답했어요." """
    return f"{total:,}명 중 {asked:,}명이 답했어요."


def eta_minutes(sec: float) -> int:
    """남은 시간(초)을 분으로 올려 센다(1분보다 짧으면 1)."""
    return max(1, -(-int(sec) // 60))


def result_eta(sec: float) -> str:
    """"약 4분 뒤에 끝나요." 1분이 안 남았으면 "1분 안에 끝나요." """
    return "1분 안에 끝나요." if sec < 60 else f"약 {eta_minutes(sec)}분 뒤에 끝나요."


def _ranked(products: int, rank: int | None) -> str:
    return f"{products}개 제품 가운데 {rank}위예요" if rank else f"{products}개 제품 가운데 순위에 들지 못했어요"


def result_so_far(n: int, k: int, name: str, rank: int | None, products: int) -> str:
    """도는 중: "지금까지는 102명 중 69명이 밀키스 화채를 골랐고 68개 제품 가운데 1위예요." """
    if not k:
        return f"지금까지는 {n:,}명 중 {name}{josa(name, '을/를')} 고른 손님이 없어요."
    return f"지금까지는 {n:,}명 중 {k:,}명이 {name}{josa(name, '을/를')} 골랐고 {_ranked(products, rank)}."


def result_done_line(group: str, n: int, k: int, name: str, rank: int | None, products: int) -> str:
    """끝난 뒤: "20대 300명 중 73명이 밀키스 화채를 골랐고 68개 제품 가운데 1위예요." """
    head = f"{group} {n:,}명 중" if group not in ("", "전체") else f"손님 {n:,}명 중"
    if not k:
        return f"{head} {name}{josa(name, '을/를')} 고른 손님은 없었어요."
    return f"{head} {k:,}명이 {name}{josa(name, '을/를')} 골랐고 {_ranked(products, rank)}."


def result_insight(occasion: str | None, barrier: str | None,
                   own: tuple[int, int, str] | None = None) -> str | None:
    """알게 된 것 둘: 가장 많이 고른 상황, 그리고 고르지 않은 손님이 가장 많이 든 까닭.
    own=(고른 수, 자사 제품을 고르던 수, 가장 많이 겹친 자사 제품)이 오면 까닭 대신 그것(자기잠식)을 말한다."""
    occ = f"'{occasion}'일 때 가장 많이 골랐" if occasion else ""
    if own:
        k, o, top = own
        bar = f"고른 {k:,}명 가운데 {o:,}명은 자사 제품({top})을 고르던 손님이에요."
    else:
        bar = f"고르지 않은 손님은 '{barrier}'{josa(barrier, '을/를')} 가장 많이 들었어요." if barrier else ""
    if occ and bar:
        return f"{occ}고, {bar}"
    if occ:
        return occ + "어요."
    return bar or None


def result_next_running(total: int) -> str:
    return f"끝나면 결과가 {total:,}명 기준으로 바뀌어요."


BTN_IMPROVE = "개선안 보기"
BTN_REPORT = "결과 보고서 내려받기"
BTN_IMPROVE_ALL = "남은 안 모두 테스트하기"  # 개선안을 낸 뒤의 버튼, 개선안 카드의 버튼(web/src/copy.ts와 같아야 한다)
BTN_IMPROVE_COMPARE = "변경안 결과 보기"  # 개선안 카드의 버튼과, 결과가 나오면 카드가 스스로 보내는 말(web/src/copy.ts와 같아야 한다)
IMPROVE_RUN_TO = "improve"  # 개선안 카드의 "테스트하기"가 보내는 metadata.reply.to
ACT_IMPROVE = "개선안 내는 중"  # 임시
ACT_IMPROVE_RUN = "다시 물을 안 정리하는 중"  # 임시
CARD_IMPROVE = "개선안 테스트"
ACT_DONE.update({ACT_SHELF: "매대에 올렸어요", ACT_RESULT: "결과를 정리했어요", ACT_INTERVIEW: "손님이 답했어요",
                 ACT_IMPROVE: "개선안을 냈어요", ACT_IMPROVE_RUN: "다시 물을 안을 정리했어요"})
IMPROVE_NO_RESULT = "개선안을 내려면 매대 테스트의 결과가 먼저 있어야 해요."  # 임시
IMPROVE_NOT_UNDERSTOOD = "어떤 값을 바꿀지 잘 모르겠어요. 가격, 용기와 용량, 이름, 행사 가운데 하나를 말씀해 주세요."  # 임시
IMPROVE_NO_ITEM = "그 안을 찾지 못했어요."  # 임시
IMPROVE_NOTHING_RAN = "아직 테스트한 변경안이 없어요. 변경안으로 테스트해 볼까요?"  # 임시
IMPROVE_STILL_RUNNING = "아직 손님들이 다녀가는 중이에요. 조금 뒤에 다시 볼게요."  # 임시
IMPROVE_UNCLEAR = "기존안과의 차이가 오차 범위 안이라, 어느 쪽이 낫다고 보기 어려워요."  # 변경안 결과에서 폭이 겹칠 때(꼭 이렇게)
IMPROVE_REASON_PLANNER = "말씀하신 안이에요."  # 임시: 기획자가 직접 말한 안의 까닭 칸


def improve_started(labels: list[str]) -> str:
    """변경안을 테스트하기 시작했을 때(고정된 말). labels는 안의 이름("가격 변경안")."""
    names = ", ".join(labels)
    return f"{names}{josa(names, '으로/로')} 같은 손님들에게 다시 물어볼게요. 결과가 나오면 알려 드릴게요."


# 결과 보고서
REPORT_READY = ("테스트 결과를 넣어 제안서를 다시 정리했어요.\n\n"
                "제안서를 내려받아 실제 소비자 조사를 하셨다면, 다시 오셔서 조사 결과를 올려 주세요. "
                "가상 소비자를 실제 답에 맞추고 개선안을 찾아 드릴게요.")


def shelf_group_subject(group: str) -> str:
    """"20대가", "20대 여자가", 전체면 "손님들이"."""
    if group == "전체":
        return "손님들이"
    return f"{group}{josa(group, '이/가')}"


def shelf_confirm_say(who: str, total: int, group: str) -> str:
    """확정할 타깃과 실제로 물을 수 있는 인원을 알린다.
    음용 상황을 반씩 나누는 방법은 그대로 두고 말에서만 뺀다(지시서 18의 A)."""
    if group == "전체":
        return f"전체 손님 {total:,}명에게 물어볼게요."
    return f"타깃인 {who} {total:,}명에게 물어볼게요."


def shelf_started(total: int) -> str:
    return SHELF_STARTED if total > SHELF_EARLY_AT else SHELF_STARTED_SMALL


def stopped_line(asked: int, total: int) -> str:
    """멈춘 테스트를 해석하는 말의 첫머리(11-25)."""
    return f"{total:,}명 중 {asked:,}명에서 멈췄어요. 지금까지의 결과예요."  # 임시


def shelf_waiting(asked: int, total: int = 300) -> str:
    if total <= SHELF_EARLY_AT:
        return f"지금 {asked:,}명이 다녀갔어요. {total:,}명이 다 다녀가면 결과를 볼 수 있어요."  # 임시
    return f"지금 {asked:,}명이 다녀갔어요. {SHELF_EARLY_AT}명이 다녀가면 먼저 온 결과를 볼 수 있어요."


# ---------- 추천의 글틀(지침 4절의 "후") ----------


def recommend(pairs: list[tuple[str, str, str]], grown: tuple[str, bool] | None, year: int) -> str:
    """pairs: [(제품, 연령대, 말로 바꾼 배수)], grown: (제품, 늘었는가)."""
    n = len(pairs) + (1 if grown else 0)
    head = f"요즘 눈에 띄는 게 {spoken.count(n)} 가지 있어요."
    bits = [f"{p}{josa(p, '은/는')} {a}{josa(a, '이/가')}" for p, a, _ in pairs]
    body = ""
    if bits:
        body = ", ".join(bits) + " 유독 많이 마시고"
    if grown:
        p, up = grown
        tail = (f"{p}{josa(p, '은/는')} 편의점에서 {year}년에 그 전해보다 더 팔렸어요" if up
                else f"{p}{josa(p, '은/는')} 편의점 매출을 함께 봐 두면 좋겠어요")
        body = f"{body}, {tail}." if body else f"{tail}."
    elif body:
        body = body.removesuffix("마시고") + "마셔요."
    return f"{head} {body} 어떤 게 끌리세요?"


# ---------- 카드의 글(정확한 숫자를 그대로) ----------


def ev_who(kind_name: str, rows: list[tuple[str, float]], than: str) -> str:
    parts = ", ".join(f"{name} {ratio:.1f}배" for name, ratio in rows[:2])
    return f"{kind_name}{josa(kind_name, '은/는')} {than}보다 {parts} 자주 마셔요"


def ev_when(target: str, kind_name: str, items: list[tuple[str, float]]) -> str:
    parts = ", ".join(f"{w} {p:.0f}%" for w, p in items)
    who = "" if target == "전체" else f"{target}의 "
    return f"{who}{kind_name} 음용 상황: {parts}"


def ev_shelf(count: int, low: int, high: int) -> str:
    price = f"{low:,}원" if low == high else f"{low:,}~{high:,}원"
    return f"편의점 동일 용량대 판매가 {price} ({count}개 제품)"


def source_record(n: int) -> str:
    return f"2024 국민건강영양조사 식품섭취조사, 음용 사례 {n:,}건"


def source_record_groups(rows: list[tuple[str, int]]) -> str:
    parts = ", ".join(f"{name} {n:,}건" for name, n in rows)
    return f"2024 국민건강영양조사 식품섭취조사, 음용 사례 {parts}"


def occasion_adv(occasion: str) -> str:
    """음용 상황의 이름 → "마시는" 앞에 놓을 말. "밖에서 식사할 때 입가심" → "밖에서 식사할 때 입가심으로", "혼자 마실 때" → "혼자",
    "일하다가 혼자 한 잔" → "일하다가 혼자", "집에서 가족과 간식 자리" → "집에서 가족과 간식 자리에서"."""
    o = occasion.strip().strip("'\"")
    for tail in (" 마실 때", " 한 잔", " 한잔"):
        o = o.removesuffix(tail)
    if o.endswith("자리"):
        o += "에서"
    if o.endswith("입가심"):
        o += "으로"
    return o


def _short_thoughts(thoughts: list[str]) -> list[str]:
    """명사구로 끼울 수 있는 짧은 생각만("여름 한정"). 문장처럼 긴 것은 빼고 말로 풀게 둔다."""
    return [t.strip() for t in thoughts if t.strip() and len(t.strip()) <= 12
            and not re.search(r"[.?!]|요$|다$|타깃|상황|니즈", t.strip())]


def drink_phrase(target: str | None, occasion: str | None, thoughts: list[str] | None = None,
                 product: str | None = None) -> str:
    """칸 이름 없이 사람의 말로: "20대가 밖에서 식사할 때 입가심으로 마시는 여름 한정 음료"."""
    who = f"{target}{josa(target, '이/가')} " if target and target != "전체" else ""
    when = f"{occasion_adv(occasion)} " if occasion else ""
    verb = "마시는 " if (who or when) else ""
    extra = " ".join(_short_thoughts(thoughts or []))
    head = (product or "").strip() or "음료"
    return f"{who}{when}{verb}{extra + ' ' if extra else ''}{head}".strip()


def when_phrase(target: str | None, occasion: str | None) -> str:
    """"20대가 밖에서 식사할 때 입가심으로 마실 때", 상황이 없으면 "20대가 마실 때"."""
    who = f"{target}{josa(target, '이/가')} " if target and target != "전체" else ""
    when = f"{occasion_adv(occasion)} " if occasion else ""
    return f"{who}{when}마실 때"


def ideas_basis(target: str | None, occasion: str | None, thoughts: list[str], n_web: int,
                product: str | None = None) -> str:
    """아이디어 카드 위의 한 줄: "20대가 밖에서 식사할 때 입가심으로 마시는 여름 한정 음료로 냈어요. 최근 기사 3건도 참고했어요." """
    if target or occasion or _short_thoughts(thoughts):
        phrase = drink_phrase(target, occasion, thoughts, product)
        text = f"{phrase}{josa(phrase, '으로/로')} 냈어요."
    else:
        text = "말씀하신 제품에서 바로 냈어요."
    if n_web:
        text += f" 최근 기사 {n_web}건도 참고했어요."
    return text


def summary_note(target: str | None, occasion: str | None) -> str:
    return " · ".join(x for x in (target, occasion) if x)


# ---------- 신제품 제안서(지시서 14의 2절). 문서이므로 보고서체("~함", "~임", 명사)로 쓴다 ----------

PROPOSAL_DEPT = "상품기획팀"
PROPOSAL_TITLE_SUFFIX = " (가칭)"
PROPOSAL_NOTICE = "제품 사양과 문구는 기획 단계의 안이며 확정된 값이 아님"
PROPOSAL_NO_PROMO = "-"
# 제품 개요의 표: 이름표와 컨셉 카드의 제품 특징 열쇠(컨셉은 한 줄 설명 benefit)
OVERVIEW_ROWS = [
    ("컨셉", "benefit"), ("제품 유형", "type"), ("맛", "flavor"), ("용기와 용량", "pack"),
    ("당·카페인", "sugar_caffeine"), ("탄산", "carbonation"), ("목표 판매가", "price"), ("타깃", "target"),
    ("음용 상황", "occasion"), ("판매 채널", "channel"),
]


def proposal_plan(shelf: str, has_kind: bool) -> list[str]:
    if not has_kind:
        return ["가상 매대 테스트를 위해 비교 제품 선정 필요"]
    return [f"편의점 {shelf} 매대 가상 테스트 예정(가상 소비자 300명, 경쟁 제품과 함께 진열해 선택 여부 확인)",
            "테스트 결과에 따라 판매가, 용량, 행사 조건 조정"]


def proposal_range(low: int, high: int) -> str:
    price = f"{low:,}원" if low == high else f"{low:,}~{high:,}원"
    return f"동일 용량대 판매가 {price}"


def proposal_gist(target: str | None, ptype: str, pack: str, price: str) -> str:
    """요지의 글틀(모델이 끝내 틀리거나 실패했을 때)."""
    inner = ", ".join(x for x in (pack, price) if x)
    body = f"{ptype}({inner})" if inner else ptype
    tail = josa(inner or ptype, "을/를") if inner else josa(ptype, "을/를")
    if target:
        return f"{target}{josa(target, '을/를')} 겨냥해 {body}{tail} 제안함"
    return f"{body} 신제품을 제안함"


def proposal_date(d: str | None) -> str | None:
    """각주의 날짜: "2026-10-19" → "2026. 10."."""
    if not d or len(d) < 7 or not d[:4].isdigit() or not d[5:7].isdigit():
        return None
    return f"{d[:4]}. {d[5:7]}."


# ---------- 테스트 결과의 요약 구역(지시서 32의 A). 해요체. 사람 수의 주어는 "가상 소비자" ----------
# 고르기와 문턱값은 agent/result_brief.py에 있고, 여기는 글틀만 둔다. 숫자는 받은 것만 쓴다.

# 걸린 점의 보고서체(가상 소비자가 고른 말 → 종이의 말)
REPORT_BARRIERS = {
    "지금 상황에 안 맞음": "상황에 맞지 않음",
    "맛이 끌리지 않음": "맛이 끌리지 않음",
    "가격이 비쌈": "가격이 비쌈",
    "처음 보는 제품이라 망설여짐": "처음 보는 제품이라 망설임",
    "용량이나 용기가 안 맞음": "용량이나 용기가 맞지 않음",
    "늘 마시는 것이 있음": "늘 마시는 제품이 있음",
    "어떤 제품인지 모르겠음": "어떤 제품인지 알기 어려움",
    "기타": "기타",
}


def barrier_name(label: str) -> str:
    return REPORT_BARRIERS.get(label, label)


def pct(k: int, n: int) -> str:
    """선택률: 소수 한 자리."""
    return f"{100 * k / n:.1f}%" if n else "0.0%"


def age_band(who: str) -> str:
    """"24세 여자, 대학생" → "20대". 나이가 없으면 빈 글."""
    m = re.match(r"\s*(\d+)세", who or "")
    return f"{int(m.group(1)) // 10 * 10}대" if m else ""


BRIEF_FROM_LABELS = {"rival": "경쟁사 제품", "own": "자사 제품", "none": "선택하지 않음"}


def _consumers(group: str) -> str:
    """"40대 남자" → "40대 남자 가상 소비자". 전체면 "가상 소비자"."""
    return "가상 소비자" if group in ("", "전체") else f"{group} 가상 소비자"


def brief_headline(group: str, n: int, k: int, name: str, rank: int | None, products: int,
                   running: bool = False) -> str:
    """결과 화면의 한 문장: "19~29세 300명 중 73명이 골랐고, 매대 68개 가운데 1위예요".
    도는 중이면 "지금까지는 …"으로 시작한다. 제품 이름은 화면의 머리에 있으므로 고른 사람이 있으면 넣지 않는다."""
    who = "가상 소비자" if group in ("", "전체") else group
    lead = "지금까지는 " if running else ""
    if not k:
        tail = "고른 가상 소비자가 없어요" if running else "고른 가상 소비자는 없었어요"
        return f"{lead}{who} {n:,}명 중 {name}{josa(name, '을/를')} {tail}"
    where = f"매대 {products}개 가운데 {rank}위예요" if rank else f"매대 {products}개 가운데 순위에 들지 못했어요"
    return f"{lead}{who} {n:,}명 중 {k:,}명이 골랐고, {where}"


def brief_range(low: int, high: int) -> str:
    return f"범위 {low:,}~{high:,}명"


def brief_how(rank: int | None, products: int, top: tuple[str, int] | None) -> str:
    head = f"매대 {products}개 제품 가운데 {rank}위예요." if rank else f"매대 {products}개 제품 가운데 순위에 들지 못했어요."
    if top:
        head += f" 기존 제품 가운데 가장 많이 고른 {top[0]}{josa(top[0], '은/는')} {top[1]:,}명이에요."
    return head


def brief_from(k: int, rival: int, own: int, none: int, own_top: tuple[str, int] | None, pending: int) -> str:
    text = (f"고른 {k:,}명 중 {rival:,}명은 원래 경쟁사 제품을, {own:,}명은 우리 제품을 고르던 가상 소비자예요. "
            f"{none:,}명은 원래 아무것도 고르지 않았어요.")
    if own_top:
        text += f" 자사 제품 가운데 가장 많이 겹친 것은 {own_top[0]}({own_top[1]:,}명)이에요."
    if pending:
        text += f" {pending:,}명은 아직 확인하고 있어요."
    return text


def brief_why(passed: int, bars: list[tuple[str, int]]) -> str:
    first = f"고르지 않은 {passed:,}명이 가장 많이 든 까닭은 '{bars[0][0]}'({bars[0][1]:,}명)"
    if len(bars) > 1:
        return first + f", 다음은 '{bars[1][0]}'({bars[1][1]:,}명)이에요."
    return first + "이에요."


def brief_value(n: int) -> str:
    return f"{n:,}명"


# 다음 행동의 까닭과 버튼
def act_price(n: int) -> str:
    return f"가격이 비싸다고 한 가상 소비자가 {n:,}명이에요."


ACT_PRICE_DONE = "가격을 바꾼 안은 이미 테스트했어요. 기존안과 견줘 볼 수 있어요."


def act_barrier(label: str, n: int) -> str:
    return f"고르지 않은 이유는 ‘{label}’이 {n:,}명으로 가장 많았어요."


def act_own(k: int, own: int) -> str:
    return f"고른 {k:,}명 중 {own:,}명은 원래 우리 회사의 다른 음료를 사던 사람이에요. 새 고객이 아니라 우리 제품에서 옮겨 온 거예요."


ACT_WEAK = "이 타깃에서는 거의 고르지 않았어요. 컨셉을 다시 볼 수 있어요."
BTN_INTERVIEW_ONE = "인터뷰하기"
BTN_CONCEPT_BOARD = "컨셉 보드로 돌아가기"


def interview_say(who: str) -> str:
    """결과 카드의 "이 손님 인터뷰하기"가 보내는 말과 같다(web/src/copy.ts의 askSay)."""
    return f"{who} 가상 소비자를 인터뷰할게요"


# ---------- 결과 보고서(지시서 32의 B). 보고서체(명사형 종결) ----------
# "전환", "유입", "신규 수요", "점유", "구매"를 쓰지 않는다. 숫자는 받은 것만 쓴다.

REPORT_TITLE = "신제품 컨셉 가상 매대 테스트 결과 보고"
REPORT_DISCLAIMER = "본 결과는 가상 매대 테스트의 결과이며 판매 실적이나 예측이 아님. 실제 소비자 조사에 올릴 컨셉을 고르는 데 사용."
REPORT_VERDICTS = {"research": "실제 소비자 조사 진행을 권고", "retest": "수정 후 재테스트를 권고", "hold": "보류를 권고"}


def report_spec(pack: str, price: str) -> str:
    """"250mL 슬림캔, 권장 소비자가 1,200원"."""
    parts = [x for x in (pack, f"권장 소비자가 {price}" if price else "") if x]
    return ", ".join(parts)


def _bare(label: str) -> str:
    """조사를 붙일 말: 끝의 괄호를 뗀다("가격 변경안(1,000원)" → "가격 변경안")."""
    return re.sub(r"\([^()]*\)$", "", label).strip() or label


def report_verdict(verdict: str, adopt: str | None) -> str:
    text = REPORT_VERDICTS[verdict]
    return f"{adopt}{josa(_bare(adopt), '으로/로')} {text}" if adopt else text


def plan_label(name: str, value: str) -> str:
    return f"{name}({value})" if value else name


def reason_select(group: str, n: int, k: int, rank: int | None, products: int, ahead: int) -> str:
    if not k:
        return f"{_consumers(group)} {n:,}명 중 선택한 소비자 없음"
    tail = (f"기존 제품 {products - 1}개 중 본 제품보다 많이 선택된 제품 없음" if not ahead
            else f"기존 제품 {products - 1}개 중 본 제품보다 많이 선택된 제품 {ahead}개")
    return f"{_consumers(group)} {n:,}명 중 {k:,}명이 선택, 매대 내 선택 순위 {rank}위({tail})"


def reason_better(label: str, diff: str) -> str:
    return f"{label}{josa(_bare(label), '이/가')} 기존안 대비 선택 {diff} 증가(범위가 겹치지 않음)"

def reason_better_pair(label: str, pair: dict) -> str:
    return f"{label}의 선택률이 공통 응답자 {pair['n']:,}명에서 {pair['delta_pp']:.1f}%p 높음(차이의 95% 구간 {pair['low_pp']:+.1f}~{pair['high_pp']:+.1f}%p)"

def reason_lower(worse: int, total: int) -> str:
    return f"개선안 {total}개 중 {worse}개에서 기존안보다 선택률이 낮음" + (f", 나머지 {total - worse}개는 뚜렷한 차이 없음" if worse < total else "")


def reason_no_gain(n: int) -> str:
    return f"개선안 {n}개는 기존안과 뚜렷한 차이 없음"


def reason_own(k: int, own: int) -> str:
    return f"선택한 {k:,}명 중 {own:,}명이 자사 제품을 선택하던 소비자로, 자사 제품과의 겹침 확인 필요"


def reason_barrier(label: str, n: int) -> str:
    return f"비선택 사유 1위는 '{label}'({n:,}명)"


# 결정 요청
DECIDE_RESEARCH = "정량 조사 진행 여부"
DECIDE_RETEST = "수정 후 재테스트 진행 여부"
DECIDE_HOLD = "본 컨셉의 보류 여부"
DECIDE_RETHINK = "타깃과 음용 상황을 바꾼 재검토 여부"


def decide_plan(spec: str) -> str:
    return f"조사에 올릴 안({spec})"


def decide_fix(barrier: str | None) -> str:
    return f"수정할 항목(비선택 사유 1위 '{barrier}' 대응)" if barrier else "수정할 항목"


def decide_target(board: str | None, tested: str) -> str:
    if board and board != tested:
        return f"조사 타깃(컨셉 보드의 타깃 {board}, 테스트에서 고른 타깃 {tested} 중 선택)"
    return f"조사 타깃({tested})"


# 핵심 수치(표 하나, 네 칸)
KEY_LABELS = {"picked": "선택한 소비자", "rank": "매대 내 선택 순위", "from": "평소 선택하던 제품",
              "barrier": "가장 많은 비선택 사유"}
KEY_NONE = "해당 없음"


def key_picked(n: int, k: int) -> str:
    return f"{n:,}명 중 {k:,}명"


def key_rank(rank: int | None, products: int) -> str:
    return f"{products}개 제품 중 {rank}위" if rank else f"{products}개 제품 중 순위 없음"


def key_from(rival: int, own: int, none: int) -> str:
    return f"경쟁사 {rival:,}명, 자사 {own:,}명, 선택하지 않음 {none:,}명"


def key_barrier(label: str, n: int) -> str:
    return f"{label}({n:,}명)"


# 한계
LIMIT_VIRTUAL = "가상 소비자의 선택이며 판매 실적이나 판매 예측이 아님"
LIMIT_SCOPE = "맛, 재선택 의향, 광고, 진열 위치는 반영하지 않음"


def limit_no_gain(n: int) -> str:
    return f"개선안 {n}개는 기존안과 뚜렷한 차이를 보이지 않음"


# 근거
FROM_LABELS = {"rival": "경쟁사 제품", "own": "자사 제품", "none": "선택하지 않음"}
VOICE_PICKED = "선택한 소비자"


def from_pending(n: int) -> str:
    return f"선택한 소비자 중 {n:,}명은 평소 선택 집계 중"


def voice_passed(label: str, n: int) -> str:
    return f"비선택 사유 '{label}'({n:,}명)"


def compare_value(picked: int, rank: int | None) -> str:
    return f"{picked:,}명 · {rank}위" if rank else f"{picked:,}명"


def compare_line(name: str, value: str, picked: int, verdict: str, diff: str) -> str:
    head = plan_label(name, value)
    if verdict == "better":
        tail = f"기존안 대비 {diff} 증가"
    elif verdict == "worse":
        tail = f"기존안 대비 {diff} 감소"
    else:
        tail = "기존안 대비 뚜렷한 차이 없음"
    return f"{head}: {picked:,}명 선택, {tail}"


def who_board(target: str) -> str:
    return f"컨셉 보드의 타깃: {target}"


def who_tested(group: str, n: int) -> str:
    return f"테스트한 타깃: {_consumers(group)} {n:,}명"


# 다음 실제 조사의 조건
def next_target(group: str, n: int, board: str | None) -> str:
    text = f"{group} 응답자 {n:,}명 이상(본 테스트와 같은 규모)"
    if board and board != group:
        text += f". 컨셉 보드의 타깃({board})도 같은 인원으로 나란히 조사"
    return text


def next_question(label: str, name: str, flavor: str | None) -> str | None:
    """걸린 점 → 조사 문항. flavor는 컨셉의 맛 이름이 있을 때("수박화채 맛")."""
    taste = f"{flavor}에 대한 기대와 우려" if flavor else f"{name}의 맛에 대한 기대와 우려"
    return {
        "맛이 끌리지 않음": taste,
        "가격이 비쌈": "적정 가격과 가격 저항선(가격 제시 방식은 컨셉마다 같게)",
        "처음 보는 제품이라 망설여짐": "처음 보는 제품을 고를 때 확인하는 정보(브랜드, 제품 유형 표기)",
        "지금 상황에 안 맞음": "마시고 싶은 상황과 시간대",
        "용량이나 용기가 안 맞음": "선호하는 용량과 용기",
        "늘 마시는 것이 있음": "평소 마시는 제품과 바꿔 볼 계기",
        "어떤 제품인지 모르겠음": "제품명과 패키지만으로 제품 유형을 알아보는지",
    }.get(label)


NEXT_CONDITIONS = [
    "컨셉 제시 순서를 응답자마다 무작위로",
    "컨셉마다 같은 가격 표기(정가와 할인가를 함께 적지 않음)",
    "컨셉마다 같은 형식의 설명(한쪽에만 붙는 권유 문구 없음)",
]
NEXT_UNKNOWNS = [
    "맛과 재선택 의향(시음 없이 진열대에서의 선택만 확인)",
    "광고, 행사, 진열 위치의 효과",
    "출시 후 계절과 시기에 따른 변화",
]


# 부록
def method_shelf(shelf: str, others: int) -> str:
    return f"매대: 편의점 {shelf} 매대 기존 {others}개 제품에 본 제품을 더해 {others + 1}개 제품"


def method_people(group: str, asked: int, total: int) -> str:
    tail = f"(배정 {total:,}명 중 응답 {asked:,}명 기준)" if asked < total else ""
    return f"인원: {_consumers(group)} {asked:,}명{tail}"


METHOD_SAMPLE = ("뽑은 법: 공개 통계 기반 가상 소비자 패널에서 타깃 조건(연령대, 성별)에 맞는 소비자를 고정된 무작위 차례로 배정. "
                 "음용 상황은 그 집단의 실제 음용 기록 비중대로")
METHOD_COMPARE = "비교: 같은 소비자에게 본 제품이 없는 매대와 있는 매대를 따로 제시해 선택을 비교"


def rule_lines(research: float, retest: float, own: float, own_min: int, *,
               paired: list[str] | None = None, unpaired: list[str] | None = None) -> list[str]:
    comparison = []
    if paired:
        comparison.append(f"{', '.join(paired)}: 같은 방문의 선택률 차이 95% 구간을 사용. 구간 전체가 0보다 크면 증가, 작으면 감소, 0을 포함하면 뚜렷한 차이 없음")
    if not paired or unpaired:
        comparison.append((f"{', '.join(unpaired)}: " if unpaired else "") +
                          "개선안 가운데 기존안과 범위(윌슨 95% 구간)가 겹치지 않고 더 많이 선택된 안이 있으면 그 안으로 권고")
    return [
        f"실제 소비자 조사 진행: 본 제품보다 많이 선택된 기존 제품이 기존 제품의 {research:.0%} 미만",
        f"수정 후 재테스트: 위에 해당하지 않고, 본 제품보다 많이 선택된 기존 제품이 {retest:.0%} 미만",
        f"보류: 선택한 소비자가 0명이거나, 본 제품보다 많이 선택된 기존 제품이 {retest:.0%} 이상",
        *comparison,
        f"선택한 소비자가 {own_min}명 이상이고 그 {own:.0%} 이상이 자사 제품을 선택하던 소비자이면 겹침 확인 필요를 이유에 추가",
        "위 문턱값은 초안이며 실제 조사 결과로 다시 맞출 예정",
    ]


# 확정 차례: 컨셉 보드 분석에 걸린 점이 있으면 분석 단계를 가리킨다.
def diagnosis_flags(count: str) -> str:
    return f"컨셉 보드 분석에서 살펴볼 점이 {count} 가지 나왔어요."


def diagnosis_pick(priced: bool, has_fix: bool) -> str:
    if not has_fix:
        return "오른쪽에서 확인하고 테스트해 주세요."
    return f"오른쪽에서 보고 어떤 {'가격' if priced else '안'}으로 테스트할지 골라 주세요."


# 확정 차례(보드 하나): 칠성이가 분석을 인사이트로 정리하고 매대 테스트를 제안한다(견본 /proto/analysis, 참가자 승인 11-25).
# 숫자는 코드가 넣는다. 견본의 글(web/src/proto/board-analysis/copy.ts)과 같은 말이다.
def won(n: float) -> str:
    return f"{int(n + 0.5):,}원"


def analysis_lead(flags: int) -> str:
    if not flags:
        return "이 컨셉으로 정했어요. 분석에서 테스트를 막는 점은 없었어요."
    return f"이 컨셉으로 정했어요. 분석에서 살펴볼 점이 {spoken.count(flags)} 가지 나왔어요."


def analysis_cooling(word: str, pct: int) -> str:
    return f"{word} 검색은 올여름 정점이 작년 여름의 {pct}%예요."


def analysis_price_over(current: float, median: float, gap: float) -> str:
    return f"{won(current)}은 소비자가 내겠다는 값({won(median)})보다 {won(gap)} 높아요."


def analysis_cheaper(count: int, low: float) -> str:
    return f"다만 같은 용량의 다른 제품 {count}종({won(low)}부터)보다는 싸요."


def analysis_propose(a: float, b: float) -> str:
    return f"가격만 바꿔 {won(a)}과 {won(b)}을 매대에서 견줘 볼까요?"


ANALYSIS_PROPOSE_ONE = "이대로 매대에 올려 볼까요?"


def btn_test_both(a: float, b: float) -> str:
    return f"{won(a)}과 {won(b)} 둘 다 테스트"


def btn_test_only(p: float) -> str:
    return f"{won(p)}만 테스트"


BTN_TEST_AS_IS = "이대로 테스트하기"

