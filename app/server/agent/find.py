"""찾기(코드): 읽기가 고른 도구를 돌린다. 숫자는 여기서만 나온다 (지시서 09의 2절 "찾기").

- 찾은 것 하나는 Found 하나다: 카드의 글(정확한 숫자), 출처의 이름과 건수, 말할 사실(말로 바꾼 숫자),
  글틀 문장("국민건강영양조사를 찾아보니 …더라고요.").
- 찾은 것이 없거나 건수가 30건 미만이면 아무것도 돌려주지 않는다. 칠성이는 그것에 대해 말하지 않는다.
- 말과 카드의 글에 "자료", "기록", "데이터", "근거"를 쓰지 않는다. 사실과 출처의 이름만 적는다.
- 요즘 소식(웹)은 모델이 찾고(agent/steps.py의 trend) 이 파일은 받은 것을 Found로 바꾼다. 한 대화에 제품마다 한 번.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent import phrases as P
from agent.note import Note
from onsite import purchase
from tools import consumer, shelf, spoken, web
from tools.consumer import MIN_FOUND, Group, josa

TOOLS = ["who", "when", "with_food", "by_job", "shelf", "sales", "news", "purchase_outcomes"]
TOOL_MEANINGS = {
    "who": "누가 마시나(연령대마다 다른 음료보다 몇 배 자주 마시나)",
    "when": "언제·어디서 마시나(시간대, 장소, 밥과 함께인지. arg에 '아침'처럼 시간대를 주면 그 시간대에 마시는 몫)",
    "with_food": "무엇과 함께 먹나(그 음료를 마신 끼니에 함께 먹은 음식)",
    "by_job": "어떤 일을 하는 사람이 마시나(직업 구분마다 몇 배)",
    "shelf": "편의점 매대에 비슷한 제품이 몇 개인가(arg에 니즈의 이름을 주면 그 니즈를 채우는 제품 수, 그 가운데 롯데칠성 제품 수)",
    "sales": "편의점에서 얼마나 팔리나(편의점 매출, 그 전해와 견줌)",
    "news": "요즘 소식(웹에서 최근 기사. 제품마다 한 번)",
    "purchase_outcomes": "컨셉 조사 구매의향과 출시 12개월 실제 구매경험률을 비교한다. arg는 제품명, 과거 제품 전체 비교는 빈 문자열.",
}
RECORD_SAID = P.RECORD_NAME  # 말에 붙이는 출처의 이름
SALES_SAID = "식품산업통계정보"


@dataclass
class Found:
    key: str  # 같은 것을 두 번 말하지 않게 하는 열쇠
    tool: str
    origin: str  # record, sales, shelf, web
    text: str  # 카드의 글(정확한 숫자)
    source: str  # 카드의 출처(이름과 건수)
    said_source: str  # 말에 붙이는 출처의 이름
    fact: str  # 말할 사실(말로 바꾼 숫자)
    sentence: str  # 글틀 문장
    names: list[str] = field(default_factory=list)  # 말에 써도 되는 이름(숫자 검사)
    caution: str | None = None  # 말에서 꼭 할 주의
    url: str | None = None
    date: str | None = None
    note: str | None = None  # 카드의 주의
    extra: dict[str, Any] = field(default_factory=dict)

    def evidence(self, idx: int) -> dict[str, Any]:
        item = {"id": f"ev-{idx}", "origin": self.origin, "text": self.text, "source": self.source}
        for k in ("url", "date", "note"):
            v = getattr(self, k)
            if v:
                item[k] = v
        return item


def run(tool: str, arg: str, note: Note) -> list[Found]:
    fn = {"who": who, "when": when, "with_food": with_food, "by_job": by_job, "shelf": shelf_count,
          "sales": sales, "purchase_outcomes": purchase_outcomes}.get(tool)
    if fn is None:
        return []
    try:
        return fn(note, arg)
    except (KeyError, ValueError, ZeroDivisionError):
        return []


# ---------- 작은 도움 ----------


def purchase_outcomes(note: Note, arg: str = "") -> list[Found]:
    data = purchase.outcomes()
    term = "".join(arg.split()).casefold()
    rows = data["history"]
    if term:
        candidates = [*data["concepts"], *rows]
        rows = [r for r in candidates if term in "".join(r["product"].split()).casefold()]
    out = []
    for row in rows:
        name = row["product"]
        source = "정량 컨셉 조사" if "intent_method" in row else f"{row['test_year']}년 컨셉테스트와 출시 실적"
        text = f"{name} · " + ", ".join(purchase.measure_lines(row))
        out.append(Found(key=f"purchase:{name}:{source}", tool="purchase_outcomes", origin="internal", text=text,
                         source=source, said_source=source, fact=text, sentence=text + ".", names=[name]))
    return out


def _than(note: Note) -> str:
    return "다른 술" if note.kind in consumer.ALCOHOL_KINDS else "다른 음료"


def _subject(note: Note) -> tuple[str, str]:
    """(말의 주어가 되는 종류의 이름, 글틀 앞머리). 제품이 조사의 종류와 다르면 그렇게 밝힌다."""
    kn = note.kind_name or ""
    if note.same_kind or not note.product.value:
        return kn, f"{RECORD_SAID}{josa(RECORD_SAID, '을/를')} 찾아보니"
    p = note.product.value
    return kn, f"{p}만 따로 본 조사는 없어서 {RECORD_SAID}에서 {kn} 쪽으로 찾아보니"


def _not_same_fact(note: Note) -> list[str]:
    if note.same_kind or not note.product.value:
        return []
    return [f"({note.product.value}만 따로 본 조사는 없어서 {note.kind_name}{josa(note.kind_name or '', '을/를')} "
            "마시는 사람들로 대신 봤다)"]


def _is(share_word: str) -> str:
    """'열에 넷' → '열에 넷이더라고요'."""
    return {"절반 넘게": "절반이 넘더라고요", "거의 다": "거의 다 그렇더라고요",
            "열에 하나도 안 되게": "열에 하나도 안 되더라고요"}.get(share_word, f"{share_word}이더라고요")


def _share_subject(w: str) -> str:
    """'열에 아홉' → '열에 아홉은'. '절반 넘게', '거의 다'에는 조사를 붙이지 않는다."""
    return w if w.endswith(("게", "다")) else f"{w}{josa(w, '은/는')}"


def _target_group(note: Note) -> Group:
    if note.group is not None:
        return note.group
    if note.kind:
        rows = consumer.top_groups(note.kind, 1)
        if rows and rows[0].n >= MIN_FOUND:
            return rows[0].group
    return Group(label="전체")


# ---------- 도구 ----------


def who(note: Note, arg: str = "") -> list[Found]:
    if not note.kind:
        return []
    rows = consumer.top_groups(note.kind, 2)
    if not rows or rows[0].n < MIN_FOUND:
        return []
    top = rows[0]
    kn, head = _subject(note)
    than, grp = _than(note), top.group.label
    t = spoken.times(top.ratio)
    if t == "비슷하게":
        fact = f"{kn}{josa(kn, '은/는')} 나이대에 따라 마시는 정도가 크게 다르지 않다"
        sentence = f"{head} {kn}{josa(kn, '은/는')} 나이대에 따라 크게 다르지 않더라고요."
    else:
        fact = f"{kn}{josa(kn, '은/는')} {grp}{josa(grp, '이/가')} {than}보다 {t} 자주 마신다"
        sentence = f"{head} {kn}{josa(kn, '은/는')} {grp}{josa(grp, '이/가')} {than}보다 {t} 자주 마시더라고요."
    caution = None
    if top.small:
        caution = f"{grp}{josa(grp, '은/는')} 조사된 사람이 적어서 참고만 해 달라고 말한다"
        sentence = sentence.removesuffix("마시더라고요.") + "마시는데, 조사된 사람이 적어서 참고만 해 주세요."
    pairs = [(r.group.label, r.ratio) for r in rows]
    return [Found(key="who", tool="who", origin="record", text=P.ev_who(kn, pairs, than),
                  source=P.source_record_groups([(r.group.label, r.n) for r in rows]), said_source=RECORD_SAID,
                  fact="; ".join(_not_same_fact(note) + [fact]), sentence=sentence, names=[grp, kn],
                  caution=caution, note=P.SMALL_SAMPLE if any(r.small for r in rows) else None,
                  extra={"group": top.group})]


def when(note: Note, arg: str = "") -> list[Found]:
    if not note.kind:
        return []
    kn, head = _subject(note)
    group = _target_group(note)
    band = consumer.band_in(arg) or consumer.band_in(note.thoughts[-1] if note.thoughts else None)
    if band:
        got = consumer.time_share(note.kind, group, band)
        if not got or got[1] < MIN_FOUND:
            group = Group(label="전체")
            got = consumer.time_share(note.kind, group, band)
        if not got or got[1] < MIN_FOUND:
            return []
        pct, n = got
        label = consumer.record_group_label(group)
        who_ = "" if label == "전체" else f"{label}{josa(label, '이/가')} "
        w = spoken.share(pct)
        fact = f"{who_}{kn}{josa(kn, '을/를')} {band}에 마시는 경우는 전체 음용 사례의 {w}"
        sentence = f"{head} {who_}{kn}{josa(kn, '을/를')} {band}에 마시는 경우는 {_is(w)}."
        return [Found(key=f"when:{band}", tool="when", origin="record",
                      text=f"{'' if label == '전체' else label + '의 '}{kn} 음용 사례 가운데 {band}: {pct:.1f}%",
                      source=P.source_record(n), said_source=RECORD_SAID,
                      fact="; ".join(_not_same_fact(note) + [fact]), sentence=sentence, names=[label, kn, band],
                      note=P.SMALL_SAMPLE if n < consumer.SMALL_SAMPLE else None)]
    w = consumer.when(note.kind, group)
    if "시간대" not in w or w["시간대"].n < MIN_FOUND:
        group = Group(label="전체")
        w = consumer.when(note.kind, group)
    if "시간대" not in w or w["시간대"].n < MIN_FOUND:
        return []
    n = w["시간대"].n
    label = consumer.record_group_label(group)
    subj = "" if label == "전체" else f"{label}{josa(label, '은/는')} "
    words = [spoken.when_word("시간대", w["시간대"].raw)]
    if "장소" in w:
        words.append(spoken.when_word("장소", w["장소"].raw))
    where = " ".join(x for x in words if x)
    facts = [f"{subj}{kn}{josa(kn, '을/를')} 주로 {where} 마신다"]
    food = consumer.food_share(note.kind, group)
    if food is not None:
        if food >= 50:
            facts.append(f"{_share_subject(spoken.share(food))} 밥 먹을 때 마신다")
        else:
            facts.append(f"{_share_subject(spoken.share(100 - food))} 음료만 마실 때 마신다")
    items = [(w[a].value, w[a].pct) for a in ("시간대", "장소", "동반", "음식 동반") if a in w]
    sentence = f"{head} {subj}{kn}{josa(kn, '을/를')} 주로 {where} 마시더라고요."
    return [Found(key="when", tool="when", origin="record", text=P.ev_when(label, kn, items),
                  source=P.source_record(n), said_source=RECORD_SAID,
                  fact="; ".join(_not_same_fact(note) + facts), sentence=sentence, names=[label, kn],
                  note=P.SMALL_SAMPLE if n < consumer.SMALL_SAMPLE else None)]


def with_food(note: Note, arg: str = "") -> list[Found]:
    if not note.kind:
        return []
    wf = consumer.with_food(note.kind, note.group)
    if wf is None:
        return []
    kn, head = _subject(note)
    top = [f.food for f in wf.mains[:3]]
    who_ = "" if wf.group == "전체" else f"{wf.group}{josa(wf.group, '이/가')} "
    listed = ", ".join(top)
    fact = f"{who_}{kn}{josa(kn, '을/를')} 마신 끼니에 함께 먹은 것은 {listed} 순이다"
    if len(top) > 1:
        sentence = (f"{head} {who_}{kn}{josa(kn, '을/를')} {', '.join(top[:-1])}, {top[-1]}{josa(top[-1], '과/와')} "
                    "함께 마신 끼니가 많더라고요.")
    else:
        sentence = f"{head} {who_}{kn}{josa(kn, '을/를')} {top[0]}{josa(top[0], '과/와')} 함께 마신 끼니가 많더라고요."
    text = f"{who_}{kn}{josa(kn, '을/를')} 마신 끼니에 함께 먹은 것: " + ", ".join(f"{f.food} {f.pct:.1f}%" for f in wf.mains[:5])
    if wf.sides:
        text += " (곁들인 것: " + ", ".join(f.food for f in wf.sides[:3]) + ")"
    return [Found(key="with_food", tool="with_food", origin="record", text=text,
                  source=f"2024 국민건강영양조사 식품섭취조사, 끼니 {wf.base:,}건", said_source=RECORD_SAID,
                  fact="; ".join(_not_same_fact(note) + [fact]), sentence=sentence, names=[wf.group, kn, *top],
                  note=P.SMALL_SAMPLE if wf.base < consumer.SMALL_SAMPLE else None)]


def by_job(note: Note, arg: str = "") -> list[Found]:
    if not note.kind:
        return []
    rows = consumer.by_job(note.kind)
    if not rows:
        return []
    kn, head = _subject(note)
    than = _than(note)
    top = rows[0]
    t = spoken.times(top.ratio)
    if t == "비슷하게":
        fact = f"{kn}{josa(kn, '은/는')} 하는 일에 따라 마시는 정도가 크게 다르지 않다"
        sentence = f"{head} {kn}{josa(kn, '은/는')} 하는 일에 따라 크게 다르지 않더라고요."
    else:
        fact = f"{kn}{josa(kn, '은/는')} {top.spoken}{josa(top.spoken, '이/가')} {than}보다 {t} 자주 마신다"
        sentence = f"{head} {kn}{josa(kn, '은/는')} {top.spoken}{josa(top.spoken, '이/가')} {than}보다 {t} 자주 마시더라고요."
    text = f"{kn}{josa(kn, '은/는')} {than}보다 " + ", ".join(f"{r.name} {r.ratio:.1f}배" for r in rows[:2]) + " 자주 마셔요"
    return [Found(key="by_job", tool="by_job", origin="record", text=text,
                  source=f"2024 국민건강영양조사 식품섭취조사, 마신 끼니 " + ", ".join(f"{r.name} {r.n:,}건" for r in rows[:2]),
                  said_source=RECORD_SAID, fact="; ".join(_not_same_fact(note) + [fact]), sentence=sentence,
                  names=[top.spoken, kn], note=P.SMALL_SAMPLE if top.n < consumer.SMALL_SAMPLE else None)]


def shelf_count(note: Note, arg: str = "") -> list[Found]:
    need = shelf.find_need(arg, note.shelf) or shelf.find_need(note.need.value, note.shelf)
    if need is None and note.occasion_code:
        top = consumer.needs(note.occasion_code)
        need = shelf.needs().get(top[0].code) if top else None
    if need is not None:
        c = shelf.need_count(need, note.shelf)
        if c.total < MIN_FOUND:
            return []
        if c.filled:
            w = spoken.share(100 * c.filled / c.total)
            fact = (f"편의점 {note.shelf} 매대에서 '{need.name}'({need.desc})에 잘 맞는 제품은 {w}이고, "
                    f"그 가운데 롯데칠성 제품은 {spoken.share(100 * c.ours / c.filled)}")
            sentence = f"편의점 {note.shelf} 매대를 보니 '{need.name}'에 맞는 제품이 {_is(w)}."
        else:
            fact = f"편의점 {note.shelf} 매대에 '{need.name}'({need.desc})에 잘 맞는 제품은 하나도 없다(비어 있는 자리)"
            sentence = f"편의점 {note.shelf} 매대를 보니 '{need.name}'에 맞는 제품은 하나도 없더라고요."
        text = (f"편의점 {note.shelf} 매대 {c.total}개 가운데 '{need.name}'에 잘 맞는 제품 {c.filled}개, "
                f"그 가운데 롯데칠성 제품 {c.ours}개")
        return [Found(key=f"shelf:{need.code}", tool="shelf", origin="shelf", text=text, source=shelf.SHELF_SOURCE,
                      said_source=f"편의점 {note.shelf} 매대", fact=fact, sentence=sentence, names=[need.name, note.shelf])]
    if not note.shelf_kind:
        return []
    k = shelf.kind_count(note.shelf_kind)
    if k is None or k.total < MIN_FOUND:
        return []
    w = spoken.share(100 * k.same / k.total)
    fact = (f"편의점 {k.shelf} 매대에서 {k.kind} 제품은 {w}이고, 그 가운데 롯데칠성 제품은 "
            f"{spoken.share(100 * k.ours / k.same)}")
    sentence = f"편의점 {k.shelf} 매대를 보니 {k.kind} 제품이 {_is(w)}."
    text = f"편의점 {k.shelf} 매대 {k.total}개 가운데 {k.kind} {k.same}개, 그 가운데 롯데칠성 제품 {k.ours}개"
    return [Found(key="shelf", tool="shelf", origin="shelf", text=text, source=shelf.SHELF_SOURCE,
                  said_source=f"편의점 {k.shelf} 매대", fact=fact, sentence=sentence, names=[k.kind, k.shelf])]


def sales(note: Note, arg: str = "") -> list[Found]:
    s = shelf.sales(note.kind)
    if s is None:
        return []
    ch = s.change
    if abs(ch) < 1:
        word, said = "그 전해와 거의 같았다", "그 전해와 거의 같더라고요"
    elif ch > 0:
        word, said = "그 전해보다 늘었다", "그 전해보다 늘었더라고요"
    else:
        word, said = "그 전해보다 줄었다", "그 전해보다 줄었더라고요"
    fact = (f"편의점 {s.name} 매출은 2025년에 {word}; 편의점 {s.shelf} 매출 가운데 {spoken.share(s.share25)}를 차지한다")
    sentence = f"{SALES_SAID}를 찾아보니 편의점 {s.name} 매출은 2025년에 {said}."
    text = (f"편의점 {s.name} 매출: 2024년 {s.y24:,}백만 원, 2025년 {s.y25:,}백만 원({ch:+.1f}%). "
            f"편의점 {s.shelf} 매출의 {s.share25:.1f}%")
    return [Found(key="sales", tool="sales", origin="sales", text=text, source=shelf.SALES_SOURCE,
                  said_source=SALES_SAID, fact=fact, sentence=sentence, names=["2025", s.name],
                  note="품목 매출에 편의점 비중을 곱한 값이에요")]


def news(claims: list[web.Claim]) -> list[Found]:
    out = []
    for c in claims:
        body = c.text.rstrip(". ")
        out.append(Found(key=f"news:{c.url}", tool="news", origin="web", text=c.text, source=c.source,
                         said_source=c.source, fact=c.text, sentence=f"{c.source} 기사를 보니 {body}.",
                         names=[c.source], url=c.url, date=c.date, note=c.note))
    return out
