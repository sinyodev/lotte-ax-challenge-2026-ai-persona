"""아이디어·컨셉의 제품 사양(지시서 33). 모두 없어도 되는 칸이다.

    variants: [{container, pack, volume_ml, price, factory_price, shelf_life_months, shelf_life_days, kcal}]
    launch, season, storage: 글 또는 None
    channels: 글의 목록(없으면 [])

채우는 차례: (가) 과제의 컨셉이면 CONCEPTS의 값 → (나) 모델이 기획자의 말에서 뽑은 값이 말한 칸만 덮는다.
모델이 뽑은 숫자는 기획자의 말에 그 숫자가 실제로 있을 때만 쓴다(지어낸 숫자를 막는다).
price는 권장 소비자가, factory_price는 출고가다. 매대에 올릴 규격은 _shelf_variant(차례, 기본 0)가 가리킨다.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from onsite import concepts

SPEC_KEYS = ("variants", "launch", "season", "channels", "storage", "_shelf_variant", "_task_concept", "_estimated")
NUM_KEYS = ("volume_ml", "price", "factory_price", "shelf_life_months", "shelf_life_days", "kcal")
NONE = "없음"


def _said(value: int, text: str) -> bool:
    """기획자의 말에 이 숫자가 있는가("1,200"과 "1200"을 같게 본다)."""
    digits = re.sub(r"(?<=\d),(?=\d{3})", "", text or "")
    return re.search(rf"(?<!\d){value}(?!\d)", digits) is not None


def from_answer(ans: Any, text: str) -> dict[str, Any]:
    """모델의 답에서 사양을 옮긴다. 기획자의 말에 없는 숫자는 None으로 둔다."""
    variants = []
    for v in getattr(ans, "variants", None) or []:
        d = v.model_dump()
        for k in NUM_KEYS:
            if d.get(k) is not None and not _said(d[k], text):
                d[k] = None
        d["pack"] = (d.get("pack") or "").strip() or None
        variants.append(d)
    storage = getattr(ans, "storage", NONE)
    return {
        "variants": variants,
        "launch": (getattr(ans, "launch", "") or "").strip() or None,
        "season": (getattr(ans, "season", "") or "").strip() or None,
        "channels": [c.strip() for c in getattr(ans, "channels", None) or [] if c.strip()],
        "storage": storage if storage and storage != NONE else None,
    }


def _same(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if a.get("volume_ml") and b.get("volume_ml"):
        return a["volume_ml"] == b["volume_ml"]
    return bool(a.get("pack") and a.get("pack") == b.get("pack")) or a.get("container") == b.get("container")


def overlay(base: dict[str, Any], said: dict[str, Any]) -> dict[str, Any]:
    """base 위에 기획자가 말한 칸만 덮는다."""
    out = copy.deepcopy(base)
    variants = out.setdefault("variants", [])
    for sv in said.get("variants") or []:
        hit = next((v for v in variants if _same(v, sv)), None)
        if hit is None:
            if len(variants) < 3:
                variants.append(dict(sv))
            continue
        for k in NUM_KEYS:
            if sv.get(k) is not None:
                hit[k] = sv[k]
        if sv.get("pack"):
            hit["pack"] = sv["pack"]
    for k in ("launch", "season", "storage"):
        if said.get(k):
            out[k] = said[k]
    if said.get("channels"):
        out["channels"] = list(said["channels"])
    return out


META_WORDS = re.compile(r"입력값|형식상|칸|미정")
# 사양의 숫자가 든 문장(가격, 유통기한, 열량, 출시). 그것은 사양 묶음이 보인다
SPEC_NUMBERS = re.compile(r"\d[\d,]*\s*(?:원|개월|kcal|칼로리)|\d.*출시|출시.*\d")
# 기획자가 붙여 넣은 사양에서 세는 규격·가격의 숫자
PASTED_NUMBERS = re.compile(r"\d[\d,]*\s*(?:원|ml|mL|ML|L|개월|kcal|칼로리)")


def pasted_task_spec(text: str) -> bool:
    """기획자의 말이 과제 컨셉 하나의 사양을 통째로 적은 것인가(이름과 규격·가격의 숫자 둘 이상)."""
    return concepts.match(text or "") is not None and len(PASTED_NUMBERS.findall(text or "")) >= 2


def clean_meta(text: str) -> str:
    """아이디어의 글(line, diff)에서 답의 형식에 관한 문장("용량 칸은 형식상 입력값이에요")을 문장 단위로 버린다."""
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return " ".join(p for p in parts if p and not META_WORDS.search(p) and not SPEC_NUMBERS.search(p)).strip()


def _empty() -> dict[str, Any]:
    return {"variants": [], "launch": None, "season": None, "channels": [], "storage": None}


def _trim(spec: dict[str, Any]) -> dict[str, Any]:
    """규격이 하나이고 숫자가 용량뿐이면 표가 필요 없다(지금처럼 '용기와 용량' 한 줄로 보인다)."""
    vs = spec.get("variants") or []
    if len(vs) == 1 and all(vs[0].get(k) is None for k in NUM_KEYS if k != "volume_ml"):
        spec["variants"] = []
    return spec


def planner_spec(name: str, ans: Any, text: str, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """기획자의 아이디어의 사양. base가 없으면 (가) 과제의 컨셉에서, 그다음 (나) 말한 칸으로 덮는다."""
    task = None
    if base is None:
        hit = concepts.match(name)
        base = concepts.spec_of(hit) if hit else _empty()
        task = hit
    spec = _trim(overlay(base, from_answer(ans, text)))
    if task:
        # 판매 시기와 출시는 달이나 연도의 숫자가 있는 말만 과제의 값을 덮는다("여름 한정"은 "5~9월 한정"을 덮지 않는다)
        said = from_answer(ans, text)
        for k in ("launch", "season"):
            if said.get(k) and not re.search(r"\d", said[k]):
                spec[k] = base.get(k)
    if task:  # 과제의 컨셉이라는 표시와 맛(기획자가 다른 맛을 말했으면 기획자의 말)
        spec["_task_concept"] = task["id"]
        said_flavor = getattr(ans, "flavor", "") or ""
        rest = re.sub(r"\s+", "", text).replace(re.sub(r"\s+", "", task["name"]), "")  # 컨셉 이름 밖에서 말한 맛만
        if task.get("flavor") and not (said_flavor and re.sub(r"\s+", "", said_flavor) in rest):
            spec["_flavor"] = task["flavor"]
    return spec


# ---------- 칠성이가 스스로 낸 아이디어의 사양(11-25) ----------
# 모델이 제안한 값은 코드가 다듬는다: 용량은 매대에 있는 규격, 가격은 100원 단위로 매대의 가격 범위 안.

FALLBACK_VOLUMES = (190, 250, 355, 500)
CHANNELS = ("편의점", "대형마트·SSM", "온라인")
LAUNCH = re.compile(r"^\d{4}-\d{2}$")


def shelf_sizes(shelf: str = "음료") -> dict[str, tuple[list[int], int, int]]:
    """매대(음료/주류)에서 용기별로 있는 용량과 가격 범위: {용기: ([용량...], 최저가, 최고가)}."""
    from tools import shelf as shelf_tool

    vols: dict[str, set[int]] = {}
    prices: dict[str, list[int]] = {}
    for p in shelf_tool.products():
        if p.shelf != shelf:
            continue
        if p.volume and p.volume > 0:
            vols.setdefault(p.container, set()).add(p.volume)
        if p.price and p.price > 0:
            prices.setdefault(p.container, []).append(p.price)
    return {c: (sorted(vols.get(c) or []), min(prices[c]), max(prices[c])) for c in prices}


def shelf_size_lines(shelf: str = "음료") -> list[str]:
    """시키는 글에 적는 매대의 용기별 용량과 가격대."""
    return [f"{c}: 용량 {', '.join(str(v) for v in vs)}ml / 가격 {lo:,}~{hi:,}원"
            for c, (vs, lo, hi) in shelf_sizes(shelf).items() if vs]


def snap_volume(container: str, volume: int | None, sizes: dict[str, tuple[list[int], int, int]]) -> int:
    """같은 용기의 매대 용량 가운데 가장 가까운 값. 그 용기의 자료가 없으면 190, 250, 355, 500 가운데."""
    pool = (sizes.get(container) or ([], 0, 0))[0] or list(FALLBACK_VOLUMES)
    v = volume or 0
    return min(pool, key=lambda x: (abs(x - v), x))


def snap_price(container: str, price: int | None, sizes: dict[str, tuple[list[int], int, int]]) -> int | None:
    """100원 단위로 반올림하고 같은 용기(없으면 매대 전체)의 가격 범위 안으로 자른다."""
    if not price or price <= 0:
        return None
    if container in sizes:
        lo, hi = sizes[container][1], sizes[container][2]
    elif sizes:
        lo, hi = min(s[1] for s in sizes.values()), max(s[2] for s in sizes.values())
    else:
        lo, hi = 0, 10**9
    p = int(round(price / 100) * 100)
    p = max(p, int(-(-lo // 100) * 100))  # 범위 안의 100원 단위
    return min(p, int(hi // 100 * 100))


def proposed_spec(ans: Any, shelf: str = "음료", today: Any = None) -> dict[str, Any]:
    """칠성이가 스스로 낸 아이디어의 사양. 기획자의 말에 있는지 묻지 않고(그것은 _said의 일) 코드의 범위로만 다듬는다."""
    from datetime import date as _date

    today = today or _date.today()
    sizes = shelf_sizes(shelf)
    container = getattr(ans, "container", "") or ""
    volume = snap_volume(container, getattr(ans, "volume_ml", None), sizes)
    life = getattr(ans, "shelf_life_months", None)
    kcal = getattr(ans, "kcal", None)
    variant = {"container": container, "pack": None, "volume_ml": volume,
               "price": snap_price(container, getattr(ans, "price", None), sizes), "factory_price": None,
               "shelf_life_months": life if isinstance(life, int) and 1 <= life <= 24 else None,
               "shelf_life_days": None,
               "kcal": kcal if isinstance(kcal, int) and 0 <= kcal <= volume * 0.8 else None}
    launch = (getattr(ans, "launch", "") or "").strip()
    if not (LAUNCH.match(launch) and 1 <= int(launch[5:]) <= 12 and launch > today.strftime("%Y-%m")):
        launch = None
    season = (getattr(ans, "season", "") or "").strip()
    season = season if re.search(r"\d", season) else None
    said = {c.strip() for c in getattr(ans, "channels", None) or []}
    channels = [c for c in CHANNELS if c == "편의점" or c in said]
    # 유통기한과 열량은 칠성이가 어림한 값이다. 화면이 "추정값"이라고 밝힌다
    return {**_trim({"variants": [variant], "launch": launch, "season": season, "channels": channels, "storage": None}),
            "_estimated": True}


def spec_of(d: dict[str, Any]) -> dict[str, Any]:
    """아이디어·컨셉 dict에 적힌 지금의 사양."""
    out = {"variants": copy.deepcopy(d.get("variants") or []), "launch": d.get("launch"), "season": d.get("season"),
           "channels": list(d.get("channels") or []), "storage": d.get("storage")}
    if d.get("_estimated"):
        out["_estimated"] = True
    return out


def label(v: dict[str, Any]) -> str:
    """규격의 이름: '슬림캔 250ml'."""
    name = v.get("pack") or v.get("container") or ""
    return " ".join(x for x in (name, f"{v['volume_ml']}ml" if v.get("volume_ml") else "") if x)


def shelf_variant(d: dict[str, Any]) -> dict[str, Any] | None:
    vs = d.get("variants") or []
    if not vs:
        return None
    k = d.get("_shelf_variant") or 0
    return vs[k] if 0 <= k < len(vs) else vs[0]


def apply(d: dict[str, Any], spec: dict[str, Any], *, move_shelf: bool) -> None:
    """dict에 사양을 적는다. move_shelf면 매대에 올릴 규격(첫 번째)으로 용기·용량·이름표(pack)도 맞춘다."""
    d.update({k: spec.get(k) for k in ("variants", "launch", "season", "storage")})
    if spec.get("_task_concept"):
        d["_task_concept"] = spec["_task_concept"]
    if spec.get("_flavor"):
        d["flavor"] = spec["_flavor"]
    if spec.get("_estimated"):
        d["_estimated"] = True
    d["channels"] = list(spec.get("channels") or [])
    if not d["variants"]:
        d.pop("_shelf_variant", None)
        return
    if move_shelf:
        d["_shelf_variant"] = 0
        v = d["variants"][0]
        d["_container"] = v.get("container") or d.get("_container")
        d["_volume"] = v.get("volume_ml") or d.get("_volume")
        d["pack"] = f"{d['_container']} {d['_volume']}ml"


def split(d: dict[str, Any], new_id: Any) -> list[dict[str, Any]]:
    """규격이 둘 이상인 아이디어를 규격마다 하나로 나눈다(11-25 참가자의 검수: 아이디어와 컨셉 보드를 규격별로).
    이름·맛·설명·특징은 같고 규격과 그 값만 다르다. 첫 규격은 원래 id를 지키고 나머지는 new_id()로 받는다.
    규격이 하나 이하면 그대로 [d]."""
    vs = d.get("variants") or []
    if len(vs) < 2:
        return [d]
    out = []
    for k, v in enumerate(vs):
        one = copy.deepcopy(d)
        if k:
            one["id"] = new_id()
        one["variants"] = [copy.deepcopy(v)]
        one["_shelf_variant"] = 0
        one["_container"] = v.get("container") or d.get("_container")
        one["_volume"] = v.get("volume_ml") or d.get("_volume")
        one["pack"] = f"{one['_container']} {one['_volume']}ml"
        one.pop("changed", None)
        out.append(one)
    return out


def same_spec_group(ideas: list[dict[str, Any]]) -> list[str]:
    """기획자의 같은 아이디어를 규격별로 나눈 카드들의 id(이름이 같은 기획자의 아이디어가 둘 이상일 때). 없으면 []."""
    groups: dict[str, list[str]] = {}
    for i in ideas:
        if i.get("by") == "planner" and len(i.get("variants") or []) == 1:
            key = i.get("_task_concept") or re.sub(r"\s+", "", i.get("name") or "")
            groups.setdefault(key, []).append(i["id"])
    best = max(groups.values(), key=len, default=[])
    return best if len(best) >= 2 else []


def public(d: dict[str, Any]) -> dict[str, Any]:
    """화면에 보내는 사양의 칸(값이 있는 것만). 옛 dict에는 아무것도 없다."""
    out: dict[str, Any] = {}
    vs = d.get("variants") or []
    if vs:
        out["variants"] = [{"label": label(v), **{k: v.get(k) for k in NUM_KEYS if v.get(k) is not None}} for v in vs]
        k = d.get("_shelf_variant") or 0
        out["shelf_variant"] = k if 0 <= k < len(vs) else 0
    for k in ("launch", "season", "storage"):
        if d.get(k):
            out[k] = d[k]
    if d.get("channels"):
        out["channels"] = list(d["channels"])
    if d.get("_estimated") and any(v.get("shelf_life_months") is not None or v.get("kcal") is not None for v in vs):
        out["estimated"] = True
    return out


def tested_line(d: dict[str, Any]) -> str | None:
    """규격이 둘 이상이면 테스트한 규격을 밝히는 말(지시서 33의 4절). 아니면 None."""
    vs = d.get("variants") or []
    if len(vs) < 2:
        return None
    on = shelf_variant(d)
    others = [label(v) for v in vs if v is not on]
    name = label(on)
    return f"{name}{'으로' if _batchim(name) else '로'} 테스트, {', '.join(others)}도 있음"


def _batchim(word: str) -> bool:
    """'으로'를 붙일 받침이 있는가(ㄹ 받침과 ml처럼 읽는 말은 '로')."""
    ch = word[-1:]
    if not ("가" <= ch <= "힣"):
        return False
    k = (ord(ch) - 0xAC00) % 28
    return k not in (0, 8)
