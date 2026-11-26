"""모델을 부르는 곳은 이 파일 하나다. 현장에서 다른 회사 모델로 바꿀 때 여기만 고친다.

가상 손님 한 명에게 매대를 보여주고 답을 정해진 형식으로 받는다.
인증: ANTHROPIC_API_KEY 환경 변수(또는 `ant auth login` 프로필). 코드에 키를 적지 않는다.
"""

from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"
MAX_TOKENS = 4000
PROMPT_VERSION = "pilot-1"


class Choice(BaseModel):
    """가상 손님의 답. 판단(번호, 욕구 번호)과 말(이유 문장)을 나눠 받는다."""

    choice_number: int = Field(description="고른 제품의 매대 번호. 아무것도 사지 않으면 0")
    reason_needs: list[str] = Field(description="고른 이유에 해당하는 욕구 번호. 1~3개. 목록에 없으면 빈 목록")
    reason_other: str = Field(description="목록에 없는 이유가 있으면 짧게. 없으면 빈 문자열")
    reason_sentence: str = Field(description="손님의 말투로 쓴 이유 한두 문장")


_client = None


def ask(system: str, user: str):
    """(답, 사용량)을 돌려준다. 모델이 답을 거절했거나 형식이 맞지 않으면 답은 None이다."""
    global _client
    import anthropic

    if _client is None:
        _client = anthropic.Anthropic()
    response = _client.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=Choice,
    )
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    if response.stop_reason == "refusal":
        return None, usage
    return response.parsed_output, usage
