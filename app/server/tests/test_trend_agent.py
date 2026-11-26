"""대화에서 고른 주제, 외부 근거, 코드 판정이 카드와 말로 이어진다."""

import asyncio

from agent import machine, research
from llm.base import set_llm
from llm.fake import FakeLLM


def turn(text, n=1):
    async def collect():
        return [event async for event in machine.turn("research-test", text, [], n)]
    return asyncio.run(collect())


def test_first_turn_from_feed_keeps_sources_and_reports_risk(monkeypatch):
    def verdict(keyword, stage):
        return {"keyword": keyword, "series": [{"month": "2026-03", "search_index": 20}],
                "stage": [stage], "reasons": ["검색 지수가 20이에요."], "related": []}
    monkeypatch.setattr(research, "verdicts", lambda: [verdict("견본차", "피크아웃"), verdict("견본청", "상승기")])
    events = turn("견본차 음료를 기획하고 싶어요.\n\n읽은 소식: 견본차를 선보였어요\n"
                  "출처: 견본 뉴스 https://news.example.org/p/1; 견본 통계 https://stats.example.org/r\n\n"
                  "기획에 앞서 견본차 관련 내부 자료의 24개월 추이와 판정 근거도 확인해 주세요.")
    labels = [e.label for e in events if e.t == "activity" and e.status == "done"]
    assert labels.index("내부 트렌드 자료를 확인했어요") < labels.index("최근 소식 확인을 마쳤어요") < labels.index("기획에 참고할 흐름을 정리했어요")
    items = next(e.payload["items"] for e in events if e.t == "card" and e.kind == "trend")
    assert [item["keyword"] for item in items if item["source"] == "internal"] == ["견본차", "견본청"]
    assert [(item["publisher"], item["url"]) for item in items if item["source"] == "web"] == [
        ("견본 뉴스", "https://news.example.org/p/1"), ("견본 통계", "https://stats.example.org/r")
    ]
    assert machine.CONVS["research-test"].product.value == "견본차"
    said = next(event.text for event in events if event.t == "say")
    assert "피크아웃" not in said and "견본차" in said


def test_no_research_until_there_is_a_subject(monkeypatch):
    fake = FakeLLM()
    set_llm(fake)
    events = turn("안녕하세요")
    assert not any(e.t == "card" and e.kind == "trend" for e in events)
    turn("제로 탄산을 기획해 보자", n=2)
    turn("아이디어 내기", n=3)
    assert sum(call["task"] == "trend" for call in fake.calls) == 1


def test_requested_new_keyword_finds_its_published_source(monkeypatch):
    import trend

    def feed():
        return [{"title": "새 별칭을 쓴 디저트가 나왔어요", "keyword": "견본별칭", "source": "web",
                 "publisher": "견본 뉴스룸", "url": "https://news.example.org/dessert", "date": "2026-10-01"}]

    monkeypatch.setattr(trend, "feed", feed)
    events = turn("견본별칭 트렌드를 찾아줘")
    items = next(e.payload["items"] for e in events if e.t == "card" and e.kind == "trend")
    assert [(item["keyword"], item["url"]) for item in items] == [("견본별칭", "https://news.example.org/dessert")]
    assert items[0]["verdict"] is None
