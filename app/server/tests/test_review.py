"""지시서 22, 32: 결과 보고서의 판정과 글틀(agent/review.py). 모델을 부르지 않는다. 결과는 summarize의 모양을 손으로 만든다."""

from __future__ import annotations

import re

from agent import review
from agent.review import Inputs, Variant


def res(picked=17, n=182, rank=3, products=56, own=(("더하다 보리차", 10), ("다른 자사", 4)), rival=(("경쟁 녹차", 2),),
        none=1, pending=0, low=None, high=None,
        barriers=(("가격이 비쌈", 60), ("늘 마시는 것이 있음", 40), ("기타", 5)), picked_q=True, passed_q=True):
    p = picked / n if n else 0
    return {
        "n": n, "picked": picked, "rank": rank if picked else None, "products": products,
        "low": low if low is not None else round(100 * max(0, p - 0.04), 1),
        "high": high if high is not None else round(100 * min(1, p + 0.04), 1),
        "from": {"own": [{"name": a, "count": b} for a, b in own], "rival": [{"name": a, "count": b} for a, b in rival],
                 "none": none, "pending": pending},
        "barriers": [{"label": a, "count": b} for a, b in barriers],
        "quotes": {"picked": [{"visitor": "v1", "who": "24세 여자, 대학생", "said": "식사랑 잘 맞아서요."}] if picked_q else [],
                   "passed": [{"visitor": "v2", "who": "27세 남자, 회사원", "said": "좀 비싸네요."}] if passed_q else []},
    }


BARS = {"v2": ["가격이 비쌈"]}


def build(r, variants=(), group="20대", asked=None, total=None, board="20대 여성", **kw):
    return review.build(Inputs(result=r, group=group, name="밀키스 화채", pack="250ml 슬림캔", price="1,200원",
                               shelf="음료", asked=asked or r["n"], total=total or r["n"], variants=list(variants),
                               barriers_of=BARS, board_target=board, **kw))


# ---------- 권고 ----------


def test_verdict_thresholds():
    # 56개 제품: 기존 55개. 컨셉보다 많이 고른 기존 제품이 10% 미만(0~5개)이면 진행, 50% 미만이면 재테스트
    assert review.verdict(res(rank=1)) == "research"
    assert review.verdict(res(rank=6)) == "research"  # 5/55 = 9.1%
    assert review.verdict(res(rank=7)) == "retest"  # 6/55 = 10.9%
    assert review.verdict(res(rank=28)) == "retest"  # 27/55
    assert review.verdict(res(rank=29)) == "hold"  # 28/55 = 50.9%
    assert review.verdict(res(picked=0, own=(), rival=(), none=0)) == "hold"


def test_recommend_text_and_reasons():
    out = build(res(rank=1))
    rec = out["recommend"]
    assert rec["verdict"] == "research" and rec["text"] == "실제 소비자 조사 진행을 권고"
    assert rec["reasons"][0] == ("20대 가상 소비자 182명 중 17명이 선택, 매대 내 선택 순위 1위"
                                 "(기존 제품 55개 중 본 제품보다 많이 선택된 제품 없음)")
    # 고른 17명 중 14명이 자사 제품을 고르던 사람: 겹침 확인 필요가 이유에 든다
    assert rec["reasons"][1] == "선택한 17명 중 14명이 자사 제품을 선택하던 소비자로, 자사 제품과의 겹침 확인 필요"
    assert 2 <= len(rec["reasons"]) <= 3


def test_recommend_adopts_better_variant():
    base = res(rank=1, low=5.0, high=14.0, own=(("자사", 2),), rival=(("경쟁", 12),), none=3)
    a = Variant("가격 변경안", "1,000원", res(picked=26, rank=1, low=14.5, high=20.0))
    b = Variant("행사 변경안", "1+1", res(picked=15, rank=2, low=4.0, high=13.0))
    out = build(base, [a, b])
    assert out["recommend"]["text"] == "가격 변경안(1,000원)으로 실제 소비자 조사 진행을 권고"
    assert "가격 변경안(1,000원)이 기존안 대비 선택 9명 증가(범위가 겹치지 않음)" in out["recommend"]["reasons"]
    assert out["decisions"][1] == "조사에 올릴 안(250ml 슬림캔, 권장 소비자가 1,000원)"
    rows = out["evidence"]["variants"]
    assert [x["verdict"] for x in rows] == ["base", "better", "same"] and [x["best"] for x in rows] == [False, True, False]
    assert rows[1]["line"] == "가격 변경안(1,000원): 26명 선택, 기존안 대비 9명 증가"
    assert rows[2]["line"] == "행사 변경안(1+1): 15명 선택, 기존안 대비 뚜렷한 차이 없음"
    assert len(out["limits"]) == 2  # 나은 안이 있으면 "차이 없음"의 한계를 적지 않는다


def test_hold_never_adopts_and_no_gain_limit():
    base = res(rank=40, low=5.0, high=14.0)
    same = Variant("가격 변경안", "1,000원", res(picked=16, rank=41, low=4.0, high=13.0))
    out = build(base, [same])
    assert out["recommend"]["text"] == "보류를 권고"
    assert "개선안 1개는 기존안과 뚜렷한 차이 없음" in out["recommend"]["reasons"]
    assert out["limits"][-1] == "개선안 1개는 기존안과 뚜렷한 차이를 보이지 않음"
    assert out["decisions"][:2] == ["본 컨셉의 보류 여부", "타깃과 음용 상황을 바꾼 재검토 여부"]


def test_compare_worse_and_different_n():
    base = res(low=5.0, high=14.0)
    w = Variant("행사 변경안", "1+1", res(picked=2, n=100, rank=20, low=0.5, high=4.0))
    rows = review.compare_rows(base, [w])
    assert rows[1]["verdict"] == "worse" and rows[1]["line"] == "행사 변경안(1+1): 2명 선택, 기존안 대비 7.3%p 감소"
    assert review.compare_rows(base, []) == []


# ---------- 결정 요청, 핵심 수치 ----------


def test_decisions_target_differs_or_same():
    out = build(res(rank=10), group="40대 남자", board="20대 여성")
    assert out["decisions"] == ["수정 후 재테스트 진행 여부", "수정할 항목(비선택 사유 1위 '가격이 비쌈' 대응)",
                                "조사 타깃(컨셉 보드의 타깃 20대 여성, 테스트에서 고른 타깃 40대 남자 중 선택)"]
    assert build(res(rank=10), group="20대", board="20대")["decisions"][-1] == "조사 타깃(20대)"
    assert len(out["decisions"]) <= 3


def test_key_numbers_four_cells():
    key = build(res())["key"]
    assert [k["key"] for k in key] == ["picked", "rank", "from", "barrier"]
    assert key[0]["value"] == "182명 중 17명" and re.fullmatch(r"범위 \d+~\d+명", key[0]["note"])
    assert key[1]["value"] == "56개 제품 중 3위"
    assert key[2]["value"] == "경쟁사 2명, 자사 14명, 선택하지 않음 1명"
    assert key[3]["value"] == "가격이 비쌈(60명)"
    none = build(res(picked=0, own=(), rival=(), none=0, barriers=()))["key"]
    assert none[2]["value"] == "해당 없음" and none[3]["value"] == "해당 없음"


# ---------- 근거, 다음 조사, 부록 ----------


def test_evidence_from_rows_and_no_variants():
    ev = build(res())["evidence"]
    assert [(x["label"], x["n"]) for x in ev["from"]["rows"]] == [("경쟁사 제품", 2), ("자사 제품", 14), ("선택하지 않음", 1)]
    assert ev["from"]["rows"][1]["top"][0] == {"name": "더하다 보리차", "count": 10}
    assert ev["variants"] == [] and ev["compare"] == []
    assert build(res(picked=0, own=(), rival=(), none=0))["evidence"]["from"]["rows"] == []


def test_voices_quotes():
    v = review.voices(res(), BARS, "20대")
    assert v[0] == {"factor": "선택한 소비자", "quote": "식사랑 잘 맞아서요.", "who": "20대"}
    assert v[1] == {"factor": "비선택 사유 '가격이 비쌈'(60명)", "quote": "좀 비싸네요.", "who": "20대"}
    assert len(v) == 2  # 2위 요인을 고른 사람의 말은 없다
    assert review.voices(res(), {"v2": ["기타"]}, "전체")[1:] == []  # 요인을 고르지 않은 사람의 말은 싣지 않는다
    assert review.voices(res(), BARS, "전체")[0]["who"] == "20대"  # 나이대 하나의 패널이 아니면 나이에서


def test_voices_top_quote_prefers_single_factor_and_no_clues():
    r = res()
    r["quotes"]["passed"] = [
        {"visitor": "a", "who": "25세", "said": "전 물만 마시는 사람이라 굳이 손이 안 가요."},
        {"visitor": "b", "who": "25세", "said": "이 값이면 다른 걸 사겠어요."},
        {"visitor": "c", "who": "25세", "said": "좀 비싸네요."},
    ]
    bars = {"a": ["가격이 비쌈", "늘 마시는 것이 있음"], "b": ["가격이 비쌈", "맛이 끌리지 않음"], "c": ["가격이 비쌈"]}
    v = review.voices(r, bars, "20대")
    assert v[1]["quote"] == "좀 비싸네요."
    assert v[2]["quote"] == "전 물만 마시는 사람이라 굳이 손이 안 가요."  # 2위 요인은 남은 사람 가운데서
    del bars["c"]
    assert review.voices(r, bars, "20대")[1]["quote"] == "이 값이면 다른 걸 사겠어요."


def test_next_research_and_appendix():
    out = build(res(barriers=(("맛이 끌리지 않음", 38), ("가격이 비쌈", 30), ("기타", 2))), flavor="수박화채 맛",
                records=["타깃 테스트 소요 시간 0.3초, 호출 182회"])
    nxt = out["next"]
    assert nxt["questions"][0] == "수박화채 맛에 대한 기대와 우려" and len(nxt["questions"]) == 2
    assert nxt["target"].startswith("20대 응답자 182명 이상")
    assert any("무작위" in x for x in nxt["conditions"])
    app = out["appendix"]
    assert app["method"][0] == "매대: 편의점 음료 매대 기존 55개 제품에 본 제품을 더해 56개 제품"
    assert app["records"] == ["타깃 테스트 소요 시간 0.3초, 호출 182회"]
    assert any("10%" in x for x in app["rules"]) and any("초안" in x for x in app["rules"])


def test_first_page_has_no_run_records_and_disclaimer():
    out = build(res(), records=["타깃 테스트 소요 시간 0.3초, 호출 182회"])
    first = str({k: out[k] for k in ("head", "recommend", "decisions", "key", "limits", "disclaimer")})
    assert "소요 시간" not in first and "호출" not in first
    assert out["disclaimer"].startswith("본 결과는 가상 매대 테스트의 결과이며 판매 실적이나 예측이 아님")
    assert out["head"] == {"title": "신제품 컨셉 가상 매대 테스트 결과 보고", "product": "밀키스 화채",
                           "spec": "250ml 슬림캔, 권장 소비자가 1,200원"}


def test_no_banned_words():
    base = res(low=5.0, high=14.0)
    out = build(base, [Variant("가격 변경안", "1,500원", res(picked=26, rank=2, low=14.5, high=20.0))])
    text = str({k: v for k, v in out.items() if k != "appendix"})
    for w in ("전환", "유입", "신규 수요", "점유", "구매", "판매량", "매출", "오차 범위", "손님", "AI", "욕구", "실험"):
        assert w not in text, w
