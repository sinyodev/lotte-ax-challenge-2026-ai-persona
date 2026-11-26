"""모델을 부르는 곳의 인터페이스. 어댑터는 AX_LLM(cli|codex|openai|fake, 기본 openai)으로 고른다.

API 열쇠를 코드나 파일에 적지 않는다. 모델에게 보내는 글에 사용자의 이름, 이메일, 저장소 경로를 넣지 않는다.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any, Protocol

# 한 차례 동안 부른 기록(일, 걸린 시간, 성공, 취소)을 모으는 곳. 대화 파일에 차례마다 남긴다(chats.py).
TURN_CALLS: ContextVar[list[dict[str, Any]] | None] = ContextVar("turn_calls", default=None)


def note_call(entry: dict[str, Any]) -> None:
    calls = TURN_CALLS.get()
    if calls is not None:
        calls.append(entry)


class LLMError(Exception):
    """시간이 넘었거나 부르기에 실패했다."""


class LLMTimeout(LLMError):
    """시간이 넘었다."""


class LLM(Protocol):
    async def ask(self, task: str, system: str, user: str, schema: dict[str, Any], *,
                  web: bool = False, timeout: float = 60.0, model: str | None = None) -> dict[str, Any]:
        """정해진 형식(schema)의 JSON 하나를 돌려준다. 실패하면 LLMError(시간이 넘으면 LLMTimeout).
        task는 일의 이름(read_first, read_target, read_occasion, trend, ideas, concepts, voice)이다.
        model을 주면 그 일에만 그 모델을 쓴다(말 쓰기의 AX_VOICE_MODEL)."""
        ...


_current: LLM | None = None


def get_llm() -> LLM:
    global _current
    if _current is None:
        name = os.environ.get("AX_LLM", "openai")
        if name == "fake":
            from llm.fake import FakeLLM

            _current = FakeLLM()
        elif name == "cli":
            from llm.cli import CliLLM

            _current = CliLLM()
        elif name == "codex":
            from llm.codex import CodexLLM

            _current = CodexLLM()
        elif name == "openai":
            from llm.openai_api import OpenAILLM

            _current = OpenAILLM()
        else:
            raise ValueError("AX_LLM은 cli, codex, openai, fake 가운데 하나여야 해요")
    return _current


def set_llm(llm: LLM | None) -> None:
    """테스트가 어댑터를 바꿔 끼울 때 쓴다."""
    global _current
    _current = llm
