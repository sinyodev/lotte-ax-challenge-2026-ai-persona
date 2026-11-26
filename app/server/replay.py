"""재생 방식 (약속 5절): 대본 파일을 읽어 칠성이의 이벤트를 차례로 낸다. 모델을 부르지 않는다.

대본에서만 쓰는 것
- {"t": "wait", "ms": 600}: 잠깐 쉰다. 내보내지 않는다.
- {"t": "activity", "id", "label", "ms"}: running을 보내고 ms만큼 쉰 뒤 done을 보낸다.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from events import (
    Actions,
    Activity,
    Card,
    ChilseongEvent,
    Choices,
    Confirm,
    Say,
    Stage,
    Summary,
)

REPLAY_DIR = Path(__file__).parent / "replay"

Sleep = Callable[[float], Awaitable[None]]


class Wait(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t: Literal["wait"] = "wait"
    ms: int = Field(ge=0)


class ScriptActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t: Literal["activity"] = "activity"
    id: str
    label: str
    ms: int = Field(ge=0)


ScriptEvent = Annotated[
    Union[Say, ScriptActivity, Wait, Choices, Actions, Confirm, Summary, Stage, Card],
    Field(discriminator="t"),
]


class Script(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    sample: bool
    turns: list[list[ScriptEvent]]
    after: list[ScriptEvent]


_script_adapter = TypeAdapter(Script)


def load_script(name: str) -> Script:
    path = REPLAY_DIR / f"{name}.json"
    return _script_adapter.validate_python(json.loads(path.read_text(encoding="utf-8")))


def turn_for(script: Script, user_turn: int) -> list[ScriptEvent]:
    """기획자의 n번째 말(1부터)에 내보낼 대본. 대본이 끝난 뒤에는 after."""
    if 1 <= user_turn <= len(script.turns):
        return script.turns[user_turn - 1]
    return script.after


async def play(events: list[ScriptEvent], sleep: Sleep = asyncio.sleep) -> AsyncIterator[ChilseongEvent]:
    """대본 한 차례를 칠성이의 이벤트로 바꿔 차례로 낸다."""
    for ev in events:
        if isinstance(ev, Wait):
            await sleep(ev.ms / 1000)
        elif isinstance(ev, ScriptActivity):
            yield Activity(id=ev.id, label=ev.label, status="running")
            await sleep(ev.ms / 1000)
            yield Activity(id=ev.id, label=ev.label, status="done")
        else:
            yield ev
