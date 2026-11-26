"""매대 결과와 근거에서 조건 하나를 바꾼 안을 제안하고, 기획자가 말한 변경을 읽는다."""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from random import Random
from statistics import median, quantiles
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.steps import BANNED as STEP_BANNED
from agent.steps import VOICE, check_copy
from llm.base import LLMError, get_llm
from tools import shelf
from tools.shelf_items import FEATURE_LABELS, carbonation, concept_features

TIMEOUT = 90.0
KINDS = ["price", "pack", "name", "promo", "flavor", "form", "container", "appeal", "volume"]
PROMOS = ["1+1", "2+1", "없음"]
CONTAINERS = ["캔", "페트", "병", "팩"]
CHANGE_CONTAINERS = [*CONTAINERS, "슬림캔", "유리병", "파우치"]
SAME = "그대로"
MAX_ITEMS = 3
REASON_MAX = 70
DIGITS = re.compile(r"\d[\d,]*")
REASON_BANNED = re.compile(r"자료|기록|데이터|근거|확률|퍼센트|%")
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass
class Base:
    """처음 안(테스트에 올린 값)."""
    name: str
    container: str
    volume: int
    price: int
    promo: str | None = None
    features: dict[str, str] = field(default_factory=dict)

    @classmethod
    def of(cls, concept: dict[str, Any]) -> "Base":
        return cls(concept["name"], concept["container"], int(concept["volume"]), int(concept["price"]),
                   concept.get("promo") or None, concept_features(concept))


def won(n: int) -> str:
    return f"{n:,}원"


def pack(container: str, volume: int) -> str:
    return f"{volume}ml {container}"


def applied(base: Base, values: dict[str, Any]) -> Base:
    promo = values.get("promo", base.promo)
    return Base(values.get("name") or base.name, values.get("container") or base.container,
                int(values.get("volume") or base.volume), int(values.get("price") or base.price),
                None if promo in (None, "", "없음", NO_PROMO) else promo,
                {**base.features, **{key: values[key] for key in FEATURE_LABELS if values.get(key)}})


def change_text(base: Base, values: dict[str, Any]) -> str:
    """"가격 2,200원 → 1,800원", 여럿이면 쉼표로 잇는다."""
    new = applied(base, values)
    parts = []
    if new.price != base.price:
        parts.append(f"가격 {won(base.price)} → {won(new.price)}")
    if (new.container, new.volume) != (base.container, base.volume):
        parts.append(f"용기와 용량 {pack(base.container, base.volume)} → {pack(new.container, new.volume)}")
    if new.name != base.name:
        parts.append(f"이름 {base.name} → {new.name}")
    if (new.promo or None) != (base.promo or None):
        parts.append(f"{'행사 ' + base.promo if base.promo else NO_PROMO} → {new.promo or '없음'}")
    for key, label in FEATURE_LABELS.items():
        if key in new.features and new.features[key] != base.features.get(key):
            parts.append(f"{label} {_feature_value(base, key)} → {_feature_value(new, key)}")
    return ", ".join(parts)


# ---------- 안의 이름과 바꾼 값(지시서 19. 화면의 타일과 칠성이의 말, 결과 보고서가 같은 이름을 쓴다) ----------

BASE_NAME = "기존안"
NO_PROMO = "행사 없음"
KIND_NAMES = {"price": "가격 변경안", "name": "제품명 변경안", "pack": "용기·용량 변경안", "promo": "행사 변경안",
              "container": "용기 변경안", "volume": "용량 변경안",
              **{key: f"{label} 변경안" for key, label in FEATURE_LABELS.items()}}


def _feature_value(base: Base, key: str) -> str:
    value = base.features.get(key, "표기 없음")
    return f"탄산 {value}" if key == "form" and value in ("약함", "보통", "강함") else value


def kind_of(values: dict[str, Any]) -> str:
    """바꾼 것의 종류. 여럿을 바꿨으면(기획자가 직접 말한 안) 가격, 용기와 용량, 이름, 행사의 차례로 앞의 것."""
    if "price" in values:
        return "price"
    if "container" in values and "volume" in values:
        return "pack"
    if "container" in values:
        return "container"
    if "volume" in values:
        return "volume"
    if "name" in values:
        return "name"
    return next((key for key in FEATURE_LABELS if key in values), "promo")


def before_after(base: Base, values: dict[str, Any]) -> tuple[str, str]:
    """타일에 그리는 앞뒤 값. 여럿을 바꿨으면 쉼표로 잇는다. ("2,200원", "1,800원")"""
    new = applied(base, values)
    pairs: list[tuple[str, str]] = []
    if new.price != base.price:
        pairs.append((won(base.price), won(new.price)))
    if (new.container, new.volume) != (base.container, base.volume):
        pairs.append((pack(base.container, base.volume), pack(new.container, new.volume)))
    if new.name != base.name:
        pairs.append((base.name, new.name))
    if (new.promo or None) != (base.promo or None):
        pairs.append((base.promo or NO_PROMO, new.promo or NO_PROMO))
    pairs += [(_feature_value(base, key), _feature_value(new, key)) for key in FEATURE_LABELS
              if key in new.features and new.features[key] != base.features.get(key)]
    old_parts, new_parts = [a for a, _ in pairs], [b for _, b in pairs]
    return ", ".join(old_parts), ", ".join(new_parts)


def describe(base: Base, values: dict[str, Any]) -> dict[str, Any]:
    """안 한 줄의 글: kind, before, after, change."""
    before, after = before_after(base, values)
    return {"kind": kind_of(values), "before": before, "after": after, "change": change_text(base, values)}


def plan_name(items: list[dict[str, Any]], item: dict[str, Any] | None) -> str:
    """안의 이름: 처음 안(None)은 "기존안", 고친 안은 "가격 변경안"처럼 바꾼 것으로. 같은 종류가 둘이면 뒤의 것에 숫자.
    화면(web/src/components/workbench/ImproveCard.tsx의 planName)과 같은 규칙이다."""
    if item is None:
        return BASE_NAME
    kind = item.get("kind") or kind_of(item.get("values") or {})
    same = [it["id"] for it in items if (it.get("kind") or kind_of(it.get("values") or {})) == kind]
    k = same.index(item["id"]) if item["id"] in same else 0
    name = KIND_NAMES.get(kind, KIND_NAMES["promo"])
    return name if k == 0 else f"{name} {k + 1}"


def diff(base: Base, values: dict[str, Any]) -> dict[str, Any]:
    """테스트에 넘기는 change: 처음 안과 다른 것만."""
    new = applied(base, values)
    out: dict[str, Any] = {}
    if new.price != base.price:
        out["price"] = new.price
    if new.container != base.container:
        out["container"] = new.container
    if new.volume != base.volume:
        out["volume"] = new.volume
    if new.name != base.name:
        out["name"] = new.name
    if (new.promo or None) != (base.promo or None):
        out["promo"] = new.promo or "없음"
    out.update({key: new.features[key] for key in FEATURE_LABELS
                if key in new.features and new.features[key] != base.features.get(key)})
    return out


def matches_change(original: dict[str, Any], changed: dict[str, Any], values: dict[str, Any]) -> bool:
    """보드에 반영할 값이 실제로 돌린 조건과 같은지 확인한다."""
    base = Base.of(original)
    return bool(diff(base, values)) and applied(base, values) == Base.of(changed)


def update_board(board: dict[str, Any], original: dict[str, Any], changed: dict[str, Any],
                 values: dict[str, Any]) -> bool:
    """현재 보드와 테스트의 원래 안이 같은 상태에서 승인된 조건을 반영한다."""
    base, tested = Base.of(original), Base.of(changed)
    b_price = re.fullmatch(r"([\d,]+)\s*원?", str(board.get("price") or "").strip())
    board_features = concept_features(board)
    if (
        b_price is None or int(b_price[1].replace(",", "")) != base.price
        or board.get("name") != base.name or board.get("_container") != base.container
        or board.get("_volume") != base.volume or (board.get("_promo") or None) != base.promo
        or any(board_features.get(key) != value for key, value in base.features.items() if key in FEATURE_LABELS)
    ):
        return False

    highlights = []
    if "price" in values:
        board.update(price=won(tested.price), _price_by="planner")
        highlights.append("price")
    if "name" in values:
        board["name"] = tested.name
        highlights.append("name")
    if values.keys() & {"container", "volume"}:
        board.update(_container=tested.container, _volume=tested.volume, pack=pack(tested.container, tested.volume))
        highlights.append("pack")
    if "flavor" in values:
        board["_flavor"] = tested.features["flavor"]
        highlights.append("flavor")
    if "appeal" in values:
        board["_appeal"] = board["headline"] = tested.features["appeal"]
        highlights.append("headline")
    if "form" in values:
        form = tested.features["form"]
        board["_form"] = form
        if carbonation(form) is not None:
            board["_carb"] = form
            highlights.append("carbonation")
        else:
            previous = board.get("_form_point")
            board["_form_point"] = form
            board["points"] = [p for p in board.get("points", []) if p != previous] + [form]
            highlights.append("points")
    if "promo" in values:
        board["_promo"] = tested.promo
        prior = board.get("_promotion_point")
        point = f"{tested.promo} 행사" if tested.promo else NO_PROMO
        board["_promotion_point"] = point
        board["points"] = [p for p in board.get("points", []) if p != prior] + [point]
        highlights.append("points")
    board["changed"] = highlights
    return True


# ---------- 값의 검사 ----------


def check_values(base: Base, values: dict[str, Any], *, price_step: bool = False) -> list[str]:
    """바꾼 값이 매대에 있을 법한가. values는 diff()의 모양."""
    why = []
    if not values:
        return ["바꾼 것이 없어요"]
    if values.keys() - {"price", "volume", "container", "promo", "name", *FEATURE_LABELS}:
        why.append("바꿀 수 없는 조건이에요")
    if "price" in values:
        p = values["price"]
        if type(p) is not int or (p % 100 and not price_step) or not 500 <= p <= 10000:
            why.append(f"가격은 500~10,000원 사이의 100원 단위로: {p}")
    if "container" in values and values["container"] not in CHANGE_CONTAINERS:
        why.append(f"용기는 {', '.join(CHANGE_CONTAINERS)} 가운데 하나: {values['container']}")
    if "volume" in values:
        v = values["volume"]
        if not isinstance(v, int) or v % 5 or not 100 <= v <= 2000:
            why.append(f"용량은 100~2,000ml 사이의 5ml 단위로(355ml 같은 매대의 용량): {v}")
    if "promo" in values and values["promo"] not in PROMOS:
        why.append(f"행사는 1+1, 2+1, 없음 가운데 하나: {values['promo']}")
    if "name" in values:
        name = str(values["name"]).strip()
        if not name or len(name) > 24:
            why.append("이름은 24자 안으로")
        try:
            check_copy({"name": name}, True, shelf.brand_words(), allowed=base.name)
        except ValueError as e:
            why.append(str(e))
        if STEP_BANNED.search(name):
            why.append(f"쓰지 않는 말: {STEP_BANNED.search(name).group(0)}")
    for key, label in FEATURE_LABELS.items():
        if key in values:
            value = values[key]
            if not isinstance(value, str) or not value.strip() or len(value) > 70 or "\n" in value:
                why.append(f"{label}은 70자 안의 매대 표기로 적어 주세요")
            elif STEP_BANNED.search(value):
                why.append(f"{label}에 쓰지 않는 말이 있어요")
    return why


def _norm(num: str) -> str:
    return num.replace(",", "")


def check_reason(reason: str, allowed: set[str]) -> list[str]:
    why = []
    t = reason.strip()
    if not t:
        return ["까닭이 비었어요"]
    if len(t) > REASON_MAX:
        why.append(f"까닭은 {REASON_MAX}자 안의 한 문장으로")
    if len([s for s in re.split(r"(?<=[.?!])\s+", t) if s.strip()]) > 1:
        why.append("까닭은 한 문장으로")
    nums = [_norm(x) for x in DIGITS.findall(t)]
    if not nums:
        why.append("까닭에 결과의 숫자를 하나 들어 주세요(예: 가격이 걸린 손님이 9명이라)")
    bad = [x for x in nums if x not in allowed]
    if bad:
        why.append(f"받은 숫자에 없는 숫자: {', '.join(bad)}")
    m = STEP_BANNED.search(t) or REASON_BANNED.search(t)
    if m:
        why.append(f"쓰지 않는 말: {m.group(0)}")
    if "?" in t or "!" in t:
        why.append("물음표나 느낌표 없이")
    return why


# ---------- 결과에서 넘기는 사실 ----------


def facts(base: Base, res: dict[str, Any], who: str) -> tuple[list[str], set[str]]:
    """모델에게 넘기는 결과의 사실과 까닭에 써도 되는 숫자."""
    lines = [f"컨셉: {base.name} / {pack(base.container, base.volume)} / {won(base.price)} / 행사 {base.promo or '없음'}",
             f"물은 손님: {who} {res['n']}명",
             f"구매한 손님: {res['picked']}명" + (f" (편의점 음료 매대 {res['products']}개 제품 중 구매 순위 {res['rank']}위)"
                                                if res.get("rank") else "")]
    barriers = res.get("barriers") or []
    if barriers:
        lines.append("걸린 점(많은 순): " + ", ".join(f"{b['label']} {b['count']}명" for b in barriers))
    views = res.get("views") or []
    if views:
        lines.append("새 제품을 보는 눈: " + ", ".join(f"{v['label']} {v['count']}명" for v in views))
    allowed = {str(res["n"]), str(res["picked"]), str(res.get("products") or ""), str(res.get("rank") or ""),
               str(base.price), str(base.volume)}
    allowed |= {str(b["count"]) for b in barriers} | {str(v["count"]) for v in views}
    allowed |= {"1", "2"}  # 1+1, 2+1
    allowed.discard("")
    return lines, allowed


# ---------- 모델이 안을 낸다 ----------

SYSTEM = VOICE + """

일: 매대 테스트의 결과를 보고, 처음 안에서 한 가지만 바꾼 개선안을 둘이나 셋 낸다. 판단만 한다.
- 바꿀 수 있는 것(kind)은 답 형식에 있다. flavor(맛)는 맛 표현, form(제형)은 제형 표기, appeal(소구점)은 매대 문구만 바꾼다. 성분과 영양 정보는 새로 쓰지 않는다.
- 한 안은 kind 하나만 바꾼다. 다른 칸은 처음 안의 값 그대로 적는다.
- 매대에 있을 법한 값: 가격은 100원 단위, 행사는 1+1 또는 2+1 또는 없음.
- 안끼리 서로 다른 것을 바꾼다. 가장 많이 걸린 점을 줄일 안을 앞에 둔다.
- reason: 왜 이 안인지 한 문장(해요체, 40자 안팎). 받은 결과의 숫자를 하나 든다(예: "가격이 걸린 손님이 9명이라 200원 낮춰 봐요").
  받은 숫자에 없는 숫자를 쓰지 않는다(바꾼 값과 그 차이의 숫자는 써도 된다).
- 다른 회사 제품의 이름을 쓰지 않는다. 매출이나 점유율을 말하지 않는다."""


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Idea(_M):
    kind: str
    price: int = 0
    container: str = ""
    volume_ml: int = 0
    name: str = ""
    promo: str = "없음"
    reason: str = ""
    flavor: str = ""
    form: str = ""
    appeal: str = ""


class Ideas(_M):
    items: list[Idea] = Field(min_length=1, max_length=MAX_ITEMS)


def schema(*, features: bool = False) -> dict[str, Any]:
    kinds = KINDS if features else KINDS[:4]
    item = {"type": "object", "additionalProperties": False,
            "required": ["kind", "price", "container", "volume_ml", "name", "promo", "reason"],
            "properties": {
                "kind": {"type": "string", "enum": kinds, "description": "바꾸는 것 하나"},
                "price": {"type": "integer", "description": "가격(원). price가 아니면 처음 안의 가격"},
                "container": {"type": "string", "enum": CHANGE_CONTAINERS, "description": "용기. pack이나 container가 아니면 처음 안의 용기"},
                "volume_ml": {"type": "integer", "description": "용량(ml). pack이 아니면 처음 안의 용량"},
                "name": {"type": "string", "description": "이름. name이 아니면 처음 안의 이름"},
                "promo": {"type": "string", "enum": PROMOS, "description": "행사. promo가 아니면 처음 안의 행사(없으면 없음)"},
                "reason": {"type": "string", "description": "까닭 한 문장(결과의 숫자를 하나 든다)"},
            }}
    if features:
        for key, label in FEATURE_LABELS.items():
            item["required"].append(key)
            item["properties"][key] = {"type": "string", "description": f"새 {label}. 바꾸지 않으면 빈 문자열"}
    return {"type": "object", "additionalProperties": False, "required": ["items"],
            "properties": {"items": {"type": "array", "minItems": 2, "maxItems": MAX_ITEMS, "items": item}}}


def idea_values(base: Base, it: Idea) -> dict[str, Any]:
    """kind의 칸만 읽는다(한 가지만 바꾼다)."""
    if it.kind == "price":
        return diff(base, {"price": it.price})
    if it.kind == "pack":
        return diff(base, {"container": it.container or base.container, "volume": it.volume_ml or base.volume})
    if it.kind == "container":
        return diff(base, {"container": it.container})
    if it.kind == "volume":
        return diff(base, {"volume": it.volume_ml})
    if it.kind == "name":
        return diff(base, {"name": it.name.strip()})
    if it.kind == "promo":
        return diff(base, {"promo": it.promo})
    if it.kind in FEATURE_LABELS:
        return diff(base, {it.kind: getattr(it, it.kind).strip()})
    return {}


async def _ask(user: str, *, features: bool = False) -> Ideas | None:
    try:
        raw = await get_llm().ask("improve", SYSTEM, user, schema(features=features), timeout=TIMEOUT)
        return Ideas.model_validate(raw)
    except (LLMError, ValidationError, ValueError) as e:
        print(f"[improve] 부르기 실패: {type(e).__name__}", file=sys.stderr, flush=True)
        return None


def _judge(base: Base, it: Idea, allowed: set[str]) -> tuple[dict[str, Any], list[str]]:
    if it.kind not in KINDS:
        return {}, [f"바꿀 수 있는 것이 아니에요: {it.kind}"]
    values = idea_values(base, it)
    why = check_values(base, values)
    if not why and it.kind == "pack" and "container" not in values and "volume" not in values:
        why.append("용기와 용량이 처음 안과 같아요")
    allowed_here = allowed | {_norm(str(v)) for v in values.values() if isinstance(v, int)}
    if "price" in values:
        allowed_here.add(str(abs(values["price"] - base.price)))  # "200원 낮춰"
    if "volume" in values:
        allowed_here.add(str(abs(values["volume"] - base.volume)))
    why += check_reason(it.reason, allowed_here)
    return values, why


async def propose(base: Base, res: dict[str, Any], who: str, shelf_kind: str | None, *,
                  enhanced: bool = False) -> tuple[list[dict[str, Any]], bool]:
    """결과 숫자를 검증하고, 근거로 표시할 실제 집계와 조건을 함께 돌려준다."""
    from agent import improve_suggestions

    lines, allowed = facts(base, res, who)
    if enhanced:
        lines.extend(f"{label} 표기: {_feature_value(base, key)}" for key, label in FEATURE_LABELS.items()
                     if key in base.features)
    user = "테스트 결과\n" + "\n".join(f"- {x}" for x in lines) + "\n\n개선안을 둘이나 셋 낸다."
    grounded = improve_suggestions.grounded(base, res, shelf_kind) if enhanced else []
    covered = {item["kind"] for item in grounded}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def keep(values: dict[str, Any], reason: str) -> None:
        if enhanced and len(values) != 1:
            return
        kind = kind_of(values)
        if kind in covered or (enhanced and kind == "price"):
            return
        key = repr(sorted(values.items()))
        if key in seen or len(out) >= MAX_ITEMS:
            return
        seen.add(key)
        out.append(improve_suggestions.item(base, res, values, reason.strip()))

    ans = await _ask(user, features=enhanced)
    wrong: list[str] = []
    if ans is not None:
        for k, it in enumerate(ans.items):
            values, why = _judge(base, it, allowed)
            if why:
                wrong.append(f"{k + 1}번째 안: " + "; ".join(why))
            else:
                keep(values, it.reason)
    if ans is None or wrong:
        note = ("\n\n앞의 답이 검사에 걸렸다(걸린 안을 고쳐서 다시 낸다. 통과한 안은 그대로 다시 적어도 된다):\n"
                + "\n".join(f"- {w}" for w in wrong)) if wrong else ""
        again = await _ask(user + note, features=enhanced)
        if again is not None:
            for it in again.items:
                values, why = _judge(base, it, allowed)
                if not why:
                    keep(values, it.reason)
        print(f"[improve] 검사에 걸림 {len(wrong)}곳, 다시 씀 → {len(out)}개", file=sys.stderr, flush=True)
    if grounded or out:
        return [*grounded, *out], False
    fallback_res = res
    if enhanced:
        fallback_res = {**res, "barriers": [b for b in res.get("barriers", []) if b["label"] != PRICEY]}
    backup = fallback(base, fallback_res, shelf_kind)
    return [improve_suggestions.item(base, res, backup["values"], backup["reason"])], True


# ---------- 글틀 ----------

FIRST_SEEN, PRICEY, PACK = "처음 보는 제품이라 망설여짐", "가격이 비쌈", "용량이나 용기가 안 맞음"


def common_volume(shelf_kind: str | None, base: Base) -> int | None:
    """매대에서 같은 종류의 가장 흔한 용량(처음 안과 같으면 그다음)."""
    vols = Counter(p.volume for p in shelf.products() if p.kind == shelf_kind and p.volume)
    for v, _ in vols.most_common():
        if v != base.volume and 100 <= v <= 2000 and v % 5 == 0:
            return v
    return None


def fallback(base: Base, res: dict[str, Any], shelf_kind: str | None) -> dict[str, Any]:
    """가장 많이 걸린 점에 맞춘 한 가지: 처음 보는 제품 → 행사 1+1, 가격 → 200원 낮춤, 용량 → 매대에서 가장 흔한 용량.
    셋 다 걸리지 않았으면 행사 1+1."""
    barriers = {b["label"]: b["count"] for b in res.get("barriers") or []}
    order = [b["label"] for b in res.get("barriers") or [] if b["label"] in (FIRST_SEEN, PRICEY, PACK)]
    top = order[0] if order else None
    if top == PRICEY and base.price - 200 >= 500:
        values = {"price": base.price - 200}
        what = "200원 낮춰 봐요"
    elif top == PACK and common_volume(shelf_kind, base):
        v = common_volume(shelf_kind, base)
        values = {"volume": v}
        what = "편의점 매대에서 가장 흔한 용량으로 바꿔 봐요"
    else:
        values = {"promo": "1+1"} if base.promo != "1+1" else {"promo": "2+1"}
        what = f"{values['promo']} 행사를 붙여 봐요"
        top = top if top == FIRST_SEEN else (top or FIRST_SEEN)
    count = barriers.get(top or "", 0)
    reason = (f"'{top}'에 걸린 손님이 {count}명이라 {what}." if count else f"한 가지만 바꿔서 {what}.")  # 임시
    values = diff(base, values)
    return {"values": values, **describe(base, values), "reason": reason}


# ---------- 기획자가 직접 말한 안 ----------

EXTRACT_SYSTEM = VOICE + """

일: 기획자가 매대 테스트에서 바꿔 보자고 한 값을 뽑는다. 판단만 한다.
- 가격(price, 원), 용기(container), 용량(volume_ml), 이름(name), 행사(promo), 맛(flavor), 제형(form), 소구점(appeal) 가운데 기획자가 말한 것만 적는다.
- 말하지 않은 칸: price와 volume_ml은 0, container와 promo는 "그대로", name은 빈 문자열.
- 맛, 제형, 소구점도 말하지 않으면 빈 문자열이다. 탄산을 빼라고 하면 form은 "무탄산".
- "200원 낮춰"처럼 상대로 말하면 처음 안의 값에서 계산해 적는다. 행사를 빼라고 하면 promo는 "없음"."""


class Extracted(_M):
    price: int = 0
    container: str = SAME
    volume_ml: int = 0
    name: str = ""
    promo: str = SAME
    flavor: str = ""
    form: str = ""
    appeal: str = ""


def extract_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False,
            "required": ["price", "container", "volume_ml", "name", "promo", *FEATURE_LABELS],
            "properties": {
                "price": {"type": "integer", "description": "새 가격(원). 말하지 않았으면 0"},
                "container": {"type": "string", "enum": CHANGE_CONTAINERS + [SAME], "description": "새 용기. 말하지 않았으면 그대로"},
                "volume_ml": {"type": "integer", "description": "새 용량(ml). 말하지 않았으면 0"},
                "name": {"type": "string", "description": "새 이름. 말하지 않았으면 빈 문자열"},
                "promo": {"type": "string", "enum": PROMOS + [SAME], "description": "새 행사. 말하지 않았으면 그대로"},
                **{key: {"type": "string", "description": f"새 {label}. 말하지 않았으면 빈 문자열"}
                   for key, label in FEATURE_LABELS.items()},
            }}


async def extract(base: Base, said: str, *, allow_exact_price: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
    """(테스트에 넘기는 change, 걸린 이유). 뽑지 못하면 (None, 이유)."""
    user = (f"처음 안: {base.name} / {pack(base.container, base.volume)} / {won(base.price)} / 행사 {base.promo or '없음'}"
            + "".join(f" / {label} {_feature_value(base, key)}" for key, label in FEATURE_LABELS.items()
                      if key in base.features)
            + f"\n\n기획자의 말: {said}")
    why: list[str] = []
    for k in range(2):
        asked = user if k == 0 or not why else f"{user}\n\n앞의 답이 검사에 걸렸다: {'; '.join(why)}"
        try:
            raw = await get_llm().ask("improve_extract", EXTRACT_SYSTEM, asked, extract_schema(), timeout=60.0)
            e = Extracted.model_validate(raw)
        except (LLMError, ValidationError, ValueError) as err:
            why = [f"부르기 실패: {type(err).__name__}"]
            continue
        candidate = {"price": e.price or None, "container": None if e.container == SAME else e.container,
                     "volume": e.volume_ml or None, "name": e.name.strip() or None,
                     **{key: getattr(e, key).strip() for key in FEATURE_LABELS}}
        if e.promo != SAME:
            candidate["promo"] = e.promo
        # 가짜 응답기를 비롯해 기존 추출기가 비워 두던 명시적인 표현도 같은 값으로 받는다.
        if not candidate["form"] and re.search(r"무탄산|비탄산|탄산(?:을)?\s*(?:빼|없애|제거)", said):
            candidate["form"] = "무탄산"
        if e.promo == SAME and re.search(r"행사(?:를)?\s*(?:빼|없애|제거|없음)", said):
            candidate["promo"] = "없음"
        for key, label in FEATURE_LABELS.items():
            if not candidate[key]:
                prefix = rf"{label}(?:을|를|은|는)?\s*"
                matched = re.search(prefix + r'["“]([^"”]+)["”]', said)
                if not matched:
                    matched = re.search(prefix + r"([^,\n]+?)(?:으?로)\s*(?:바꾸|바꿔|바꾼|변경|수정|해서)", said)
                if matched:
                    candidate[key] = matched[1].strip()
        values = diff(base, candidate)
        why = check_values(base, values, price_step=allow_exact_price)
        if not why:
            return values, []
    return None, why


# ---------- 처음 안과 견주기 ----------


def overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """흔들릴 수 있는 폭(윌슨 95% 구간, %)이 겹치는가."""
    return a["low"] <= b["high"] and b["low"] <= a["high"]


def verdict(base_res: dict[str, Any], res: dict[str, Any]) -> str:
    """unclear(폭이 겹침), more, less. 화면의 표(web/src/components/workbench/ImproveCard.tsx)와 같은 규칙이다."""
    if res.get("paired"):
        return res["paired"]["verdict"]
    if overlaps(base_res, res):
        return "unclear"
    return "more" if res["picked"] / max(1, res["n"]) > base_res["picked"] / max(1, base_res["n"]) else "less"


def next_letter(items: list[dict[str, Any]]) -> str:
    i = len(items)
    return LETTERS[i] if i < len(LETTERS) else f"Z{i}"


# ---------- 밀키스 화채 비교 데모 ----------


def _demo_price_step(base_price: int) -> dict[str, Any]:
    from shelftest import catalog

    products = catalog.current()
    # 결합 매대에 현장 SKU가 하나라도 있어야 제공 자료를 결합한 결과다.
    joined = any(p.sku for p in products)
    rivals = [p for p in products if p.shelf == "음료" and p.kind == "탄산" and p.pack == 1
              and not p.is_own and p.price > 0] if joined else []
    prices = sorted({p.price for p in rivals})
    if len(prices) >= 2:
        gaps = [high - low for low, high in zip(prices, prices[1:])]
        gap = median(gaps)
        # 50원 경계는 올리고, 서로 다른 가격을 비교할 수 있도록 최소 100원으로 한다.
        step = max(100, int((gap + 50) // 100) * 100)
        if step < base_price:
            return {"source": "joined-shelf", "step": step, "medianGap": gap,
                    "rivalCount": len(rivals), "distinctPrices": len(prices)}
    return {"source": "demo", "step": 100}


def _demo_selection(choices: list[bool]) -> dict[str, Any]:
    from shelftest.result import wilson

    n, picked = len(choices), sum(choices)
    low, high = wilson(picked, n)
    return {"n": n, "picked": picked, "rate": round(100 * picked / n, 1), "interval": [low, high]}


def _demo_paired(original: list[bool], changed: list[bool]) -> dict[str, Any]:
    from scipy.stats import multinomial

    differences = [int(after) - int(before) for before, after in zip(original, changed, strict=True)]
    gained, lost, n = differences.count(1), differences.count(-1), len(differences)
    # 같은 손님의 두 응답을 한 쌍으로 복원 추출한다. 세 범주의 빈도만 필요하다.
    draws = multinomial.rvs(n, [gained / n, lost / n, (n - gained - lost) / n],
                            size=4000, random_state=279)
    low, *_, high = quantiles((draws[:, 0] - draws[:, 1]).tolist(), n=40, method="inclusive")

    def as_pp(count: float) -> float:
        return round(100 * count / n, 1)

    return {"gained": gained, "lost": lost, "difference": as_pp(gained - lost),
            "interval": [as_pp(low), as_pp(high)]}


def demo_comparison() -> dict[str, Any]:
    """같은 합성 패널의 선택 규칙을 원래 안과 조건 하나를 바꾼 안에 적용한다."""
    from onsite.concepts import CONCEPTS

    concept = next(item for item in CONCEPTS if item["id"] == "milkis-hwachae")
    pack_info = next(item for item in concept["variants"] if item["pack"] == "PET")
    price = pack_info["price"]
    price_step = _demo_price_step(price)
    step = price_step["step"]

    rng = Random(179)
    # 구매 관심, 제형 선호, 맛 선호, 가격 민감도를 손님마다 한 번 정한다.
    panel = [(rng.random(), rng.uniform(-0.23, 0.44), rng.uniform(-0.32, 0.48), rng.uniform(0.2, 1.3))
             for _ in range(120)]

    def choose(*, still: bool = False, lighter_flavor: bool = False, cost: int = price) -> list[bool]:
        return [interest + still * form + lighter_flavor * flavor + (price - cost) / price * sensitivity >= 0.69
                for interest, form, flavor, sensitivity in panel]

    original = choose()
    base = _demo_selection(original)
    low_price, high_price = price - step, price + step
    price_down, price_up = choose(cost=low_price), choose(cost=high_price)

    def compare(after: list[bool]) -> dict[str, Any]:
        return {"selection": _demo_selection(after), "paired": _demo_paired(original, after)}

    price_compare = compare(price_down)
    return {
        "demo": True,
        "volumeMl": pack_info["volume_ml"],
        "base": {"price": price, "selection": base},
        "variants": {"form": compare(choose(still=True)), "flavor": compare(choose(lighter_flavor=True)),
                     "price": price_compare},
        "priceStep": price_step,
        "pricePoints": [
            {"price": low_price, "selection": price_compare["selection"]},
            {"price": price, "selection": base},
            {"price": high_price, "selection": _demo_selection(price_up)},
        ],
    }
