"""컨셉이 없는 매대의 답을 미리 쌓아 둔다. 어느 상황을 겨냥한 컨셉이 와도 컨셉을 올린 매대만 물으면 되게.

타깃 손님의 앞 절반은 컨셉이 겨냥한 상황을 받는다(method.occasion_of). 그 (손님, 상황)의 답을 상황마다 미리 묻는다.
이미 저장된 것은 건너뛴다. 묻는 글과 저장하는 모양은 테스트가 돌 때와 같다(runner._ask, store.append_baseline).

실행: uv run python -m shelftest.warm --band 19-29 [--workers 16] [--until 02:55] [--codes D1 D2]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime

from shelftest import method, runner, store


async def main(band: str, workers: int, until: str | None, codes: list[str] | None, total: int) -> None:
    model = runner.shopper_model()
    v = method.shelf_v()
    cache = store.baselines(v, model)
    sem = asyncio.Semaphore(workers)
    stop_at = datetime.combine(datetime.now().date(), datetime.strptime(until, "%H:%M").time()) if until else None
    for code in codes or list(method.occasions()):
        plan = method.plan(band, None, code, total, "미리 묻기", 1000, None)
        todo = [x for x in plan.visits if x["상황 번호"] == code and (x["uuid"], code) not in cache]
        started, done = time.monotonic(), 0

        async def one(visit: dict) -> None:
            nonlocal done
            async with sem:
                if stop_at and datetime.now() >= stop_at:
                    return
                row, _ = await runner._ask(plan, visit, method.BASELINE, model)
            if row is None:
                return
            base = {"uuid": visit["uuid"], "occasion": code, **row}
            cache[(visit["uuid"], code)] = base
            store.append_baseline(v, model, base)
            done += 1

        await asyncio.gather(*(one(x) for x in todo))
        took = time.monotonic() - started
        print(f"{code} {method.occasions()[code]['상황']}: {done}/{len(todo)}명, {took:.0f}초"
              + (f", 한 명에 {took / done:.1f}초(동시에 {workers}명)" if done else ""), file=sys.stderr, flush=True)
        if stop_at and datetime.now() >= stop_at:
            break


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--band", default="19-29")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--until")
    p.add_argument("--codes", nargs="*")
    p.add_argument("--total", type=int, default=runner.DEFAULT_TOTAL)
    a = p.parse_args()
    asyncio.run(main(a.band, a.workers, a.until, a.codes, a.total))
