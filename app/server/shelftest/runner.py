"""매대 테스트를 뒤에서 돌린다 (지시서 15의 1절 "돌리기").

- 테스트 하나 = 뒤에서 도는 작업 하나(asyncio). 동시에 AX_SHOPPER_WORKERS명(기본 8).
- 컨셉을 올린 매대부터 모든 손님에게 묻고, 그 답이 오면 그 손님이 다녀간 것이다("몇 명이 집었나"와 "걸린 점"이 먼저 나온다).
  컨셉이 없는 매대는 저장해 둔 답이 있으면 처음에 바로 쓰고, 없으면 컨셉 매대가 다 끝난 뒤에 묻는다("누구 것을 가져오나").
- 가상 손님의 모델은 AX_SHOPPER_MODEL(기본 claude-opus-5-5). 어댑터(llm/)로 부른다. claude -p 어댑터는 시스템 글을
  우리 것으로 바꾸고 도구를 모두 끈다(pilot.answer_by_cli와 같은 조건).
- 답이 올 때마다 store/runs/<id>.jsonl에 한 줄씩 덧붙인다. 서버를 다시 띄운 뒤 그 테스트를 읽으면 남은 손님부터 이어서 돈다.
- 컨셉이 없는 매대의 답은 store/baselines/에 (매대 자료의 판, 모델, 손님, 상황)으로 두고 다시 쓴다.
- 같은 것(컨셉의 이름·용기와 용량·가격·행사, 타깃, 상황, 인원, 모델)을 다시 올리면 새로 돌리지 않고 그 테스트를 준다.
- 틀린 답은 두 번까지 다시 묻고, 그래도 안 되면 그 손님을 빼고 간다(결과의 skipped).
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import os
import sys
import time
import uuid
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from llm.base import LLMError, get_llm
from shelftest import explore, method, result, shopper_json, store, usage
from tools import consumer, shelf_items
from tools.occasion_display import show as show_occasion
from tools.consumer import Group

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_WORKERS = 8
DEFAULT_TOTAL = 300
DEFAULT_EXPLORE_PER_CELL = 40
RETRIES = 2  # 틀린 답을 다시 묻는 횟수
ASK_TIMEOUT = 180.0
CONCEPT_PROMPT_VERSION = 1
# 11차 글에서 컨셉을 보이는 방식(shopper_json.BLIND). 새 실행에만 적고, 옛 실행은 적힌 값(없으면 옛 방식)대로 다시 연다.
CHOICE_METHOD = "blind-v1"

TASKS: dict[str, asyncio.Task] = {}
# 개선안(change가 있는 테스트)은 대화마다 뒤에서 차례로 돈다(지시서 17의 B: 여러 안을 한꺼번에 눌러도 하나씩)
_IMPROVE_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}


def _improve_lock(chat_id: str) -> asyncio.Lock:
    key = (id(asyncio.get_running_loop()), chat_id)
    lock = _IMPROVE_LOCKS.get(key)
    if lock is None:
        lock = _IMPROVE_LOCKS[key] = asyncio.Lock()
    return lock


def default_total() -> int:
    """대화에서 올릴 때의 인원(기본 300). 확인할 때 적은 인원으로 돌리려면 AX_SHELF_TOTAL."""
    try:
        return max(1, int(os.environ.get("AX_SHELF_TOTAL", DEFAULT_TOTAL)))
    except ValueError:
        return DEFAULT_TOTAL


def explore_per_cell() -> int:
    try:
        return max(1, int(os.environ.get("AX_EXPLORE_PER_CELL", DEFAULT_EXPLORE_PER_CELL)))
    except ValueError:
        return DEFAULT_EXPLORE_PER_CELL


def shopper_model() -> str:
    from llm.models import model_for

    return model_for("shopper").model


def workers() -> int:
    try:
        return max(1, int(os.environ.get("AX_SHOPPER_WORKERS", DEFAULT_WORKERS)))
    except ValueError:
        return DEFAULT_WORKERS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ---------- 무엇을 누구에게 ----------


@dataclass
class Spec:
    chat_id: str
    concept_id: str
    name: str
    container: str
    volume: int
    price: int
    promo: str | None = None
    age: str | None = None
    sex: str | None = None
    occasion_code: str | None = None
    total: int = DEFAULT_TOTAL
    change: dict[str, Any] = field(default_factory=dict)
    mode: Literal["target", "explore", "improve"] = "target"
    explore_id: str | None = None
    target_basis: str | None = None
    storage: str | None = None
    base_run_id: str | None = None  # 개선 전 실행을 대화에서 이미 알고 있을 때
    features: dict[str, str] = field(default_factory=dict)
    season: str | None = None
    launch: str | None = None


CHANGE_KEYS = ("name", "container", "volume", "price", "promo")


def apply_change(spec: Spec, change: dict[str, Any] | None, *, require_original: bool = False) -> Spec:
    """공개 통로의 개선안은 같은 타깃 테스트의 저장된 제품 조건 하나를 바꾼다."""
    if not change:
        return spec
    if require_original:
        from agent import improve

        original = _original_run(spec, spec.total, store.all_meta())
        if not original:
            raise ValueError("같은 인원과 타깃의 원래 안을 먼저 테스트해 주세요.")
        if len(change) != 1:
            raise ValueError("개선안에서 바꿀 조건을 하나 골라 주세요.")
        values = dict(change)
        if any(type(v) not in (int, str) for v in values.values()):
            raise ValueError("바꿀 조건을 숫자나 매대에 표시할 글로 입력해 주세요.")
        for key in ("price", "volume"):
            if key in values and isinstance(values[key], str) and values[key].isdigit():
                values[key] = int(values[key])
        base = improve.Base.of(original["concept"])
        why = improve.check_values(base, values, price_step=True)
        if why:
            raise ValueError(why[0])
        if not improve.diff(base, values):
            raise ValueError("원래 안과 다른 조건을 골라 주세요.")
        candidate = improve.applied(base, values)
        spec.name, spec.price, spec.volume = candidate.name, candidate.price, candidate.volume
        spec.container, spec.promo, spec.features = candidate.container, candidate.promo, candidate.features
        spec.base_run_id, spec.change = original["id"], values
        return spec
    for k in CHANGE_KEYS:
        if k in change and change[k] not in (None, ""):
            v = change[k]
            setattr(spec, k, int(v) if k in ("volume", "price") else str(v))
    feature_changes = {k: change[k] for k in shelf_items.FEATURE_LABELS if change.get(k)}
    spec.features.update(feature_changes)
    spec.change = {**{k: change[k] for k in CHANGE_KEYS if k in change}, **feature_changes}
    return spec


def who_label(age: str | None, sex: str | None) -> str:
    return f"{consumer.default_label(Group(age=age, sex=sex))} 손님"


def occasion_share(age: str | None, sex: str | None, code: str | None) -> float | None:
    """그 집단의 음료 자리 가운데 그 상황의 비중(%)."""
    if not code:
        return None
    for o in consumer.occasions(None, Group(age=age, sex=sex), method.SHELF):
        if o.occasion.code == code:
            return round(o.score, 1)
    return None


def _hash(key: Any) -> str:
    return hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:16]


def _same_target(meta: dict[str, Any], spec: Spec, requested: int) -> bool:
    return (
        meta.get("mode", "target") == "target" and not meta.get("change")
        and meta["chat_id"] == spec.chat_id and meta["concept_id"] == spec.concept_id
        and (spec.explore_id is None or meta.get("explore_id") == spec.explore_id)
        and meta["target"] == {"age": spec.age, "sex": spec.sex}
        and meta.get("occasion_code") == spec.occasion_code
        and int(meta.get("requested", meta["total"])) == requested
    )


def _original_run(spec: Spec, requested: int, history: list[dict[str, Any]]) -> dict[str, Any] | None:
    if spec.base_run_id:
        original = store.load_meta(spec.base_run_id)
        if original is None or not _same_target(original, spec, requested):
            raise ValueError("개선안의 처음 테스트를 찾을 수 없어요")
        return original
    candidates = (meta for meta in history if _same_target(meta, spec, requested))
    return max(candidates, key=lambda m: (m["started_at"], m.get("updated_at", ""), m["id"]), default=None)


def _snapshot(plan: method.Plan) -> list[dict[str, Any]]:
    return [{"visit": v["방문"], "uuid": v["uuid"], "age": v["연령대"], "sex": v["성별"],
             "occasion": v["상황 번호"], **{k: v[k] for k in ("visit_month", "temp_c", "shelf_seconds", "comparison_limit") if k in v}} for v in plan.visits]


def _assigned(meta: dict[str, Any], legacy: method.Plan | None = None) -> list[dict[str, Any]]:
    if "participants" in meta:
        return meta["participants"]
    # 옛 기록에는 배정표가 없다. 저장된 답의 손님과 상황을 먼저 보존한다.
    visits = _snapshot(legacy if legacy is not None else method.plan(*_plan_args(meta)))
    t = meta["target"]
    people = {p.uuid: p for p in method.people(t.get("age"), t.get("sex"))}
    answered = {}
    for row in store.answers(meta["id"]):
        v, uid, code = row.get("visit"), row.get("uuid"), row.get("occasion")
        if v and uid and code and (v not in answered or row.get("cond") == method.CONCEPT):
            p = people.get(uid)
            answered[v] = {"visit": v, "uuid": uid, "age": p.band if p else t.get("age") or "",
                           "sex": p.sex if p else t.get("sex") or "", "occasion": code}
    used = {p["uuid"] for p in answered.values()}
    visits = [p for p in visits if p["visit"] not in answered and p["uuid"] not in used]
    return sorted([*visits, *answered.values()], key=lambda p: p["visit"])


def create(spec: Spec) -> str:
    """테스트를 만들고 뒤에서 돌린다. 같은 것이 이미 있으면 그 테스트의 id(멈췄거나 실패했으면 이어서 돌린다)."""
    mode = "improve" if spec.mode == "target" and spec.change else spec.mode
    if mode == "explore":
        spec.age = spec.sex = spec.occasion_code = None
    if spec.occasion_code and spec.occasion_code not in method.occasions():
        spec.occasion_code = None
    model = shopper_model()
    shelf_v = method.shelf_v()
    adapter = os.environ.get("AX_LLM", "openai")
    prompt_version = CONCEPT_PROMPT_VERSION
    choice_method = CHOICE_METHOD if method.prompt_round() == 11 else None
    features = shelf_items.concept_features(spec.features)
    line = method.line_name(spec.name, spec.container, spec.volume)
    history = store.all_meta()
    original = None
    weights = None
    if mode == "explore":
        per_cell = explore_per_cell()
        requested = per_cell * len(explore.CELLS)
        people = explore.participants(per_cell)
        weights = explore.population_weights()
    else:
        requested = max(1, int(spec.total))
        original = _original_run(spec, requested, history) if mode == "improve" else None
        people = method.people(spec.age, spec.sex)
        if spec.explore_id and original is None:
            study = store.load_meta(spec.explore_id)
            if study is None or study.get("mode") != "explore":
                raise ValueError("탐색 테스트를 찾을 수 없어요")
            excluded = {p["uuid"] for p in _assigned(study)}
            people = [p for p in people if p.uuid not in excluded]
    if original is not None:
        if (original["shelf_v"] != shelf_v or original["model"] != model
                or original.get("shopper_adapter", adapter) != adapter):
            raise ValueError("매대 자료나 응답기가 바뀌었어요. 원래 안을 다시 테스트해 주세요.")
        prompt_version = original.get("concept_prompt_version", 0)
        if not prompt_version:
            if spec.change.keys() & shelf_items.FEATURE_LABELS.keys():
                raise ValueError("이전 테스트에서는 제품 특징을 보여 주지 않았어요. 원래 안을 다시 테스트해 주세요.")
            features = {}
        elif prompt_version != CONCEPT_PROMPT_VERSION:
            raise ValueError("제품을 보여 주는 방식이 달라졌어요. 원래 안을 다시 테스트해 주세요.")
        if original.get("choice_method") != choice_method:
            raise ValueError("제품을 보여 주는 방식이 달라졌어요. 원래 안을 다시 테스트해 주세요.")
        assigned = _assigned(original)
        if spec.explore_id is None:
            spec.explore_id = original.get("explore_id")
        if spec.target_basis is None:
            spec.target_basis = original.get("target_basis")
        if spec.storage is None:
            spec.storage = original.get("storage") or (original.get("placement") or {}).get("storage")
    else:
        plan = method.plan(spec.age, spec.sex, spec.occasion_code, requested, line, spec.price, spec.promo,
                           participants=people[:requested], storage=spec.storage, season=spec.season, launch=spec.launch)
        assigned = _snapshot(plan)
    placement = method.placement(spec.name, spec.storage)
    storage = placement["storage"] if placement else spec.storage
    total = len(assigned)
    legacy_key = [spec.name.strip(), spec.container, spec.volume, spec.price, spec.promo or "", spec.age or "",
                  spec.sex or "", spec.occasion_code or "", total, model, shelf_v]
    base_id = original["id"] if original is not None else None
    fp = _hash([legacy_key, mode, spec.chat_id, spec.concept_id, requested, spec.explore_id, spec.target_basis,
                storage, placement, assigned, weights, prompt_version, sorted(features.items()), base_id, adapter]
               + ([choice_method] if choice_method else []))
    for meta in history:
        if meta.get("fp") == fp:
            if meta.get("status") in ("stopped", "failed"):
                meta["status"] = "running"
                meta["updated_at"] = _now()
                store.save_meta(meta)
            ensure_running(meta["id"])
            return meta["id"]
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    now = _now()
    meta = {
        "id": run_id, "fp": fp, "status": "running", "chat_id": spec.chat_id, "concept_id": spec.concept_id,
        "concept": {"id": spec.concept_id, "name": spec.name.strip(), "pack": f"{spec.volume}ml {spec.container}",
                    "container": spec.container, "volume": spec.volume, "price": spec.price,
                    "promo": spec.promo or None, **features},
        "line": line, "target": {"age": spec.age, "sex": spec.sex}, "occasion_code": spec.occasion_code,
        "total": total, "requested": requested, "model": model, "shelf_v": shelf_v,
        "mode": mode, "explore_id": spec.explore_id, "target_basis": spec.target_basis, "storage": storage,
        "participants": assigned, "placement": placement, "shelf_products": result.catalog_snapshot(),
        "usage_version": 1,
        "concept_prompt_version": prompt_version, "base_run_id": base_id, "shopper_adapter": adapter,
        "shopper_round": method.prompt_round(), "choice_method": choice_method,
        "change": spec.change or None, "started_at": now, "updated_at": now,
    }
    if mode == "explore":
        meta["population_weights"] = weights
    used_months = sorted({p["visit_month"] for p in assigned if "visit_month" in p})
    if used_months:
        eligible = (original["visit_months"]["eligible"] if original and "visit_months" in original
                    else method.sale_months(line, season=spec.season, launch=spec.launch))
        meta["visit_months"] = {"eligible": eligible, "used": used_months}
        meta["concept"].update(season=spec.season, launch=spec.launch)
    store.save_meta(meta)
    _start(run_id)
    return run_id


def _start(run_id: str) -> None:
    loop = asyncio.get_running_loop()
    meta = store.load_meta(run_id)
    measured = usage.begin(run_id) if meta and meta.get("usage_version") else None
    # 새 문맥으로 띄운다: 대화의 한 차례가 모으는 모델 부르기 기록(llm.base.TURN_CALLS)에 섞이지 않게
    TASKS[run_id] = loop.create_task(_run(run_id, measured), context=contextvars.Context())


def ensure_running(run_id: str) -> None:
    """상태가 running인데 도는 작업이 없으면(서버를 다시 띄운 뒤) 남은 손님부터 이어서 돈다."""
    meta = store.load_meta(run_id)
    if not meta or meta.get("status") != "running":
        return
    task = TASKS.get(run_id)
    if task is None or task.done():
        try:
            _start(run_id)
        except RuntimeError:  # 도는 이벤트 루프가 없을 때(동기 코드에서 읽음)
            pass


def stop(run_id: str) -> bool:
    meta = store.load_meta(run_id)
    if meta is None:
        return False
    if meta.get("status") == "running":
        meta["status"] = "stopped"
        meta["updated_at"] = _now()
        store.save_meta(meta)
    active = usage.ACTIVE.get(run_id)
    if active is not None:
        active.finish()
    task = TASKS.pop(run_id, None)
    if task is not None and not task.done():
        task.cancel()
    return True


def resume(run_id: str) -> bool | None:
    """멈춘 테스트를 이어서 돌린다(11-25). 저장된 답은 _run이 다시 쓰고 남은 손님만 묻는다.
    테스트가 없으면 None, 멈춘 것이 아니면 False."""
    meta = store.load_meta(run_id)
    if meta is None:
        return None
    if meta.get("status") != "stopped":
        return False
    meta["status"] = "running"
    meta["updated_at"] = _now()
    store.save_meta(meta)
    ensure_running(run_id)
    return True


def _plan_args(meta: dict[str, Any]) -> tuple:
    c, t = meta["concept"], meta["target"]
    return (t.get("age"), t.get("sex"), meta.get("occasion_code"), int(meta.get("requested", meta["total"])),
            meta["line"], int(c["price"]), c.get("promo"))


def _saved_round(meta: dict[str, Any]) -> int:
    if meta.get("shopper_round") is not None:
        return meta["shopper_round"]
    visits = meta.get("participants") or []
    if any("comparison_limit" in v for v in visits):
        return 10
    if not meta.get("visit_months") and not any("visit_month" in v for v in visits):
        return method.ROUND
    # 차수 저장 전의 월별 배정은 당시 매대 지문으로 식별한다.
    for number in (6, 7, 8, 9):
        if meta.get("shelf_v") == method.shelf_v(number):
            return number
    return method.prompt_round()


def _plan(meta: dict[str, Any]) -> method.Plan:
    args = _plan_args(meta)
    saved_round = _saved_round(meta)
    options = {"round_number": saved_round} if saved_round != method.prompt_round() else {}
    if "participants" not in meta:
        legacy = method.plan(*args, **options)
        assigned = _assigned(meta, legacy)
        if assigned == _snapshot(legacy):
            return legacy
    else:
        assigned = meta["participants"]
    t = meta["target"]
    people = {p.uuid: p for p in method.people(t.get("age"), t.get("sex"))}
    occasions = method.occasions()
    selected = [people[p["uuid"]] for p in assigned if p["uuid"] in people and p["occasion"] in occasions]
    concept = meta["concept"]
    plan = method.plan(*args, participants=selected, storage=meta.get("storage"),
                       season=concept.get("season"), launch=concept.get("launch"), **options)
    assignments = {p["uuid"]: p for p in assigned}
    for visit in plan.visits:
        saved = assignments[visit["uuid"]]
        code = saved["occasion"]
        visit.update({"방문": saved["visit"], "상황 번호": code, "상황": occasions[code]["상황"]})
        visit.update({k: saved[k] for k in ("visit_month", "temp_c", "shelf_seconds", "comparison_limit") if k in saved})
    if meta.get("concept_prompt_version") == CONCEPT_PROMPT_VERSION:
        plan = shelf_items.enrich_concept(plan, meta["concept"])
        plan.with_concept["concept_prompt_version"] = CONCEPT_PROMPT_VERSION
    if meta.get("choice_method"):
        plan.with_concept["choice_method"] = meta["choice_method"]
    return plan


async def _ask(plan: method.Plan, visit: dict[str, Any], cond: str, model: str,
               measured: usage.RunUsage | None = None) -> tuple[dict[str, Any] | None, str]:
    if getattr(plan, "round_number", None) == 10:
        from shelftest import journey
        return await journey.run(plan, visit, cond, model, measured, get_llm, RETRIES, ASK_TIMEOUT)
    system, user, order = method.prompts(plan, visit, cond)
    asked = cond == method.CONCEPT
    if asked and plan.with_concept.get("concept_prompt_version") == CONCEPT_PROMPT_VERSION:
        user += shelf_items.concept_prompt(plan, order)
    if asked and shopper_json.blind(plan):
        return await _ask_blind(plan, system, user, order, model, measured)
    return await _ask_prepared(system, user, order, method.schema(asked), asked, model, measured)


async def _ask_blind(plan: method.Plan, system: str, user: str, order: list[dict[str, str]], model: str,
                     measured: usage.RunUsage | None) -> tuple[dict[str, Any] | None, str]:
    """blind-v1: 새 상품을 짚지 않은 매대에서 먼저 고르게 하고, 고른 것을 못 박은 뒤 새 상품에 대한 생각을 따로 묻는다."""
    row, why = await _ask_prepared(system, user, order, method.schema(False), False, model, measured)
    if row is None:
        return None, why
    if row["product"] == plan.line:
        row.update(view="이번에 산다", barriers=[], said=row["sentence"])
        return row, ""
    follow = shopper_json.opinion_prompt(plan, user, order, row)
    for _ in range(1 + RETRIES):
        started = time.monotonic()
        try:
            llm = get_llm()
            with measured.call() if measured is not None else nullcontext():
                raw = await llm.ask("shopper", system, follow, shopper_json.opinion_schema(),
                                    timeout=ASK_TIMEOUT, model=model)
            row.update(shopper_json.parse_opinion(raw))
            row["sec"] = round(row["sec"] + time.monotonic() - started, 1)
            return row, ""
        except (LLMError, method.BadAnswer) as e:
            why = type(e).__name__
    return None, why


async def _ask_prepared(system: str, user: str, order: list[dict[str, str]], schema: dict[str, Any],
                        asked: bool, model: str, measured) -> tuple[dict[str, Any] | None, str]:
    why = ""
    for _ in range(1 + RETRIES):
        started = time.monotonic()
        try:
            llm = get_llm()
            with measured.call() if measured is not None else nullcontext():
                raw = await llm.ask("shopper", system, user, schema, timeout=ASK_TIMEOUT, model=model)
            row = method.parse(raw, order, asked)
            row["sec"] = round(time.monotonic() - started, 1)
            return row, ""
        except (LLMError, method.BadAnswer) as e:
            why = type(e).__name__
    return None, why


async def _run(run_id: str, measured: usage.RunUsage | None = None) -> None:
    meta = store.load_meta(run_id)
    try:
        if not meta or meta["status"] != "running":
            return
        if measured is None and meta.get("usage_version"):
            measured = usage.begin(run_id)
        shelf_v = method.shelf_v()
        if meta.get("shelf_v") != shelf_v and not os.getenv("AX_SHOPPER_ROUND"):
            saved_round = _saved_round(meta)
            if saved_round != method.prompt_round():
                shelf_v = method.shelf_v(saved_round)
        if meta.get("shelf_v") != shelf_v:
            meta.update(status="failed", error="테스트를 시작했을 때와 매대가 달라졌어요", updated_at=_now())
            store.save_meta(meta)
            return
        plan = _plan(meta)
        visits = plan.visits[: int(meta["total"])]
        model = meta["model"]
        rows = store.answers(run_id)
        got: dict[str, dict[str, dict]] = {}
        skipped = set()
        for r in rows:
            if r.get("skip"):
                skipped.add(r.get("visit"))
            elif r.get("visit"):
                got.setdefault(r["visit"], {})[r.get("cond", "")] = r
        base_cache = store.baselines(shelf_v, model)
        sem = asyncio.Semaphore(workers())

        def write(visit: dict[str, Any], cond: str, row: dict[str, Any], **extra: Any) -> dict[str, Any]:
            out = {"visit": visit["방문"], "cond": cond, "uuid": visit["uuid"], "occasion": visit["상황 번호"],
                   **row, **extra, "at": _now()}
            store.append_answer(run_id, out)
            return out

        def skip(v: str, why: str) -> None:
            skipped.add(v)
            store.append_answer(run_id, {"visit": v, "skip": True, "why": why[:200], "at": _now()})

        if "participants" in meta:
            available = {v["방문"] for v in visits}
            for p in meta["participants"]:
                v = p["visit"]
                if v not in available and v not in skipped and method.CONCEPT not in got.get(v, {}):
                    skip(v, "손님 기록 없음")

        async def one(visit: dict[str, Any], cond: str) -> None:
            v = visit["방문"]
            if v in skipped or cond in got.get(v, {}):
                return
            try:
                async with sem:
                    row, why = await _ask(plan, visit, cond, model, measured)
                if row is None:
                    if cond == method.CONCEPT:  # 컨셉이 없는 매대의 답만 없으면 "전에 집던 것"에서만 빠진다
                        skip(v, why)
                    return
                got.setdefault(v, {})[cond] = write(visit, cond, row)
                if cond == method.BASELINE:
                    base = {"uuid": visit["uuid"], "occasion": method.baseline_occasion(visit), **row}
                    base_cache[(visit["uuid"], base["occasion"])] = base
                    store.append_baseline(shelf_v, model, base)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — 한 손님의 뜻밖의 오류는 그 손님만 뺀다
                if cond == method.CONCEPT:
                    skip(v, type(e).__name__)

        async def everyone() -> None:
            for visit in visits:  # 저장해 둔 답은 묻지 않고 바로 쓴다
                v = visit["방문"]
                cached = base_cache.get((visit["uuid"], method.baseline_occasion(visit)))
                if v in skipped or method.BASELINE in got.get(v, {}) or cached is None:
                    continue
                keep = {k: cached[k] for k in ("number", "product", "needs", "other", "sentence", "sec") if k in cached}
                got.setdefault(v, {})[method.BASELINE] = write(visit, method.BASELINE, keep, reused=True)
            await asyncio.gather(*(one(v, method.CONCEPT) for v in visits))
            await asyncio.gather(*(one(v, method.BASELINE) for v in visits))

        if meta.get("mode") == "improve" or meta.get("change"):
            async with _improve_lock(meta.get("chat_id") or ""):
                print(f"[shelf] {run_id} 시작(개선안): {len(visits)}명, 동시에 {workers()}명, 모델 {model}",
                      file=sys.stderr, flush=True)
                await everyone()
        else:
            print(f"[shelf] {run_id} 시작: {len(visits)}명, 동시에 {workers()}명, 모델 {model}", file=sys.stderr, flush=True)
            await everyone()
        fresh = store.load_meta(run_id) or meta
        if fresh.get("status") == "running":
            fresh["status"] = "done"
            fresh["updated_at"] = _now()
            store.save_meta(fresh)
        print(f"[shelf] {run_id} 끝", file=sys.stderr, flush=True)
    except asyncio.CancelledError:
        # 멈춤(stop이 상태를 적는다)이나 서버가 꺼짐(상태를 running으로 두어 다시 띄우면 이어서 돈다)
        raise
    except Exception as e:  # noqa: BLE001 — 뜻밖의 오류는 실패로 적는다
        fresh = store.load_meta(run_id) or meta
        fresh["status"] = "failed"
        fresh["error"] = type(e).__name__
        fresh["updated_at"] = _now()
        store.save_meta(fresh)
        print(f"[shelf] {run_id} 실패: {type(e).__name__}", file=sys.stderr, flush=True)
    finally:
        if measured is not None:
            measured.finish()
        if TASKS.get(run_id) is asyncio.current_task():
            TASKS.pop(run_id, None)


# ---------- 읽기 ----------


def view(run_id: str) -> dict[str, Any] | None:
    """GET /api/runs/{id}의 모양. 상태가 running인데 도는 작업이 없으면 이어서 돌린다."""
    meta = store.load_meta(run_id)
    if meta is None:
        return None
    ensure_running(run_id)
    meta = store.load_meta(run_id) or meta
    rows = store.answers(run_id)
    pairs, skipped = result.concept_visits(rows)
    t = meta["target"]
    code = meta.get("occasion_code")
    people = {p.uuid: p for p in method.people(t.get("age"), t.get("sex"))} if pairs else {}
    last = max((r.get("at") or "" for r in rows), default="")
    c = meta["concept"]
    out = {
        "id": meta["id"], "status": meta["status"],
        "concept": {"id": c["id"], "name": c["name"], "pack": c["pack"], "container": c["container"],
                    "volume": c["volume"], "price": c["price"], "promo": c.get("promo")},
        "who": {"label": who_label(t.get("age"), t.get("sex")),
                "occasion": show_occasion(method.occasions().get(code, {}).get("상황")) if code else None,
                "occasion_share": occasion_share(t.get("age"), t.get("sex"), code)},
        "asked": len(pairs), "total": int(meta["total"]), "requested": int(meta.get("requested", meta["total"])),
        "skipped": len(skipped), "placement": meta.get("placement"),
        "started_at": meta["started_at"], "updated_at": max(meta.get("updated_at") or "", last),
        "model": meta["model"],
        "result": result.summarize(meta, rows, people),
    }
    if meta.get("target_basis") is not None:
        out["target_basis"] = meta["target_basis"]
    if "visit_months" in meta:
        out["visit_months"] = meta["visit_months"]
    if meta.get("usage_version"):
        out["usage"] = usage.view(run_id)
    if meta.get("mode") == "explore":
        out["explore"] = explore.summarize(meta, pairs)
    if meta["status"] == "running":  # 기다리는 화면(11-25). 끝난 테스트에는 없다
        from shelftest import waiting
        out["waiting"] = waiting.view(meta, rows, pairs, people, out.get("explore"))
    if (brief := __import__("agent.result_brief", fromlist=["for_view"]).for_view(out, meta, rows, people)) is not None:
        out["brief"] = brief  # 지시서 32: 결과 카드 맨 위의 요약 구역
    return out
