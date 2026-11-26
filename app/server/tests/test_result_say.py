"""테스트 결과를 알리는 칠성이의 말: 현황 → 알게 된 것 → 다음. 숫자는 코드가 넣는다. 결과와 답은 손으로 지어낸 견본이다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent import machine, voice
from agent import phrases as P
from agent import result_brief as RB


def view(status="done", asked=300, total=300, n=300, k=73, rank=1, own=10, occasions=None, barriers=None):
    return {
        "status": status, "concept": {"name": "밀키스 화채"}, "who": {"label": "20대 손님"}, "asked": asked, "total": total,
        "result": {"n": n, "picked": k, "products": 68, "rank": rank if k else None,
                   "from": {"rival": [{"name": "경쟁 콜라", "count": k - own}] if k else [],
                            "own": [{"name": "자사 사이다", "count": own}] if k and own else [], "none": 0, "pending": 0},
                   "barriers": barriers if barriers is not None else [{"label": "처음 보는 제품이라 망설여짐", "count": 99},
                                                                      {"label": "맛이 끌리지 않음", "count": 40}],
                   "by_occasion": occasions if occasions is not None else [
                       {"occasion": "밖에서 식사할 때 입가심", "n": 166, "picked": 50},
                       {"occasion": "집에서 혼자 낮이나 저녁에", "n": 100, "picked": 20},
                       {"occasion": "집에서 가족과 간식 자리", "n": 3, "picked": 3}]},  # 10명이 안 되는 상황은 견주지 않는다
    }


def said(v, eta=None):
    bits, order, after = machine._result_bits(v, eta)
    turn = voice.result_turn(product=v["concept"]["name"], received=bits, order=order)
    return turn, f"{turn.fallback} {after}"


def test_running_says_progress_and_time_first():
    turn, text = said(view(status="running", asked=102, n=102, k=69), eta=230)
    assert text == ("300명 중 102명이 답했어요. 약 4분 뒤에 끝나요. "
                    "지금까지는 102명 중 69명이 밀키스 화채를 골랐고 68개 제품 가운데 1위예요. "
                    "끝나면 결과가 300명 기준으로 바뀌어요.")
    assert voice.check(turn.fallback, turn.facts) == []


def test_running_without_time_leaves_it_out():
    turn, text = said(view(status="running", asked=102, n=102, k=69), eta=None)
    assert "분" not in text and text.startswith("300명 중 102명이 답했어요. 지금까지는")
    assert voice.check(turn.fallback, turn.facts) == []


def test_done_says_conclusion_then_two_insights_then_next():
    turn, text = said(view())
    assert text == ("테스트가 끝났어요. 20대 300명 중 73명이 밀키스 화채를 골랐고 68개 제품 가운데 1위예요. "
                    "'밖에서 식사할 때 입가심'일 때 가장 많이 골랐고, 고르지 않은 손님은 '처음 보는 제품이라 망설여짐'을 가장 많이 들었어요. "
                    f"{P.RESULT_NEXT_DONE}")
    assert voice.check(turn.fallback, turn.facts) == []
    for w in ("컨셉", "구매", "열에", "순위"):
        assert w not in text


def test_nobody_picked():
    turn, text = said(view(k=0, occasions=[]))
    assert "20대 300명 중 밀키스 화채를 고른 손님은 없었어요." in text and "일 때" not in text
    assert voice.check(turn.fallback, turn.facts) == []


def test_check_catches_old_words_and_wrong_order():
    turn, _ = said(view())
    old = "20대 손님 300명 가운데 73명이 컨셉을 구매했어요. 구매 순위 1위예요."
    why = voice.check(old, turn.facts)
    assert any("컨셉" in w for w in why) and any("구매" in w for w in why)
    swapped = ("'처음 보는 제품이라 망설여짐'을 가장 많이 들었어요. '밖에서 식사할 때 입가심'일 때 가장 많이 골랐어요. "
               "20대 300명 중 73명이 밀키스 화채를 골랐어요.")
    assert any("차례" in w for w in voice.check(swapped, turn.facts))


def test_eta_counts_both_shelves():
    start = datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc)
    meta = {"status": "running", "started_at": start.isoformat(), "total": 100}
    # 60초 동안 새로 물은 답 60개 + 저장해 둔 답 20개. 남은 답은 200 - 80 = 120개 → 120초
    rows = [{"visit": f"T{i}", "cond": "c"} for i in range(60)] + [{"visit": f"T{i}", "cond": "b", "reused": True} for i in range(20)]
    assert RB.eta_seconds(meta, rows, now=start + timedelta(seconds=60)) == 120.0
    assert RB.eta_seconds({**meta, "status": "done"}, rows, now=start + timedelta(seconds=60)) is None
    assert RB.eta_seconds(meta, rows[:5], now=start + timedelta(seconds=60)) is None  # 셀 만큼 쌓이지 않았다
    assert P.result_eta(120.0) == "약 2분 뒤에 끝나요." and P.result_eta(30) == "1분 안에 끝나요."


def test_headline_is_one_short_sentence():
    assert P.brief_headline("20대", 300, 73, "밀키스 화채", 1, 68) == "20대 300명 중 73명이 골랐고, 매대 68개 가운데 1위예요"
    assert P.brief_headline("20대", 102, 69, "밀키스 화채", 1, 68, running=True).startswith("지금까지는 20대 102명 중 69명이")
