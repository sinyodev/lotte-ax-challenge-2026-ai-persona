"""매대에서 기록된 차이와 그 차이를 설명할 수 있는 참석자."""

from collections import defaultdict
from fractions import Fraction

from agent import phrases, result_brief
from shelftest import catalog, interview, method, result, store
from tools.consumer import AGE_NAMES

MAX_PARTICIPANTS = 6
POOL_SIZE = 24


def shelf_info(meta: dict) -> dict[str, tuple[str, bool]]:
    products = meta.get("shelf_products")
    if products is None:
        products = [(p.key, p.name, p.is_own) for p in catalog.public() if p.shelf == method.SHELF]
    return {key: (label, own) for key, label, own in products}


def shown(key: str, meta: dict, info: dict[str, tuple[str, bool]]) -> str:
    if key in info:
        return info[key][0]
    return interview._shown(key, meta["line"], meta["concept"]["name"])


def safe_reason(value: str | None, names: list[str]) -> str:
    text = (value or "").strip()
    if interview.TASTED.search(text) or interview.BANNED.search(text) or any(n in text for n in names if n):
        return ""
    return text


def age_sex(person: method.Person) -> str:
    band = AGE_NAMES.get(person.band, person.band or f"{person.age // 10 * 10}대")
    return f"{band} {person.sex}".strip()


def _cell_contrast(cells: dict[str, list[int]]) -> tuple[str, str] | None:
    if len(cells) < 2:
        return None
    # 비율이 같으면 응답이 더 많이 쌓인 집단을 먼저 쓴다.
    low = min(cells, key=lambda c: (Fraction(*cells[c]), -cells[c][1], c))
    high = min(cells, key=lambda c: (-Fraction(*cells[c]), -cells[c][1], c))
    return (high, low) if Fraction(*cells[high]) > Fraction(*cells[low]) else None


def resolve_question(payload: dict, question_id: str) -> dict | None:
    if question_id.startswith("custom:") and question_id[7:].strip():
        return {"id": question_id, "text": question_id[7:], "basis": "기획자가 정한 질문"}
    return next((q for q in payload["questions"] if q["id"] == question_id), None)


def prepare(run_id: str) -> dict | None:
    if not isinstance(run_id, str) or not store.ID_RE.fullmatch(run_id):
        return None
    meta = store.load_meta(run_id)
    if not meta or meta.get("id") != run_id or not meta.get("concept", {}).get("name"):
        return None
    rows = store.answers(run_id)
    pairs, _ = result.concept_visits(rows)
    if not pairs:
        return None
    target = meta.get("target", {})
    people = {p.uuid: p for p in method.people(target.get("age"), target.get("sex"))}
    summary = result.summarize(meta, rows, people)
    assert summary is not None
    line, concept = meta["line"], meta["concept"]["name"]
    info = shelf_info(meta)
    assigned = {v["visit"]: v["uuid"] for v in meta["participants"]} if "participants" in meta else None
    candidates, picked, passed = {}, [], []
    by_cell: dict[str, list[str]] = defaultdict(list)
    cells: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    own_ids, baseline_ids, barrier_ids = [], [], []
    top = (summary.get("barriers") or [None])[0]
    for before, row in pairs:
        visitor, uuid = row["visit"], row.get("uuid", "")
        person = people.get(uuid)
        if person is None:
            continue
        is_picked = row["product"] == line
        label = age_sex(person)
        cells[label][0] += is_picked
        cells[label][1] += 1
        if assigned is not None and assigned.get(visitor) != uuid:
            continue
        reason = safe_reason(row.get("sentence"), method.name_words(person))
        entry = {"id": visitor, "who": method.who_line(person), "picked": is_picked,
                 "choice": shown(row["product"], meta, info), "reason": reason or "사유 기록 없음"}
        if before is not None:
            entry["usual"] = shown(before["product"], meta, info)
            if is_picked:
                baseline_ids.append(visitor)
                if info.get(before["product"], ("", False))[1]:
                    own_ids.append(visitor)
        candidates[visitor] = entry
        by_cell[label].append(visitor)
        (picked if is_picked else passed).append(visitor)
        if top and not is_picked and top["label"] in (row.get("barriers") or []):
            barrier_ids.append(visitor)
    if not candidates:
        return None

    questions = []
    leaders: list[str] = []
    n, k = summary["n"], summary["picked"]
    if top and barrier_ids:
        label, count = top["label"], top["count"]
        pass_count = sum(not (row["product"] == line) and label in (row.get("barriers") or []) for _, row in pairs)
        basis = (f"지나친 {n - k:,}명 중 {count:,}명이 ‘{label}’을 걸린 점으로 들었어요."
                 if count == pass_count else
                 f"매대 응답 {n:,}건에서 ‘{label}’이 {count:,}번 기록됐어요. 지나친 응답에서는 {pass_count:,}건이에요.")
        questions.append({"id": "barrier", "visitor": barrier_ids[0], "text": f"‘{label}’은 매대에서 고를 때 어떤 영향을 줬어요?", "basis": basis})
        leaders.extend(barrier_ids[:2])
    inflow = result_brief.inflow(summary)
    if own_ids and inflow["own"]:
        basis = f"고른 {k:,}명 중 {inflow['own']:,}명은 컨셉이 없는 매대에서 자사 제품을 골랐어요."
        if inflow["pending"]:
            basis += f" 고른 사람 가운데 {inflow['pending']:,}명은 컨셉이 없는 매대의 답이 아직 없어요."
        questions.append({"id": "own", "visitor": own_ids[0], "text": "같은 회사의 기존 제품과 견주면, 어떤 점이 이 컨셉을 고르는 데 영향을 줬어요?", "basis": basis})
        leaders.extend(own_ids[:2])
    contrast = _cell_contrast(cells)
    if contrast and all(by_cell[c] for c in contrast):
        high, low = contrast
        h, hn = cells[high]
        l, ln = cells[low]
        basis = f"{high} 응답자 {hn:,}명 중 {h:,}명, {low} 응답자 {ln:,}명 중 {l:,}명이 골랐어요."
        questions.append({"id": "segment", "text": "매대에서 이 컨셉을 다른 제품과 견줄 때 어떤 점을 먼저 봤어요?", "basis": basis})
        leaders += [next((v for v in by_cell[high] if candidates[v]["picked"]), by_cell[high][0]),
                    next((v for v in by_cell[low] if not candidates[v]["picked"]), by_cell[low][0])]
    sources = {label: inflow[key] for key, label in phrases.BRIEF_FROM_LABELS.items() if inflow[key]}
    if baseline_ids and (len(sources) >= 2 or (not own_ids and inflow["known"] >= 2)):
        split = ", ".join(f"{label} {count:,}명" for label, count in sources.items())
        questions.append({"id": "inflow", "text": "이 컨셉이 있는 매대와 없는 매대에서 고를 때 무엇이 달랐어요?",
                          "basis": f"고른 {k:,}명 중 두 매대의 답이 모두 있는 {inflow['known']:,}명은 컨셉이 없는 매대에서 {split}이었어요."})
        leaders.extend(baseline_ids[:2])
    if len(questions) < 3 and len(candidates) > 1:
        occasions = {r["occasion"]: [r["picked"], r["n"]] for r in summary["by_occasion"] if r["occasion"]}
        if contrast := _cell_contrast(occasions):
            high, low = contrast
            h, hn = occasions[high]
            l, ln = occasions[low]
            questions.append({"id": "occasion", "text": "어떤 상황에서 마실 생각이었고, 그 상황은 선택에 어떤 영향을 줬어요?",
                              "basis": f"‘{high}’ 응답자 {hn:,}명 중 {h:,}명, ‘{low}’ 응답자 {ln:,}명 중 {l:,}명이 골랐어요."})
    if len(questions) < 3 and (not questions or (picked and passed)):
        questions.append({"id": "choice", "text": "오늘 매대에서 그 선택을 한 가장 큰 이유는 무엇이었어요?",
                          "basis": f"컨셉을 올린 매대에서 답한 {n:,}명 중 {k:,}명이 컨셉을 골랐고 {n - k:,}명이 지나쳤어요."})

    # 기준이 된 방문은 후보에 남기고, 추천과 후보 모두 선택이 다른 사람을 섞는다.
    first = [v[0] for v in (picked, passed) if v]
    varied = [ids[0] for ids in by_cell.values()]
    mixed = [members[i] for i in range(max(len(picked), len(passed)))
             for members in (picked, passed) if i < len(members)]
    pool = list(dict.fromkeys([*leaders[:1], *first, *leaders, *varied, *mixed]))[:POOL_SIZE]
    return {"demo": False, "view": "setup", "run_id": run_id, "concept": concept, "questions": questions,
            "candidates": [candidates[v] for v in pool], "suggested": pool[:MAX_PARTICIPANTS]}
