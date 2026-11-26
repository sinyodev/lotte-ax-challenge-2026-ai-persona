"""결과 보고서에 정성 인터뷰와 같은 가상 소비자의 선택 비교를 더한다."""

from __future__ import annotations

from agent import improve, improve_compare
from agent import phrases as P
from agent.note import Note
from shelftest import group, group_dialogue, group_flow, interview, result, store

_FINDINGS = {"agreed": "모인 의견", "split": "갈린 의견", "changed": "바뀐 생각"}
_VERDICTS = {"more": "개선안 선택률이 높음", "less": "개선안 선택률이 낮음", "unclear": "뚜렷한 차이 없음"}
_SOURCES = {"record": "소비자 기록", "shelf": "매대", "internal": "내부 자료", "web": "웹", "suggestion": "칠성이의 제안"}


def _records(meta: dict, sessions: list[dict]) -> dict:
    if not sessions:
        return {}
    run_id = meta["id"]
    pairs, _ = result.concept_visits(store.answers(run_id))
    participants = list(dict.fromkeys(p["id"] for session in sessions for p in session["participants"]))
    visitors = interview.find_many(meta, pairs, participants)
    records = {}
    for session in sessions:
        for candidate in session["turns"]:
            if found := group_flow.saved_turn(run_id, session, candidate["id"], visitors=visitors):
                turn, guest = found
                records[session["id"], turn["id"]] = {"quote": turn["text"], "who": guest["who"]}
    return records


def _linked_quote(entry: dict, records: dict) -> dict | None:
    voice = records.get((entry.get("session_id"), entry.get("quote_id")))
    return voice if entry.get("origin") == "record" and voice and voice["quote"] == entry.get("text") else None


def _voices(plan: dict, sessions: list[dict], records: dict) -> list[dict]:
    collected: dict[tuple[str, str], list[str]] = {}

    def keep(voice: dict, factor: str) -> None:
        labels = collected.setdefault((voice["quote"], voice["who"]), [])
        if factor not in labels:
            labels.append(factor)

    for session in sessions:
        sid = session["id"]
        method = P.GROUP_METHODS[session["mode"]]
        has_finding = False
        categories = ({"독립 응답 요약": group_dialogue.independent_answers(session["turns"])} if session["mode"] == "fgi"
                      else {label: session["findings"].get(key, []) for key, label in _FINDINGS.items()})
        for label, findings in categories.items():
            for finding in findings:
                caption = f"{method} · {label} ({finding['count']:,}명) · {finding['text']}"
                for turn_id in finding["turn_ids"]:
                    if voice := records.get((sid, turn_id)):
                        keep(voice, caption)
                        has_finding = True
                        break
        if not has_finding:
            for turn in session["turns"]:
                if voice := records.get((sid, turn["id"])):
                    keep(voice, f"{method} · {session['question']}")
                    break

    for item in plan.get("items", []):
        for entry in item.get("evidence", []):
            if voice := _linked_quote(entry, records):
                keep(voice, "개선안의 근거 발언")
    return [{"factor": " / ".join(labels), "quote": quote, "who": who}
            for (quote, who), labels in collected.items()]


def comparison_lines(pair: dict) -> list[str]:
    return [
        f"두 안에 모두 응답한 가상 소비자 {pair['n']:,}명 기준",
        (f"두 안 모두 선택 {pair['both']:,}명, 개선안에서만 선택 {pair['gained']:,}명, "
         f"원래 안에서만 선택 {pair['lost']:,}명, 두 안 모두 미선택 {pair['neither']:,}명"),
        (f"선택률 {pair['original_rate']:.1f}% → {pair['changed_rate']:.1f}% "
         f"({pair['delta_pp']:+.1f}%p), 차이의 95% 구간 {pair['low_pp']:+.1f}~{pair['high_pp']:+.1f}%p"),
        f"판정 {_VERDICTS[pair['verdict']]}",
    ]


def _adoption_lines(entries: list[dict], records: dict) -> list[str]:
    lines = []
    for entry in entries:
        if "session_id" in entry or "quote_id" in entry:
            voice = _linked_quote(entry, records)
            if voice:
                lines.append(f"채택 근거 · {voice['who']} · “{voice['quote']}”")
        elif entry.get("text") and entry.get("origin") in _SOURCES:
            lines.append(f"채택 근거 · {_SOURCES[entry['origin']]} · {entry['text']}")
    return list(dict.fromkeys(lines))


def pair_for(meta: dict, item: dict) -> dict | None:
    variant_id = item.get("run_id")
    variant = store.load_meta(variant_id) if store.valid_id(variant_id) else None
    if not variant or not improve.matches_change(meta["concept"], variant["concept"], item.get("values") or {}):
        return None
    return improve_compare.for_runs(meta["id"], variant_id)


def add(note: Note, concept: dict, test: dict) -> None:
    """기존 보고서의 소비자 반응에 조사 발언을, 채택한 개선안의 줄에 근거를 붙인다."""
    run_id = note.runs.get(concept["id"])
    meta = group_flow.owned_target(note, test.get("chat_id"), run_id)
    if not meta or not isinstance(test.get("evidence"), dict):
        return
    evidence = test["evidence"]
    sessions = group.completed(run_id)
    records = _records(meta, sessions)
    plan = group_flow.plan_for(note, run_id, concept["id"])
    for voice in _voices(plan, sessions, records):
        if voice not in evidence.setdefault("voices", []):
            evidence["voices"].append(voice)
    adopted = concept.get("_adopted_improvement") or {}
    if not adopted or adopted.get("base_run") != run_id or adopted.get("item_id") != plan.get("adopted_item_id"):
        return
    items = plan.get("items", [])
    item = next((i for i in items if i["id"] == adopted["item_id"] and i.get("run_id") == adopted.get("run_id")), None)
    if item:
        row = next((r for r in evidence.get("variants", []) if r.get("pair") and r["name"] == improve.plan_name(items, item)), None)
        if row and not row.get("adopted"):
            row["adopted"] = True
            row["line"] = "\n".join([row["line"], "기획자가 채택한 개선안", *_adoption_lines(adopted.get("evidence") or [], records)])
