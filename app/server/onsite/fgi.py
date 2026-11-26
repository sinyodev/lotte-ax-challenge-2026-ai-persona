"""정성 조사 문서의 원문과 참석자 표에서 센 호감도를 함께 남긴다."""

import re
from pathlib import Path

from docx import Document

SCORE_THRESHOLD = 4
PARTICIPANT_FIELDS = ("ID", "연령대", "성별", "직업", "RTD커피 주 구매(회)")
MODERATOR = re.compile(r"^진행자.*?[：:]")
CLAIM_OF = re.compile(r"(\d+)\s*명\s*(?:중(?:에서)?|가운데)\s*(\d+)\s*명")
CLAIM_SLASH = re.compile(r"(\d+)\s*명?\s*/\s*(\d+)\s*명")
QUOTE = re.compile(
    r'''^(?:“(?P<double>.*)”|"(?P<straight>.*)"|‘(?P<single>.*)’|'(?P<apostrophe>.*)')'''
    r"\s*(?:\(\s*(?P<by>[^\s,·;/)]+)[^)]*\))?$",
    re.DOTALL,
)


def _table_rows(table) -> list[list[str]]:
    return [[cell.text.strip() for cell in row.cells] for row in table.rows]


def _explicit_number(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text)
    return int(match[1].replace(",", "")) if match else None


def _read_method(rows: list[list[str]]) -> dict:
    fields = dict(rows)
    method = fields.get("조사 방법", "")
    cost_period = fields.get("비용/기간", "")
    return {
        "groups": _explicit_number(method, r"(\d+)\s*(?:개\s*)?그룹"),
        "per_group": _explicit_number(method, r"그룹\s*당\s*(\d+)\s*명"),
        "minutes": _explicit_number(method, r"(\d+)\s*분"),
        "cost_10k_won": _explicit_number(cost_period, r"([\d,]+)\s*만\s*원"),
        "weeks": _explicit_number(cost_period, r"(\d+)\s*주"),
        "recruit_note": fields.get("모집 방식") or None,
    }


def _number_cell(cell: str) -> int | None:
    return int(cell) if re.fullmatch(r"[0-9]+", cell) else None


def _read_participants(header: list[str], rows: list[list[str]]) -> tuple[list[str], list[dict]]:
    concepts = [column for column in header if column and column not in PARTICIPANT_FIELDS]
    participants = []
    for cells in rows:
        row = dict(zip(header, cells, strict=True))
        if not any(cells):
            continue
        participants.append({
            "id": row["ID"] or None,
            "age": row["연령대"] or None,
            "gender": row["성별"] or None,
            "job": row["직업"] or None,
            "rtd_per_week": _number_cell(row["RTD커피 주 구매(회)"]),
            "scores": {concept: _number_cell(row[concept]) for concept in concepts},
        })
    return concepts, participants


def _read_claim(text: str) -> dict | None:
    if match := CLAIM_OF.search(text):
        return {"n": int(match[2]), "of": int(match[1])}
    if match := CLAIM_SLASH.search(text):
        return {"n": int(match[1]), "of": int(match[2])}
    return None


def _moderator_entry(concept: str, text: str, participants: list[dict]) -> dict:
    scores = [row["scores"][concept] for row in participants]
    valid_scores = [score for score in scores if score is not None and 1 <= score <= 5]
    recount = {"score_4plus": sum(score >= SCORE_THRESHOLD for score in valid_scores), "of": len(valid_scores)}
    claimed = _read_claim(text)
    mismatch = claimed is not None and (
        claimed["n"] != recount["score_4plus"] or claimed["of"] != recount["of"]
    )
    return {"concept": concept, "text": text, "claimed": claimed, "recount": recount, "mismatch": mismatch}


def _read_sections(document, concepts: list[str], participants: list[dict]) -> tuple[list, list, list]:
    quotes, moderator, overall = [], [], []
    current_concept = None
    in_overall = False
    for paragraph in document.paragraphs:
        raw = paragraph.text.strip()
        style = paragraph.style.name
        if style == "Heading 1":
            current_concept = None
            in_overall = "종합 시사점" in raw
        elif style == "Heading 2":
            heading = re.sub(r"^(?:[①-⑳]|\d+[.)])\s*", "", raw)
            current_concept = heading if heading in concepts else None
        elif in_overall and style.startswith("List") and raw:
            overall.append(raw)
        elif current_concept and MODERATOR.match(raw):
            moderator.append(_moderator_entry(current_concept, raw, participants))
        elif current_concept and (quote := QUOTE.fullmatch(raw)):
            exact_words = next(quote[k] for k in ("double", "straight", "single", "apostrophe") if quote[k] is not None)
            quotes.append({"concept": current_concept, "text": exact_words, "by": quote["by"]})
    return quotes, moderator, overall


def _report_recount(entries: list[dict]) -> dict:
    compared = [entry for entry in entries if entry["claimed"] is not None]
    mismatches = [entry for entry in compared if entry["mismatch"]]
    evidence = " ".join(
        f"{e['concept']}는 진행자 문장에 {e['claimed']['of']}명 중 {e['claimed']['n']}명, "
        f"참석자 표에는 {e['recount']['of']}명 중 {e['recount']['score_4plus']}명으로 나왔어요."
        for e in mismatches
    )
    detail = (
        f"진행자 요약 중 인원과 전체 인원이 모두 적힌 {len(compared)}건을 참석자 표의 호감도 "
        f"{SCORE_THRESHOLD}점 이상 인원과 비교했어요. 표에서는 1~5점이 있는 사람을 전체로 셌어요. "
        "진행자가 말한 관심과 표의 호감도는 서로 다른 항목일 수 있어요."
    )
    return {
        "source": "fgi", "rule": "moderator_recount", "label": "진행자 요약의 인원을 참석자 표와 비교했어요",
        "removed": 0, "flagged": len(mismatches), "detail": f"{detail} {evidence}".strip(),
    }


def build_fgi(path: Path) -> tuple[dict, list[dict]]:
    document = Document(path)
    method_rows = participant_header = participant_rows = None
    for table in document.tables:
        header, *rows = _table_rows(table)
        if header == ["항목", "내용"]:
            method_rows = rows
        elif set(PARTICIPANT_FIELDS).issubset(header):
            participant_header, participant_rows = header, rows
    if method_rows is None or participant_header is None:
        raise ValueError("정성 조사 문서에서 조사 방법 또는 참석자 표를 찾지 못했습니다.")

    concepts, participants = _read_participants(participant_header, participant_rows)
    quotes, moderator, overall = _read_sections(document, concepts, participants)
    result = {
        "method": _read_method(method_rows),
        "participants": participants,
        "quotes": quotes,
        "moderator": moderator,
        "overall": overall,
    }
    return result, [_report_recount(moderator)]
