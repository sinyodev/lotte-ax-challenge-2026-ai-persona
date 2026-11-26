import json

import pytest
from docx import Document

from onsite.fgi import _read_claim, build_fgi


def _add_table(document, rows):
    table = document.add_table(rows=0, cols=len(rows[0]))
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row, strict=True):
            cell.text = value


@pytest.mark.parametrize(
    ("text", "claim"),
    [
        ("7명 중 2명에게 해당합니다.", {"n": 2, "of": 7}),
        ("8명 가운데 4명에게 해당합니다.", {"n": 4, "of": 8}),
        ("9명 중에서 3명에게 해당합니다.", {"n": 3, "of": 9}),
        ("3명 / 13명이 관심을 보였습니다.", {"n": 3, "of": 13}),
        ("4/11명 정도입니다.", {"n": 4, "of": 11}),
        ("7명이 관심을 보였습니다.", None),
        ("구매 가격은 2,000원입니다.", None),
    ],
)
def test_claim_requires_explicit_numerator_and_denominator(text, claim):
    assert _read_claim(text) == claim


def test_fgi_preserves_source_and_recounts_valid_scores(tmp_path):
    document = Document()
    document.add_heading("1. 조사 개요", level=1)
    _add_table(document, [
        ["항목", "내용"],
        ["조사 방법", "2개 그룹 (그룹당 3명), 약 75분"],
        ["모집 방식", "최근 무가당 음료 구매자를 먼저 모집"],
        ["비용/기간", "1,030만 원 / 4주"],
    ])
    document.add_heading("2. 참석자 구성", level=1)
    _add_table(document, [
        ["ID", "연령대", "성별", "직업", "RTD커피 주 구매(회)", "자몽 탄산", "보리차", "매실차", "레몬차"],
        ["Q81", "60대", "여성", "사무직", "2", "5", "1", "4", "5"],
        ["Q82", "30대", "남성", "제조업", "0", "3", "4", "1", "4"],
        ["Q83", "40대", "여성", "", "", "", "5", "3", "2"],
    ])
    document.add_heading("3. 주요 반응", level=1)
    document.add_heading("① 자몽 탄산", level=2)
    words = "향이 더 선명했으면 좋겠어요."
    document.add_paragraph(f'“{words}” (Q81, 60대)', "List Bullet")
    no_author = "색이 마음에 들어요."
    document.add_paragraph(f'"{no_author}"', "List Bullet")
    only_denominator_differs = "진행자 종합: 3명 중 1명이 관심을 보였다."
    document.add_paragraph(only_denominator_differs)
    document.add_heading("② 보리차", level=2)
    only_count_differs = "진행자 종합: 1명/3명이 관심을 보였다."
    document.add_paragraph(only_count_differs)
    document.add_heading("③ 매실차", level=2)
    unquantified = "진행자 종합: 일부가 선호했다."
    document.add_paragraph(unquantified)
    document.add_heading("④ 레몬차", level=2)
    exactly_matches = "진행자 종합: 3명 가운데 2명이 선호했다."
    document.add_paragraph(exactly_matches)
    document.add_heading("4. 종합 시사점", level=1)
    conclusions = ["향을 바꾼 시제품을 비교한다.", "후속 조사에서 가격을 확인한다."]
    for conclusion in conclusions:
        document.add_paragraph(conclusion, "List Bullet")
    document.add_paragraph("※ 견본 초안")
    path = tmp_path / "견본.docx"
    document.save(path)

    fgi, (report,) = build_fgi(path)

    assert fgi["method"] == {
        "groups": 2, "per_group": 3, "minutes": 75, "cost_10k_won": 1030, "weeks": 4,
        "recruit_note": "최근 무가당 음료 구매자를 먼저 모집",
    }
    assert len(fgi["participants"]) == 3
    assert fgi["participants"][0] == {
        "id": "Q81", "age": "60대", "gender": "여성", "job": "사무직", "rtd_per_week": 2,
        "scores": {"자몽 탄산": 5, "보리차": 1, "매실차": 4, "레몬차": 5},
    }
    assert fgi["participants"][2]["job"] is None
    assert fgi["participants"][2]["rtd_per_week"] is None
    assert fgi["participants"][2]["scores"]["자몽 탄산"] is None
    assert fgi["quotes"] == [
        {"concept": "자몽 탄산", "text": words, "by": "Q81"},
        {"concept": "자몽 탄산", "text": no_author, "by": None},
    ]
    assert fgi["moderator"] == [
        {"concept": "자몽 탄산", "text": only_denominator_differs, "claimed": {"n": 1, "of": 3},
         "recount": {"score_4plus": 1, "of": 2}, "mismatch": True},
        {"concept": "보리차", "text": only_count_differs, "claimed": {"n": 1, "of": 3},
         "recount": {"score_4plus": 2, "of": 3}, "mismatch": True},
        {"concept": "매실차", "text": unquantified, "claimed": None,
         "recount": {"score_4plus": 1, "of": 3}, "mismatch": False},
        {"concept": "레몬차", "text": exactly_matches, "claimed": {"n": 2, "of": 3},
         "recount": {"score_4plus": 2, "of": 3}, "mismatch": False},
    ]
    assert fgi["overall"] == conclusions
    assert report["source"] == "fgi" and report["removed"] == 0 and report["flagged"] == 2
    assert "모두 적힌 3건" in report["detail"]
    assert json.loads(json.dumps(fgi, allow_nan=False)) == fgi
