"""대화마다 한 작업이 차례를 실행하고 기록한다. HTTP 응답은 그 작업의 출력만 읽는다."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import aclosing
from contextvars import Context
from typing import Any

from pydantic import BaseModel

import chats
from llm import usage
from llm.base import TURN_CALLS

logger = logging.getLogger(__name__)


class Turn:
    def __init__(self, record: chats.TurnRecord, events: AsyncGenerator[BaseModel, None],
                 finish_note: Callable[[bool], dict[str, Any] | None], trace: dict[str, Any]) -> None:
        self.record = record
        self.buffer: asyncio.Queue[BaseModel | None] = asyncio.Queue()
        self.started = False
        self.stopping = False
        self.error: Exception | None = None
        self.discard = False
        chats.ACTIVE[record.id] = self
        self.task = asyncio.create_task(self._run(events, finish_note, trace), context=Context())

    async def _produce(self, events: AsyncGenerator[BaseModel, None]) -> None:
        try:
            async with aclosing(events):
                if self.stopping:
                    raise asyncio.CancelledError
                async for event in events:
                    self.record.add(event)
                    self.buffer.put_nowait(event)
        except asyncio.CancelledError:
            self.stopping = True
        except Exception as err:
            logger.exception("대화 %s 차례 오류", self.record.id)
            self.error = err

    async def _run(self, events, finish_note, trace) -> None:
        self.started = True
        rec = self.record
        calls: list[dict[str, Any]] = []
        TURN_CALLS.set(calls)
        try:
            with usage.collect() as meter:
                await self._produce(events)
            if rec.id in chats.DELETED:
                return
            stopped = self.stopping or self.error is not None
            note = finish_note(stopped)
            if not self.discard:
                rec.turn["usage"] = meter.summary()
                rec.finish(note=note, stopped=stopped, trace=trace, calls=calls,
                           error=repr(self.error) if self.error else None)
        except Exception as err:
            logger.exception("대화 %s 차례 저장 오류", rec.id)
            self.error = err
        finally:
            chats.ACTIVE.pop(rec.id)
            chats.DELETED.discard(rec.id)
            self.buffer.put_nowait(None)

    async def stream(self) -> AsyncIterator[BaseModel]:
        while (event := await self.buffer.get()) is not None:
            yield event
        if self.error is not None:
            raise self.error

    async def stop(self) -> None:
        if not self.stopping:
            self.stopping = True
            # 첫 실행 전의 Task를 cancel하면 마무리 코드도 실행되지 않는다.
            if self.started:
                self.task.cancel()
        await asyncio.shield(self.task)


async def shutdown() -> None:
    running = list(chats.ACTIVE.values())
    for turn in running:
        turn.discard = True
    await asyncio.gather(*(turn.stop() for turn in running))
