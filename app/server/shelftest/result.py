"""화면이 읽는 결과 (지시서 15의 1절 GET /api/runs/{id}). 모델을 부르지 않는다. 쌓인 답에서 그때그때 센다.

- 다녀간 손님: 컨셉을 올린 매대의 답이 온 손님(이 매대부터 묻는다). 컨셉이 없는 매대의 답은 뒤에 채워지고,
  "전에 집던 것"은 그 답이 온 손님만으로 센다(아직 안 온 손님 수는 from.pending).
- 집은 손님과 윌슨 95% 구간(%), 56개 가운데 순위, 위아래 둘씩의 이웃.
- 집은 손님이 컨셉이 없는 매대에서 집던 것: 경쟁사 제품, 자사 제품, 안 사던 손님.
- 보는 눈, 걸린 점, 상황마다, 손님의 말(각각 많아야 넷, 걸린 점이 서로 다른 것). 손님의 이름은 내보내지 않는다.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from shelftest import catalog, method
from tools.occasion_display import show as show_occasion

QUOTES = 4
NO_PURCHASE_SHOWN = "아무것도 사지 않음"  # 손님의 말에 붙는 "고른 것"(지시서 17의 D)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """윌슨 95% 구간을 퍼센트로."""
    if n <= 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(100 * max(0.0, center - half), 1), round(100 * min(1.0, center + half), 1)


def catalog_snapshot() -> list[list[str | bool]]:
    """현재 음료 매대의 내부 상품명, 표시명, 자사 여부를 저장할 형태로 반환한다."""
    return [[p.key, p.name, p.is_own] for p in catalog.current() if p.shelf == method.SHELF]


def complete_visits(rows: list[dict[str, Any]]) -> tuple[list[tuple[dict, dict]], set[str]]:
    """((기준, 컨셉) 짝을 방문 차례대로, 뺀 방문)."""
    by: dict[str, dict[str, dict]] = {}
    skipped: set[str] = set()
    for r in rows:
        v = r.get("visit")
        if not v:
            continue
        if r.get("skip"):
            skipped.add(v)
            continue
        by.setdefault(v, {}).setdefault(r.get("cond", ""), r)
    pairs = [(c[method.BASELINE], c[method.CONCEPT]) for v, c in sorted(by.items())
             if v not in skipped and method.BASELINE in c and method.CONCEPT in c]
    return pairs, skipped


def concept_visits(rows: list[dict[str, Any]]) -> tuple[list[tuple[dict | None, dict]], set[str]]:
    """((기준 또는 None, 컨셉) 짝을 방문 차례대로, 뺀 방문). 컨셉을 올린 매대의 답이 온 손님은 모두 든다."""
    by: dict[str, dict[str, dict]] = {}
    skipped: set[str] = set()
    for r in rows:
        v = r.get("visit")
        if not v:
            continue
        if r.get("skip"):
            skipped.add(v)
            continue
        by.setdefault(v, {}).setdefault(r.get("cond", ""), r)
    pairs = [(c.get(method.BASELINE), c[method.CONCEPT]) for v, c in sorted(by.items())
             if v not in skipped and method.CONCEPT in c]
    return pairs, skipped


def _pick_quotes(cands: list[tuple[dict, str]], key) -> list[dict[str, Any]]:
    """걸린 점(또는 상황)이 서로 다른 것을 먼저, 모자라면 나머지에서 방문 차례대로."""
    out, seen, rest = [], set(), []
    for row, said in cands:
        k = key(row)
        if k in seen:
            rest.append((row, said))
            continue
        seen.add(k)
        out.append((row, said))
    out += rest
    return [_quote(r, s) for r, s in out[:QUOTES]]


def _quote(row: dict[str, Any], said: str) -> dict[str, Any]:
    return {"visitor": row["visit"], "who": row["_who"], "occasion": row["_occasion"], "said": said,
            "chose": row["_chose"]}


def summarize(meta: dict[str, Any], rows: list[dict[str, Any]], people: dict[str, method.Person]) -> dict[str, Any] | None:
    pairs, _ = concept_visits(rows)
    n = len(pairs)
    if n == 0:
        return None
    line = meta["line"]
    concept_name = meta["concept"]["name"]
    occ_names = {code: show_occasion(o["상황"]) for code, o in method.occasions().items()}  # 화면의 이름(프롬프트는 그대로)
    products = meta.get("shelf_products")
    if products is None:
        # 결합 이전 기록은 당시 공개 매대에서의 순위와 자사 분류를 재현한다.
        products = [(p.key, p.name, p.is_own) for p in catalog.public() if p.shelf == method.SHELF]
    info = {name: (shown, ours) for name, shown, ours in products}

    def shown(name: str) -> str:
        if name == line:
            return concept_name
        if name == method.NO_PURCHASE:
            return NO_PURCHASE_SHOWN
        return info[name][0] if name in info else method.display(name)

    concept_rows = [c for _, c in pairs]
    picked_pairs = [(b, c) for b, c in pairs if c["product"] == line]
    k = len(picked_pairs)
    low, high = wilson(k, n)

    # 순위: 컨셉을 올린 매대에서 집힌 수. 순위는 1 + 나보다 많이 집힌 제품 수(같은 수면 컨셉을 앞에, 나머지는 이름 차례)
    counts = Counter(c["product"] for c in concept_rows)
    names = [p[0] for p in products] + [line]
    ranked = sorted(names, key=lambda x: (-counts.get(x, 0), x != line, shown(x)))
    rank = 1 + sum(1 for x in names if counts.get(x, 0) > k) if k else None

    def nb(x: str) -> dict[str, Any]:
        return {"name": shown(x), "picked": counts.get(x, 0), "ours": x == line or info.get(x, ("", False))[1],
                "self": x == line}

    if k:
        i = ranked.index(line)
        neighbors = [nb(x) for x in ranked[max(0, i - 2): i + 3]]
    else:
        neighbors = [nb(x) for x in ranked[:5] if counts.get(x, 0) > 0]

    rival: Counter = Counter()
    own: Counter = Counter()
    none = pending = 0
    for b, _ in picked_pairs:
        if b is None:
            pending += 1
            continue
        before = b["product"]
        if before == method.NO_PURCHASE:
            none += 1
        elif info.get(before, ("", False))[1]:
            own[before] += 1
        else:
            rival[before] += 1

    views = Counter(c.get("view", "") for c in concept_rows)
    barriers = Counter(x for c in concept_rows for x in c.get("barriers") or [])

    by_occ: dict[str, list[int]] = {}
    for c in concept_rows:
        code = c.get("occasion", "")
        cell = by_occ.setdefault(code, [0, 0])
        cell[0] += 1
        cell[1] += c["product"] == line

    # 손님의 말: 집은 손님은 고른 이유, 안 집은 손님은 새 제품을 보고 든 생각. 이름이 든 말은 뺀다
    picked_q, passed_q = [], []
    for _, c in pairs:
        person = people.get(c.get("uuid", ""))
        if person is None:
            continue
        is_picked = c["product"] == line
        said = (c.get("sentence") if is_picked else c.get("said")) or ""
        said = said.strip()
        if not said or any(w and w in said for w in method.name_words(person)):
            continue
        row = {**c, "_who": method.who_line(person), "_occasion": occ_names.get(c.get("occasion", ""), ""),
               "_chose": shown(c["product"])}
        (picked_q if is_picked else passed_q).append((row, said))

    journey_fields = {}
    if any("journey" in row for row in concept_rows):
        from shelftest import journey
        journey_fields["journey"] = journey.funnel(concept_rows, line)
    return {
        **journey_fields, "n": n, "picked": k, "low": low, "high": high,
        "rank": rank, "products": len(names),
        "neighbors": neighbors,
        "from": {"rival": [{"name": shown(x), "count": y} for x, y in rival.most_common()],
                 "own": [{"name": shown(x), "count": y} for x, y in own.most_common()],
                 "none": none, "pending": pending},
        "views": [{"label": v, "count": views.get(v, 0)} for v in method.VIEWS],
        "barriers": [{"label": b, "count": c} for b, c in barriers.most_common() if c > 0],
        "by_occasion": [{"occasion": occ_names.get(code, code), "n": cell[0], "picked": cell[1]}
                        for code, cell in sorted(by_occ.items(), key=lambda kv: (-kv[1][0], kv[0]))],
        "quotes": {"picked": _pick_quotes(picked_q, lambda r: r.get("occasion")),
                   "passed": _pick_quotes(passed_q, lambda r: (r.get("barriers") or [""])[0])},
    }
