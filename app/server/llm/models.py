"""앱의 일 이름과 응답기별 모델 설정을 연결한다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


Role = Literal["read", "plan", "shopper", "interview", "voice"]


@dataclass(frozen=True)
class ModelChoice:
    model: str
    effort: str | None = None


# 역할별 워크스페이스 실측과 선정 근거는 docs/model-choice.md에 있다.
_GPT_DEFAULTS = {
    "read": ModelChoice("gpt-6.2-sol", "low"),
    "plan": ModelChoice("gpt-6.2-sol", "low"),
    "shopper": ModelChoice("gpt-6-luna", "low"),
    "interview": ModelChoice("gpt-6-luna", "low"),
    "voice": ModelChoice("gpt-6-luna", "low"),
}

_LEGACY_MODEL_ENV = {
    "read": "AX_VOICE_MODEL",
    "plan": "AX_CLI_MODEL",
    "shopper": "AX_SHOPPER_MODEL",
    "interview": "AX_SHOPPER_MODEL",
    "voice": "AX_VOICE_MODEL",
}


def role_for_task(task: str) -> Role:
    if task == "group_turn":
        return "interview"
    if task in ("voice", "shopper", "interview"):
        return task
    if task in ("pod", "improve_extract") or task == "read" or task.startswith("read_"):
        return "read"
    return "plan"


IMAGE_DEFAULT = "gpt-image-1"


def model_for(role: str, *, backend: str | None = None) -> ModelChoice:
    if role == "image":
        # 컨셉의 예시 이미지(imagegen/). 대회 게이트웨이의 이미지 생성 모델. 뒷단과 상관없이 하나다.
        return ModelChoice(os.getenv("AX_MODEL_IMAGE") or IMAGE_DEFAULT)
    if role not in _GPT_DEFAULTS:
        raise ValueError(f"알 수 없는 모델 역할: {role}")
    backend = backend or os.environ.get("AX_LLM", "openai")
    if backend in ("codex", "openai"):
        default = _GPT_DEFAULTS[role]
        legacy = None if role == "plan" else _LEGACY_MODEL_ENV.get(role)
    elif role == "interview":
        default = model_for("shopper", backend=backend)
        legacy = None
    else:
        legacy = _LEGACY_MODEL_ENV[role]
        default = ModelChoice("sonnet" if role in ("read", "voice") else "claude-opus-5-5")
    model = os.getenv(f"AX_MODEL_{role.upper()}") or (os.getenv(legacy) if legacy else None)
    effort = os.getenv(f"AX_EFFORT_{role.upper()}") or default.effort
    return ModelChoice(model or default.model, effort)


def choice_for_call(task: str, model: str | None, *, backend: str) -> ModelChoice:
    role = role_for_task(task)
    selected = model_for(role, backend=backend)
    if role == "interview" and model == model_for("shopper", backend=backend).model:
        # 기존 인터뷰 호출부가 매대 설정을 넘긴다. 이때 인터뷰에 정한 값을 쓴다.
        return selected
    return ModelChoice(model or selected.model, selected.effort)
