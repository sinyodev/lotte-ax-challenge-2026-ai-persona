"""도는 테스트의 기다리는 화면에 보일 것 (11-25, GET /api/runs/{id}의 waiting 칸).

모델을 부르지 않는다. 쌓인 답에서 그때그때 센다.

- 진행: 한 손님에게 두 매대(컨셉이 있는 매대, 없는 매대)를 묻는다. 남은 일은 "답 수"로 센다(steps).
  저장해 둔 답을 다시 쓴 걸음은 처음부터 끝나 있던 일이라 세지 않는다(막대가 절반에서 시작하지 않게).
  빠진 손님은 두 걸음을 모두 끝낸 것으로 센다.
  그래서 steps_done == steps_total이면 남은 묻기가 없다(곧 끝난다).
- 남은 시간: 최근에 새로 온 답(다시 쓴 답은 뺀다)의 속도로 계산한다. 속도를 모를 때는 None.
- 지금까지의 한 줄(lead): 응답이 너무 적으면 None. 탐색은 칸마다 10명 이상이고 가장 높은 칸이 하나일 때만,
  타깃은 30명 이상일 때만.
- 방금 다녀간 손님(recent): 컨셉이 있는 매대의 답만, 최근 것부터. 손님의 uuid와 이름은 내보내지 않는다.
  이름이 든 말은 비운다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shelftest import method
from tools.consumer import AGE_NAMES
from tools.occasion_display import show as show_occasion

RECENT = 6
SAID_MAX = 120
RATE_SPAN_S = 90.0  # 속도를 재는 최근 시간
RATE_WINDOW = 40  # 최근 시간에 답이 모자랄 때 쓰는 최근 답의 수
MIN_FRESH = 6  # 이만큼 새 답이 와야 남은 시간을 말한다
MIN_SPAN_S = 5.0
EXPLORE_MIN_PER_CELL = 10
TARGET_MIN = 30


def _ts(at: str | None) -> float | None:
    if not at:
        return None
    try:
        return datetime.fromisoformat(at).timestamp()
    except ValueError:
        return None


def _steps(meta: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    """(끝낸 걸음, 전체 걸음, 컨셉 매대의 답이 온 손님, 두 매대의 답이 모두 온 손님)."""
    total = int(meta["total"])
    got: dict[str, set[str]] = {}
    reused: set[tuple[str, str]] = set()
    skipped: set[str] = set()
    for r in rows:
        v = r.get("visit")
        if not v:
            continue
        if r.get("skip"):
            skipped.add(v)
        else:
            got.setdefault(v, set()).add(r.get("cond", ""))
            if r.get("reused") and r.get("cond") in (method.CONCEPT, method.BASELINE):
                reused.add((v, r["cond"]))
    done = 0
    concept = both = 0
    for v, conds in got.items():
        if v in skipped:
            continue
        has_c, has_b = method.CONCEPT in conds, method.BASELINE in conds
        done += has_c + has_b
        concept += has_c
        both += has_c and has_b
    done += 2 * len(skipped)
    # 저장해 둔 답을 다시 쓴 걸음은 처음부터 끝나 있던 일이라 진행에서 뺀다.
    # 빼지 않으면 손님이 한 명도 다녀가기 전에 막대가 절반에서 시작한다(참가자의 검수 11-25).
    free = sum(1 for v, _ in reused if v not in skipped)
    return max(0, min(done, 2 * total) - free), max(0, 2 * total - free), concept, both


def _eta(rows: list[dict[str, Any]], remaining: int, now: float) -> float | None:
    if remaining <= 0:
        return 0.0
    times = sorted(t for r in rows if not r.get("skip") and not r.get("reused") and r.get("visit")
                   for t in [_ts(r.get("at"))] if t is not None)
    if len(times) < MIN_FRESH:
        return None
    # 최근 RATE_SPAN_S초의 답(모자라면 최근 RATE_WINDOW개)으로 잰다
    window = [t for t in times if t >= now - RATE_SPAN_S]
    if len(window) < MIN_FRESH:
        window = times[-RATE_WINDOW:]
    # 마지막 답 뒤로 흐른 시간도 넣는다(답이 멈췄으면 남은 시간이 늘어난다)
    span = max(window[-1], now) - window[0]
    if span < MIN_SPAN_S:
        return None
    rate = (len(window) - 1) / span
    if rate <= 0:
        return None
    return round(remaining / rate, 1)


def _shown(meta: dict[str, Any]):
    line, name = meta["line"], meta["concept"]["name"]
    info = {key: shown for key, shown, _ in meta.get("shelf_products") or []}

    def shown(product: str) -> str:
        if product == line:
            return name
        if product == method.NO_PURCHASE:
            return method.NO_PURCHASE
        return info.get(product) or method.display(product)

    return shown


def _recent(meta: dict[str, Any], rows: list[dict[str, Any]], people: dict[str, Any]) -> list[dict[str, Any]]:
    planned = {p["visit"]: p for p in meta.get("participants") or []}
    shown = _shown(meta)
    out = []
    for r in reversed(rows):
        if len(out) >= RECENT:
            break
        if r.get("skip") or r.get("cond") != method.CONCEPT or not r.get("product"):
            continue
        person = people.get(r.get("uuid", ""))
        plan = planned.get(r.get("visit"), {})
        age = plan.get("age") or (person.band if person else "")
        sex = plan.get("sex") or (person.sex if person else "")
        said = (r.get("sentence") or "").replace("\n", " ").strip()
        if said and (person is None or any(w and w in said for w in method.name_words(person))):
            said = ""
        occ = show_occasion(method.occasions().get(r.get("occasion", ""), {}).get("상황"))
        out.append({"visit": r["visit"], "age": AGE_NAMES.get(age, age), "sex": sex, "occasion": occ,
                    "chose": shown(r["product"]), "said": said[:SAID_MAX], "ours": r["product"] == meta["line"]})
    return out


def _lead(meta: dict[str, Any], pairs: list[tuple[dict | None, dict]], explore_view: dict | None) -> dict[str, Any] | None:
    if explore_view is not None:
        cells = explore_view.get("cells") or []
        if not cells or any(c["n"] < EXPLORE_MIN_PER_CELL for c in cells):
            return None
        peak = max(c["picked"] / c["n"] for c in cells)
        top = [c for c in cells if c["picked"] / c["n"] == peak]
        if peak <= 0 or len(top) != 1:
            return None
        c = top[0]
        return {"kind": "group", "age": AGE_NAMES.get(c["age"], c["age"]), "sex": c["sex"],
                "picked": c["picked"], "n": c["n"]}
    n = len(pairs)
    if n < TARGET_MIN:
        return None
    picked = sum(1 for _, c in pairs if c.get("product") == meta["line"])
    return {"kind": "target", "picked": picked, "n": n, "name": meta["concept"]["name"]}


def view(meta: dict[str, Any], rows: list[dict[str, Any]], pairs: list[tuple[dict | None, dict]],
         people: dict[str, Any], explore_view: dict | None, now: float | None = None) -> dict[str, Any]:
    import time

    now = time.time() if now is None else now
    done, total, concept, both = _steps(meta, rows)
    return {
        "mode": meta.get("mode", "target"),
        "steps_done": done, "steps_total": total,
        "visited": concept, "complete": both,
        "eta_s": _eta(rows, total - done, now),
        "lead": _lead(meta, pairs, explore_view),
        "recent": _recent(meta, rows, people),
    }
