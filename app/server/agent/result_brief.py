"""테스트 결과의 요약 구역(지시서 32의 A): 알게 된 것 한 문장, 근거 세 줄, 다음 행동(많아야 셋).

- 모델을 부르지 않는다. 숫자는 결과(shelftest.result.summarize)와 쌓인 답에서, 글은 agent/phrases.py의 brief_*·act_*에서.
- 규칙과 문턱값은 이 파일의 상수에 있다. 결과 보고서의 권고(agent/review.py)도 여기의 문턱값과 ahead()를 쓴다.
- 다음 행동의 버튼은 지금 있는 동작으로 이어진다. 버튼마다 do가 있다:
  {"say": 말, "to": 묶음 id, "ids": [...]}(대화에서 그 버튼을 누른 것과 같다) 또는 {"stage": "concept"}(작업대의 단계 이동).
  대화에 같은 버튼(같은 id)이 이미 있으면 그 묶음의 id와 말을 쓴다.
- 행동은 RULES의 차례로 모은다(collect_actions). 다른 묶음은 RULES에 (Ctx) → Action | None 함수를 한 줄 더한다.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from agent import phrases as P
from tools.occasion_display import show as show_occasion

# ---------- 문턱값(초안) ----------

PRICE = "가격이 비쌈"
PRICE_TOP = 3  # 걸린 점에서 가격이 이 순위 안이면
PRICE_SHARE = 0.10  # 또는 지나친 가상 소비자의 이 비율 이상이 가격을 들면 가격 변경안을 권한다
OWN_SHARE = 0.30  # 고른 가상 소비자 가운데 자사 제품을 고르던 비율이 이 이상이면 그 가상 소비자를 인터뷰
LOWER_HALF = 0.50  # 컨셉보다 많이 고른 기존 제품이 이 비율 이상이면(아래 절반) 컨셉 보드로
MAX_RULE_ACTIONS = 2  # 규칙에서 고른 행동의 수. 결과 보고서는 늘 마지막에 하나 더(모두 많아야 셋)

# 결과 보고서의 권고(지시서 32의 B-1). review.py가 쓴다
RESEARCH_TOP = 0.10  # 컨셉보다 많이 고른 기존 제품이 기존 제품의 이 비율 미만이면 실제 소비자 조사 진행
RETEST_TOP = 0.50  # 이 비율 미만이면 수정 후 재테스트, 이상이거나 0명이면 보류
CANNIBAL_SHARE = 0.50  # 고른 가상 소비자의 이 비율 이상이 자사 제품을 고르던 사람이면 겹침 확인
CANNIBAL_MIN = 4  # 위를 따지는 최소 선택 수

# 대화의 버튼 id(agent/machine.py와 같다. machine을 불러오지 않으려고 글자로 둔다)
IMPROVE, IMPROVE_COMPARE, REPORT = "improve", "improve-compare", "report"
INTERVIEW_TO = P.INTERVIEW_TO
BRIEF_TO = "result-brief"  # 대화에 같은 버튼이 없을 때의 묶음 id


# ---------- 계산 ----------


def ahead(res: dict[str, Any]) -> tuple[int, int] | None:
    """(컨셉보다 많이 고른 기존 제품 수, 기존 제품 수). 고른 사람이 없으면 None."""
    existing = max(1, int(res.get("products") or 1) - 1)
    if not res.get("picked") or not res.get("rank"):
        return None
    return int(res["rank"]) - 1, existing


def ahead_share(res: dict[str, Any]) -> float | None:
    a = ahead(res)
    return None if a is None else a[0] / a[1]


def lower_half(res: dict[str, Any]) -> bool:
    share = ahead_share(res)
    return share is None or share >= LOWER_HALF


def people_range(res: dict[str, Any]) -> tuple[int, int]:
    """윌슨 구간(%)을 사람 수로. 화면의 폭 막대와 같은 셈이다."""
    n = int(res.get("n") or 0)
    return math.floor(float(res.get("low") or 0) * n / 100), math.ceil(float(res.get("high") or 0) * n / 100)


def inflow(res: dict[str, Any]) -> dict[str, Any]:
    """고른 가상 소비자가 컨셉이 없는 매대에서 고르던 것. known은 그것을 아는 수(pending 제외)."""
    f = res.get("from") or {}
    own_rows, rival_rows = f.get("own") or [], f.get("rival") or []
    own = sum(x["count"] for x in own_rows)
    rival = sum(x["count"] for x in rival_rows)
    none = int(f.get("none") or 0)
    return {"own": own, "rival": rival, "none": none, "pending": int(f.get("pending") or 0),
            "known": own + rival + none,
            "own_top": (own_rows[0]["name"], own_rows[0]["count"]) if own_rows else None,
            "rival_top": (rival_rows[0]["name"], rival_rows[0]["count"]) if rival_rows else None}


OCCASION_MIN = 10  # 음용 상황별 선택률은 이만큼 답한 상황만 견준다(화면의 차트와 같다)


def top_occasion(res: dict[str, Any]) -> str | None:
    """고른 비율이 가장 높은 음용 상황(OCCASION_MIN명 이상 답한 것만, 같으면 답한 사람이 많은 것). 고른 사람이 없으면 None."""
    rows = [o for o in res.get("by_occasion") or [] if int(o.get("n") or 0) >= OCCASION_MIN and o.get("picked")]
    if not rows:
        return None
    return show_occasion(max(rows, key=lambda o: (o["picked"] / o["n"], o["n"]))["occasion"])  # 옛 실행의 결과에 남은 이름도


def top_barrier(res: dict[str, Any]) -> str | None:
    bars = res.get("barriers") or []
    return bars[0]["label"] if bars else None


@dataclass
class Visitor:
    visit: str
    who: str
    barriers: list[str]
    picked: bool
    before_own: bool | None  # 컨셉이 없는 매대에서 자사 제품을 골랐나(답이 아직 없으면 None)


@dataclass
class Ctx:
    """행동을 고르는 데 쓰는 것. view는 GET /api/runs/{id}의 모양(brief 없이)."""
    run_id: str
    view: dict[str, Any]
    res: dict[str, Any]
    visitors: list[Visitor] = field(default_factory=list)
    top_existing: tuple[str, int] | None = None
    improve: dict[str, Any] | None = None  # 이 테스트를 처음 안으로 둔 개선안 표(대화의 노트)
    offers: dict[str, tuple[str, str]] = field(default_factory=dict)  # 버튼 id → (묶음 id, 말)
    group: str | None = None  # 타깃의 표기(탐색과 같은 "40~49세 남성"). 없으면 view의 이름표에서
    top: list[dict[str, Any]] = field(default_factory=list)  # 매대에서 가장 많이 고른 제품(shelf_top)
    eta_s: float | None = None  # 도는 중이면 끝나기까지 남은 초(eta_seconds)

    @property
    def passed(self) -> int:
        return int(self.res["n"]) - int(self.res["picked"])

    @property
    def tried_kinds(self) -> set[str]:
        """이미 돌린 개선안의 종류."""
        items = (self.improve or {}).get("items") or []
        return {it.get("kind") or "" for it in items if it.get("run_id")}


def scan(meta: dict[str, Any], rows: list[dict[str, Any]], people: dict[str, Any]) -> tuple[list[Visitor], tuple[str, int] | None]:
    """쌓인 답에서: 가상 소비자마다(방문 차례대로)의 고름과 걸린 점, 기존 제품 가운데 가장 많이 고른 것."""
    from shelftest import catalog, method, result

    pairs, _ = result.concept_visits(rows)
    line = meta["line"]
    products = meta.get("shelf_products")
    if products is None:
        products = [(p.key, p.name, p.is_own) for p in catalog.public() if p.shelf == method.SHELF]
    info = {name: (shown, ours) for name, shown, ours in products}
    out = []
    for b, c in pairs:
        person = people.get(c.get("uuid", ""))
        before_own = None if b is None else bool(info.get(b["product"], ("", False))[1])
        out.append(Visitor(visit=c["visit"], who=method.who_line(person) if person else "",
                           barriers=list(c.get("barriers") or []), picked=c["product"] == line, before_own=before_own))
    counts = Counter(c["product"] for _, c in pairs if c["product"] not in (line, method.NO_PURCHASE))
    top = None
    if counts:
        name, k = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        top = (info[name][0] if name in info else method.display(name), k)
    return out, top


def offers_of(rec: dict[str, Any] | None) -> dict[str, tuple[str, str]]:
    """대화에 나온 버튼: id → (그 묶음의 id, 말). 같은 id면 나중 것."""
    out: dict[str, tuple[str, str]] = {}
    for m in (rec or {}).get("messages") or []:
        for e in m.get("events") or []:
            if e.get("t") == "actions":
                for a in e.get("actions") or []:
                    out[a["id"]] = (e["id"], a["label"])
    return out


# ---------- 다음 행동 ----------

Action = dict[str, Any]


def _say(ctx: Ctx, action_id: str, label: str) -> dict[str, Any]:
    to, said = ctx.offers.get(action_id, (BRIEF_TO, label))
    return {"say": said, "to": to, "ids": [action_id]}


def _group_question(ctx: Ctx, hint: str) -> dict[str, Any]:
    return {"say": P.BTN_ASK_GROUP, "to": P.GROUP_TO, "ids": ["open", ctx.run_id, hint]}


def _barrier_counts(ctx: Ctx) -> list[tuple[str, int]]:
    return [(b["label"], b["count"]) for b in ctx.res.get("barriers") or []]


def rule_weak(ctx: Ctx) -> Action | None:
    if not lower_half(ctx.res):
        return None
    return {"id": "concept-board", "reason": P.ACT_WEAK, "label": P.BTN_CONCEPT_BOARD, "do": {"stage": "concept"}}


def rule_price(ctx: Ctx) -> Action | None:
    bars = _barrier_counts(ctx)
    i = next((k for k, (label, _) in enumerate(bars) if label == PRICE), None)
    if i is None:
        return None
    count = bars[i][1]
    if not (i < PRICE_TOP or (ctx.passed and count >= PRICE_SHARE * ctx.passed)):
        return None
    if "price" in ctx.tried_kinds:  # 이미 돌린 가격 변경안은 다시 권하지 않고 그 결과로 잇는다
        return {"id": IMPROVE_COMPARE, "reason": P.ACT_PRICE_DONE, "label": P.BTN_IMPROVE_COMPARE,
                "do": _say(ctx, IMPROVE_COMPARE, P.BTN_IMPROVE_COMPARE)}
    return {"id": IMPROVE, "reason": P.act_price(count), "label": P.BTN_IMPROVE, "do": _say(ctx, IMPROVE, P.BTN_IMPROVE)}


def rule_top_barrier(ctx: Ctx) -> Action | None:
    bars = _barrier_counts(ctx)
    if not bars or bars[0][0] == PRICE:
        return None
    label, count = bars[0]
    v = next((v for v in ctx.visitors if not v.picked and v.who and label in v.barriers), None)
    if v is None:
        return None
    return {"id": f"interview-barrier/{v.visit}", "reason": P.act_barrier(label, count), "label": P.BTN_ASK_GROUP,
            "do": _group_question(ctx, f"barrier:{label}")}


def rule_own(ctx: Ctx) -> Action | None:
    f = inflow(ctx.res)
    k = int(ctx.res["picked"])
    if not k or not f["known"] or f["own"] < OWN_SHARE * f["known"]:
        return None
    v = next((v for v in ctx.visitors if v.picked and v.who and v.before_own), None)
    if v is None:
        return None
    return {"id": f"interview-own/{v.visit}", "reason": P.act_own(k, f["own"]), "label": P.BTN_ASK_GROUP,
            "do": _group_question(ctx, "own")}


def report_action(ctx: Ctx) -> Action:
    return {"id": REPORT, "reason": None, "label": P.BTN_REPORT, "do": _say(ctx, REPORT, P.BTN_REPORT)}


# 차례대로 맞는 것을 고른다. 다른 묶음(W7의 FGI·FGD 질문 후보 등)은 여기에 함수를 한 줄 더한다
RULES: list[Callable[[Ctx], Action | None]] = [rule_weak, rule_price, rule_top_barrier, rule_own]


def collect_actions(ctx: Ctx) -> list[Action]:
    """규칙에서 맞는 것(많아야 MAX_RULE_ACTIONS개), 늘 마지막에 결과 보고서."""
    out: list[Action] = []
    for rule in RULES:
        if len(out) >= MAX_RULE_ACTIONS:
            break
        a = rule(ctx)
        if a is not None and all(x["id"] != a["id"] for x in out):
            out.append(a)
    return out + [report_action(ctx)]


# ---------- 요약 구역 ----------


def points(ctx: Ctx) -> list[dict[str, Any]]:
    """근거 세 줄: 얼마나, 평소 무엇을 고르던 사람인가, 왜 지나쳤나. 줄마다 숫자 하나, 문장 하나, 작은 막대(없어도 됨)."""
    res = ctx.res
    k, name = int(res["picked"]), ctx.view["concept"]["name"]
    out = []
    bar = [{"label": name, "n": k, "self": True}]
    if ctx.top_existing:
        bar.append({"label": ctx.top_existing[0], "n": ctx.top_existing[1], "self": False})
    out.append({"key": "how", "value": P.brief_value(k), "text": P.brief_how(res.get("rank"), res["products"], ctx.top_existing),
                "bar": bar, "of": max(x["n"] for x in bar)})
    f = inflow(res)
    if k and (f["known"] or f["pending"]):
        out.append({"key": "from", "value": P.brief_value(f["rival"]),
                    "text": P.brief_from(k, f["rival"], f["own"], f["none"], f["own_top"], f["pending"]),
                    "bar": [{"label": P.BRIEF_FROM_LABELS[x], "n": f[x], "self": False} for x in ("rival", "own", "none")],
                    "of": k, "stacked": True})
    bars = _barrier_counts(ctx)[:2]
    if bars and ctx.passed:
        out.append({"key": "why", "value": P.brief_value(bars[0][1]), "text": P.brief_why(ctx.passed, bars),
                    "bar": [{"label": label, "n": c, "self": False} for label, c in bars], "of": ctx.passed})
    return out


def target_label(meta: dict[str, Any]) -> str | None:
    """타깃의 표기를 탐색 화면과 같게("40~49세 남성"). 연령도 성별도 없으면 None(지금의 이름표를 쓴다)."""
    from agent.explore import _label  # explore → runner → 여기로 도는 불러오기를 피한다

    t = meta.get("target") or {}
    return _label(t.get("age"), t.get("sex")) if t.get("age") or t.get("sex") else None


def brief(ctx: Ctx) -> dict[str, Any]:
    res = ctx.res
    group = ctx.group or ctx.view["who"]["label"].removesuffix(" 손님").strip()
    lo, hi = people_range(res)
    running = ctx.view.get("status") == "running"
    out = {
        "headline": P.brief_headline(group, int(res["n"]), int(res["picked"]), ctx.view["concept"]["name"],
                                     res.get("rank"), int(res["products"]), running=running),
        "range": P.brief_range(lo, hi),
        "group": group,
        "points": points(ctx),
        "actions": collect_actions(ctx),
    }
    if ctx.top:
        out["top"] = ctx.top
    if running:
        out["eta_s"] = ctx.eta_s
    return out


# ---------- 남은 시간, 매대의 위쪽 ----------

ETA_MIN_ANSWERS = 10  # 이만큼 새로 물은 답이 쌓여야 남은 시간을 셈한다
TOP_SHOWN = 6  # 결과 화면의 "매대에서의 자리"에 보이는 제품 수


def _at(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def eta_seconds(meta: dict[str, Any], rows: list[dict[str, Any]], now: datetime | None = None) -> float | None:
    """도는 테스트가 끝나기까지 남은 초. 두 매대(컨셉을 올린 매대, 없는 매대)의 답을 모두 센다.
    빠르기는 시작부터 지금까지 새로 물은 답의 수(저장해 둔 답을 다시 쓴 것은 빼고)로 잰다. 셀 수 없으면 None."""
    if meta.get("status") != "running":
        return None
    started = _at(meta.get("started_at"))
    if started is None:
        return None
    now = now or datetime.now(timezone.utc)
    answers = [r for r in rows if not r.get("skip") and r.get("cond")]
    fresh = [r for r in answers if not r.get("reused")]
    skipped = {r.get("visit") for r in rows if r.get("skip")}
    need = 2 * max(0, int(meta.get("total") or 0) - len(skipped))
    left = need - len(answers)
    if left <= 0:
        return 0.0
    spent = (now - started).total_seconds()
    if len(fresh) < ETA_MIN_ANSWERS or spent <= 0:
        return None
    return round(left * spent / len(fresh), 1)


def shelf_top(meta: dict[str, Any], rows: list[dict[str, Any]], res: dict[str, Any]) -> list[dict[str, Any]]:
    """컨셉을 올린 매대에서 가장 많이 고른 제품(TOP_SHOWN개, 아무것도 안 삼은 빼고). 컨셉이 그 안에 없으면 끝에 붙인다."""
    from shelftest import catalog, method, result

    pairs, _ = result.concept_visits(rows)
    line = meta["line"]
    products = meta.get("shelf_products")
    if products is None:
        products = [(p.key, p.name, p.is_own) for p in catalog.public() if p.shelf == method.SHELF]
    info = {name: (shown, ours) for name, shown, ours in products}
    counts = Counter(c["product"] for _, c in pairs if c["product"] != method.NO_PURCHASE)

    def row(name: str) -> dict[str, Any]:
        is_self = name == line
        shown = meta["concept"]["name"] if is_self else (info[name][0] if name in info else method.display(name))
        return {"name": shown, "picked": counts.get(name, 0), "self": is_self,
                "ours": is_self or bool(info.get(name, ("", False))[1])}

    ranked = sorted(counts, key=lambda x: (-counts[x], x != line, x))
    top = ranked[:TOP_SHOWN]
    if line not in top and res.get("picked"):
        top.append(line)
    return [row(x) for x in top]


def for_view(view: dict[str, Any], meta: dict[str, Any], rows: list[dict[str, Any]],
             people: dict[str, Any]) -> dict[str, Any] | None:
    """runner.view가 부른다. 결과가 없거나 탐색·개선안의 테스트면 None(그 카드에는 요약 구역이 없다)."""
    res = view.get("result")
    if not res or meta.get("mode") in ("explore", "improve") or meta.get("change"):
        return None
    rec = None
    if meta.get("chat_id"):
        import chats

        rec = chats.load(meta["chat_id"])
    imp = ((rec or {}).get("note") or {}).get("improve")
    imp = imp if isinstance(imp, dict) and imp.get("base_run") == view["id"] else None
    visitors, top = scan(meta, rows, people)
    ctx = Ctx(run_id=view["id"], view=view, res=res, visitors=visitors, top_existing=top, improve=imp,
              offers=offers_of(rec), group=target_label(meta), top=shelf_top(meta, rows, res),
              eta_s=eta_seconds(meta, rows))
    return brief(ctx)
