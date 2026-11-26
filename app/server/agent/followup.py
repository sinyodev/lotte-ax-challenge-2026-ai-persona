"""후속 개선의 대화 (약속 v1.20): 조사 확인 → 가상 소비자 맞추기 → 다시 테스트 → 개선안.

모델을 부르지 않는다. 숫자와 판정은 calibrate/followup.py가 세고, 말은 이 파일의 글틀에서 나온다.
버튼은 id 하나만 보내므로 "apply:<upload_id>" 꼴로 낸다. 화면이 ["apply", upload_id]로 보내도 같은 길로 간다.
"""

from __future__ import annotations

import math
from collections.abc import AsyncIterator
from typing import Any

from agent import phrases as P
from agent.note import Note
from calibrate import followup as data
from calibrate import overlay
from events import ActionItem, Actions, Card, Stage
from tools import spoken
from tools.consumer import josa

TO = "followup"
UPLOAD = "upload-survey"
APPLY_RETEST = "apply-retest"  # 맞추기와 다시 테스트를 한 번에. 옛 대화의 apply, retest도 그대로 받는다
STEPS = ("upload", "apply", APPLY_RETEST, "retest", "retest-result", "ideas", "save")
MIN_GAP = 5  # 100명 중 이만큼은 달라야 "달랐다"고 말한다

CARD_TITLE = "후속 개선"
BTN_UPLOAD = "조사 결과 올리기"
BTN_APPLY_RETEST = "가상 소비자 고치고 다시 테스트"
BTN_RETEST = "다시 테스트하기"
BTN_RETEST_RESULT = "결과 보기"
BTN_IDEAS = "최적화로 나온 개선안 보기"
BTN_FIT = "가상 소비자 최적화"
BTN_SAVE = "가상 소비자 인사이트에 추가"
BTN_SHELF_AGAIN = "매대 테스트 다시 하기"
ASK_FILE = "소비자 조사 결과 파일을 올려 주세요. 엑셀 파일을 대화창에 끌어다 놓아도 돼요."
GONE = "올린 조사 파일을 찾지 못했어요. 조사 결과를 다시 올려 주세요."
APPLY_FIRST = "가상 소비자를 먼저 조사에 맞춰야 해요. 지금 맞춰 볼까요?"
RETEST_NOT_READY = "다시 테스트는 아직 준비 중이에요. 조사에서 나온 개선안부터 볼까요?"
RETEST_FAILED = "다시 테스트를 시작하지 못했어요. 조사에서 나온 개선안부터 볼까요?"
RETEST_STOPPED = "다시 테스트가 중간에 멈췄어요. 이어서 해 볼까요?"
NO_IDEAS = "조사에서 새로 고칠 곳을 찾지 못했어요. 지금 컨셉 그대로 다음 조사를 준비해도 좋아요."


def btn_apply(target: str) -> str:
    return BTN_FIT


# ---------- 말 ----------


def _small(survey: dict[str, Any]) -> str:
    n = survey["n"]["target"]
    return f" 응답이 {n:,}명뿐이라 참고로만 봐 주세요." if n < data.SMALL_N else ""


def _pct(x: float) -> str:
    return f"{math.floor(x + 0.5)}%"  # 화면(copy/followup-report.ts)의 Math.round와 같게


def _won(x: float) -> str:
    return f"{math.floor(x + 0.5):,}원"


def big_gaps(survey: dict[str, Any]) -> list[dict[str, Any]]:
    """예상(가상 소비자)과 실제(조사)가 MIN_GAP 이상 다른 문항, 크게 다른 차례로. 화면의 bigGaps와 같다."""
    gaps = [d for d in survey["diffs"] if d["virtual"] is not None and abs(d["actual"] - d["virtual"]) >= MIN_GAP]
    return sorted(gaps, key=lambda d: -abs(d["actual"] - d["virtual"]))


def _gap_line(d: dict[str, Any], price: int) -> str:
    virtual, actual = d["virtual"], d["actual"]
    if d["id"] == "price":
        if virtual >= 100:
            return f"가격: 저는 모두 {_won(price)}을 낼 거라고 봤는데, 실제로는 {_pct(actual)}만 내겠다고 했어요."
        return f"가격: 저는 {_pct(virtual)}가 {_won(price)}을 낼 거라고 봤는데, 실제로는 {_pct(actual)}였어요."
    if d["id"] == "worry":
        return f"맛: 저는 {_pct(virtual)}가 맛을 걱정할 거라고 봤는데, 실제로는 {_pct(actual)}였어요."
    return ""


def diff_text(survey: dict[str, Any], total: int, *, can_retest: bool = True) -> str:
    """조사를 올린 차례의 말(견본 FollowupProtoPage의 sayOf). total은 처음 테스트의 가상 소비자 수."""
    target, n = survey["target"], survey["n"]
    removed = sum(r["count"] for r in survey["removed"])
    cut = f"중복이거나 성의 없는 답 {removed:,}명을 빼고, " if removed else ""
    read = f"조사 결과를 읽었어요. {n['raw']:,}명 가운데 {cut}{target} {n['target']:,}명의 답을 봤어요.{_small(survey)}"
    gaps = big_gaps(survey)
    if gaps:
        count = {1: "한", 2: "두", 3: "세"}.get(len(gaps), str(len(gaps)))
        lines = [f"제 예상과 {count} 가지가 달랐어요.", *(_gap_line(d, survey["concept"]["price"]) for d in gaps)]
        found = "\n".join(x for x in lines if x)
    else:
        found = "제 예상과 거의 같았어요."
    if can_retest:
        ask = f"실제 {target}의 답에 맞춰 가상 소비자를 고치고, 같은 {total:,}명에게 다시 물어볼까요?"
    else:
        ask = f"실제 {target}의 답에 맞춰 가상 소비자를 최적화할까요?"
    return "\n\n".join([read, found, ask])


def retest_text(p: dict[str, Any], total: int, survey: dict[str, Any]) -> str:
    """다시 테스트가 끝난 차례의 말(견본의 retestSay). 두 번 모두 답한 사람만 견준다."""
    target, name = survey["target"], survey["concept"]["name"]
    scope = "" if p["n"] == total else f"두 번 모두 답한 {p['n']:,}명으로 보면, "
    before, after = p["before"], p["after"]
    how = "으로 같았어요" if after == before else "으로 줄었어요" if after < before else "으로 늘었어요"
    done = (f"다시 테스트가 끝났어요. {scope}실제 {target}의 답에 맞추니 {name}{josa(name, '을/를')} "
            f"고른 사람이 {before:,}명에서 {after:,}명{how}.")
    if p["lost"] and p["gained"]:
        move = f"{p['lost']:,}명이 빠지고 {p['gained']:,}명이 새로 골랐어요."
    elif p["lost"]:
        move = f"{p['lost']:,}명이 빠졌고 새로 고른 사람은 없어요."
    elif p["gained"]:
        move = f"빠진 사람 없이 {p['gained']:,}명이 새로 골랐어요."
    else:
        move = "누가 골랐는지도 그대로예요."
    if not p["clear"] and (p["lost"] or p["gained"]):
        move += " 이 차이는 우연일 수 있어요."
    ask = "빠진 사람을 다시 데려올 개선안을 조사에서 찾아볼까요?" if p["lost"] else "조사에서 나온 개선안도 볼까요?"
    return "\n\n".join([done, move, ask])


# ---------- 조각 ----------


def card(n: Note, survey: dict[str, Any], step: str) -> Card:
    n.followup = {"upload_id": survey["upload_id"], "step": step}
    return Card(id=TO, stage=TO, kind=TO, title=CARD_TITLE, status="ready", payload=view(survey, step, n.improve))


def view(survey: dict[str, Any], step: str, improve: dict[str, Any] | None = None) -> dict[str, Any]:
    """카드의 payload. 개선안 걸음에는 최적화로 나온 개선안(ideas)이 붙는다."""
    out = data.payload(survey, step=step, improve=improve)
    out["ideas"] = ideas_view(survey) if step == "ideas" else []
    return out


def actions(items: list[tuple[str, str]]) -> Actions:
    return Actions(id=TO, actions=[ActionItem(id=i, label=label, primary=(k == 0) or None)
                                   for k, (i, label) in enumerate(items)])


def route(ids: list[str]) -> tuple[str, str]:
    """["apply", id]와 ["apply:id"] 둘 다 받는다."""
    if len(ids) == 1 and ":" in ids[0]:
        ids = ids[0].split(":", 1)
    if len(ids) == 2 and ids[0] in STEPS and data.valid_id(ids[1]):
        return ids[0], ids[1]
    return "", ""


def wants(n: Note, text: str, ids: list[str], reply_to: str | None) -> bool:
    """이 차례를 후속 개선이 맡는가. 다시 테스트 카드가 스스로 보내는 "결과 보기"도 여기로 온다."""
    if reply_to == TO or route(ids)[0] or UPLOAD in ids or (not ids and text.strip() == BTN_UPLOAD):
        return True
    if not ids and text.strip() in (P.BTN_RESULT, P.BTN_EARLY_RESULT) and data.valid_id((n.followup or {}).get("upload_id")):
        st = data.state(n.followup["upload_id"])
        return bool(st.get("retest_run")) and not st.get("told")
    return False


async def handle(n: Note, conv_id: str, ids: list[str], text: str) -> AsyncIterator[Any]:
    from agent.machine import _end

    n.interview = None
    if not ids and text.strip() in (P.BTN_RESULT, P.BTN_EARLY_RESULT) and n.followup:
        step, upload_id = "retest-result", n.followup["upload_id"]
    else:
        step, upload_id = route(ids)
    survey = data.load(upload_id) if data.valid_id(upload_id) else None
    if survey is None or survey["chat_id"] != conv_id:
        for ev in _end(n, GONE if step else ASK_FILE, actions([(UPLOAD, BTN_UPLOAD)])):
            yield ev
        return
    run = {"upload": _upload, "apply": _apply, APPLY_RETEST: _apply_retest, "retest": _retest,
           "retest-result": _retest_result, "ideas": _ideas, "save": _save}[step]
    for ev in run(n, conv_id, survey):
        yield ev


def _upload(n: Note, conv_id: str, survey: dict[str, Any]) -> list[Any]:
    from agent.machine import _end

    uid = survey["upload_id"]
    view = card(n, survey, "diff")
    can = data.can_retest()
    first = (f"{APPLY_RETEST}:{uid}", BTN_APPLY_RETEST) if can else (f"apply:{uid}", btn_apply(survey["target"]))
    text = diff_text(survey, view.payload["track"]["total"], can_retest=can)
    offer = [first, (f"ideas:{uid}", BTN_IDEAS)] if can else [first]
    return [Stage(current=TO), view, *_end(n, text, actions(offer))]


def _fit(survey: dict[str, Any]) -> int | None:
    """가상 소비자를 조사에 맞춘다. 맞춘 사람 수, 처음 테스트가 없으면 None."""
    from shelftest import runner, store

    uid = survey["upload_id"]
    base = store.load_meta(survey["base_run"])
    if base is None:
        return None
    people = runner._assigned(base)
    overlay.build(uid, people)
    if data.state(uid)["step"] == "diff":
        data.set_state(uid, step="applied")
    return len(people)


def fit_text(survey: dict[str, Any], head: str) -> str:
    """가상 소비자를 최적화한 차례의 말: 최적화가 무엇인지, 무엇이 바뀌었는지, 그래서 무엇을 할 수 있는지."""
    fit = data.fitted(survey) or {"n": 0, "diffs": {}}
    price, target = survey["concept"]["price"], survey["target"]
    what = (f"가상 소비자를 최적화했어요. 최적화는 가상 소비자 {fit['n']:,}명의 답을 "
            f"조사에 답한 실제 {target} {survey['n']['target']:,}명과 같은 비율로 맞추는 일이에요.")
    names = {"price": f"가격: {_won(price)}을 내겠다는 가상 소비자가", "worry": "맛: 맛을 걱정하는 가상 소비자가"}
    moved = []
    for d in survey["diffs"]:
        after = fit["diffs"].get(d["id"])
        if d["id"] not in names or d["virtual"] is None or after is None or abs(after - d["virtual"]) < MIN_GAP:
            continue
        way = "줄었어요" if after < d["virtual"] else "늘었어요"
        moved.append(f"{names[d['id']]} {_pct(d['virtual'])}에서 {_pct(after)}로 {way}.")
    if moved:
        count = {1: "한", 2: "두", 3: "세"}.get(len(moved), str(len(moved)))
        change = "\n".join([f"바뀐 것은 {count} 가지예요.", *moved])
    else:
        change = "제 예상이 실제와 거의 같아서 크게 바뀐 곳은 없어요."
    value = (f"이제 가상 소비자가 실제 {target}처럼 망설여서, 어디를 고쳐야 하는지 더 정확히 찾을 수 있어요. "
             "개선안을 찾아볼까요?")
    return "\n\n".join([what, change, value])


def _fitted(survey: dict[str, Any], k: int) -> str:
    target = survey["target"]
    return f"가상 소비자 {k:,}명을 실제 {target}{josa(target, '과/와')} 같은 비율로 맞췄어요."


def _apply_retest(n: Note, conv_id: str, survey: dict[str, Any]) -> list[Any]:
    """가상 소비자 고치고 다시 테스트: 맞추기와 다시 테스트 시작을 한 번에. 다시 테스트를 못 하면 맞추기만."""
    if not data.can_retest():
        return _apply(n, conv_id, survey)
    from agent.machine import _end

    k = _fit(survey)
    if k is None:
        return _end(n, GONE, None)
    return _retest(n, conv_id, survey, head=_fitted(survey, k))


def _apply(n: Note, conv_id: str, survey: dict[str, Any]) -> list[Any]:
    from agent.machine import _end

    uid = survey["upload_id"]
    k = _fit(survey)
    if k is None:
        return _end(n, GONE, None)
    head = _fitted(survey, k)
    if data.can_retest():
        text = f"{head} 처음 결과는 맞추기 전의 것이라 다시 테스트해야 해요. 지금 해 볼까요?"
        offer = actions([(f"retest:{uid}", BTN_RETEST)])
    else:
        text, offer = fit_text(survey, head), actions([(f"ideas:{uid}", BTN_IDEAS)])
    return [Stage(current=TO), card(n, survey, "applied"), *_end(n, text, offer)]


def _retest(n: Note, conv_id: str, survey: dict[str, Any], head: str = "") -> list[Any]:
    from agent.machine import _end, shelf_run_card
    from shelftest import runner, store

    uid = survey["upload_id"]
    ideas = actions([(f"ideas:{uid}", BTN_IDEAS)])
    if not data.can_retest():
        return _end(n, RETEST_NOT_READY, ideas)
    if not overlay.assigned(uid):
        return _end(n, APPLY_FIRST, actions([(f"apply:{uid}", btn_apply(survey["target"]))]))
    base = store.load_meta(survey["base_run"])
    if base is None:
        return _end(n, GONE, None)
    c, t = base["concept"], base["target"]
    spec = runner.Spec(
        chat_id=conv_id, concept_id=base["concept_id"], name=c["name"], container=c["container"], volume=c["volume"],
        price=c["price"], promo=c.get("promo"), age=t.get("age"), sex=t.get("sex"),
        occasion_code=base.get("occasion_code"), total=int(base.get("requested") or base["total"]),
        explore_id=base.get("explore_id"), target_basis=base.get("target_basis"), storage=base.get("storage"),
        features=runner.shelf_items.concept_features(c), season=c.get("season"), launch=c.get("launch"), overlay=uid)
    try:
        run_id = runner.create(spec)
    except ValueError as err:
        return _end(n, str(err), ideas)
    meta = store.load_meta(run_id) or {}
    if run_id == base["id"] or meta.get("overlay") != uid:
        # 조사 답이 끼워지지 않은 테스트를 다시 테스트라고 보이지 않는다
        if run_id != base["id"] and meta.get("status") == "running":
            runner.stop(run_id)
        return _end(n, RETEST_FAILED, ideas)
    data.set_state(uid, step="retest", retest_run=run_id, told=False)
    text = f"가상 소비자 {int(meta['total']):,}명에게 조사를 반영해 다시 묻고 있어요. 끝나면 처음과 무엇이 달라졌는지 볼게요."
    if head:
        text = f"{head} {text}"
    return [Stage(current=TO), card(n, survey, "retest"), shelf_run_card(run_id, meta),
            *_end(n, text, actions([(f"retest-result:{uid}", BTN_RETEST_RESULT)]))]


def _retest_result(n: Note, conv_id: str, survey: dict[str, Any]) -> list[Any]:
    from agent.machine import _end
    from shelftest import runner, store

    uid = survey["upload_id"]
    run_id = data.state(uid).get("retest_run")
    meta = store.load_meta(run_id) if run_id else None
    if meta is None:
        offer = actions([(f"retest:{uid}", BTN_RETEST)] if data.can_retest() else [(f"ideas:{uid}", BTN_IDEAS)])
        return _end(n, "아직 다시 테스트한 결과가 없어요." if data.can_retest() else RETEST_NOT_READY, offer)
    if meta["status"] == "running":
        runner.ensure_running(run_id)
        asked = (data.picks(run_id) or {}).get("n", 0)
        text = f"가상 소비자 {int(meta['total']):,}명 중 {asked:,}명이 다녀갔어요. 다 다녀가면 처음 결과와 나란히 보여 드릴게요."
        return _end(n, text, actions([(f"retest-result:{uid}", BTN_RETEST_RESULT)]))
    p = data.paired(survey["base_run"], run_id) if meta["status"] == "done" else None
    if p is None:
        return _end(n, RETEST_STOPPED, actions([(f"retest:{uid}", BTN_RETEST), (f"ideas:{uid}", BTN_IDEAS)]))
    data.set_state(uid, told=True)
    base_total = (data.picks(survey["base_run"]) or {}).get("n", 0)
    return [Stage(current=TO), card(n, survey, "retest"),
            *_end(n, retest_text(p, base_total, survey), actions([(f"ideas:{uid}", BTN_IDEAS)]))]


# ---------- 개선안 ----------

APPEALS = {
    "추억": "어릴 때 먹던 그 맛", "부드러운 맛 기대": "부드럽게 넘어가는 맛", "맛의 호기심": "처음 만나는 맛",
    "새로운 방식의 호기심": "새롭게 즐기는 방법", "한정판의 매력": "지금만 만나는 한정판", "여름에 시원함": "한여름에 시원하게",
    "디자인": "사진 찍고 싶은 디자인", "진한 맛 기대": "진하게 즐기는 맛", "무난한 맛 기대": "누구나 편하게 즐기는 맛",
    "브랜드 신뢰": "믿고 고르는 맛", "선물하기 좋음": "선물하기 좋은 한 병",
}
FLAVORS = {"강한 단맛": "단맛을 줄인", "인위적인 맛": "인위적인 향을 줄인"}


def survey_ideas(survey: dict[str, Any], base: Any, *, features: bool) -> list[tuple[dict[str, Any], str, str]]:
    """조사에서 나온 안: (바꿀 값, 까닭, 근거의 글). base는 improve.Base. features면 맛과 소구점도 바꿀 수 있다."""
    target, total = survey["target"], survey["n"]["target"]
    head = f"소비자 조사 {target} {total:,}명 중"
    out = []
    wtp, best = survey["wtp"], survey["best_price"]
    if best and best != base.price:
        share = next(x["share"] for x in survey["curve"] if x["price"] == best)
        out.append(({"price": best}, "조사에서 매출이 가장 큰 가격이에요.",
                    f"{head} 가격을 적은 {wtp['n']:,}명에서 {base.price:,}원을 낼 수 있는 사람은 {wtp['able_n']:,}명이에요. "
                    f"{best:,}원은 100명 중 {round(share)}명이 낼 수 있어요."))
    if not features:
        return out
    taste = survey["taste"]
    if taste and taste["n"]:
        counts = {o["text"]: o["n"] for o in survey["opinions"]["bad"]}
        worst = max(taste["labels"], key=lambda label: counts[label])
        flavor = base.features.get("flavor") or "맛"
        if not flavor.startswith(FLAVORS[worst]):
            worries = ", ".join(f"‘{label}’ {counts[label]:,}명" for label in taste["labels"])
            out.append(({"flavor": f"{FLAVORS[worst]} {flavor}"},
                        f"맛을 걱정한 {taste['n']:,}명 중 {taste['intent_n']:,}명만 구매 의향이 있어요.",
                        f"{head} 맛을 걱정한 사람은 {taste['n']:,}명이에요({worries})."))
    good = survey["opinions"]["good"]
    if good:
        top = good[0]
        out.append(({"appeal": APPEALS[top["text"]]},
                    f"‘{top['text']}’{josa(top['text'], '을/를')} 말한 사람은 100명 중 {top['intent']}명이 구매 의향이 있어요.",
                    f"{head} {top['n']:,}명이 ‘{top['text']}’{josa(top['text'], '을/를')} 사고 싶은 이유로 들었어요."))
    return out


def _effect(survey: dict[str, Any], values: dict[str, Any], people: list[dict[str, Any]]) -> dict[str, Any] | None:
    """안 하나가 최적화한 가상 소비자 가운데 누구에게 닿는가(코드가 센다). 테스트한 값이 아니다."""
    if not people:
        return None
    total = len(people)
    if "price" in values:
        priced = [p for p in people if p["wtp"] is not None]
        if not priced:
            return None

        def able(price: int) -> int:
            return round(100 * sum(p["wtp"] >= price for p in priced) / len(priced))

        return {"kind": "price", "before": able(int(survey["concept"]["price"])), "after": able(int(values["price"]))}
    if "flavor" in values:
        labels = set((survey.get("taste") or {}).get("labels") or [])
        return {"kind": "worry", "n": sum(bool(labels & set(p["opinions"])) for p in people), "total": total}
    if "appeal" in values:
        label = next((k for k, v in APPEALS.items() if v == values["appeal"]), None)
        if label is None:
            return None
        return {"kind": "hope", "label": label, "n": sum(label in p["opinions"] for p in people), "total": total}
    return None


def ideas_view(survey: dict[str, Any]) -> list[dict[str, Any]]:
    """최적화로 나온 개선안(카드의 ideas): 바꿀 것, 까닭, 조사의 근거, 닿는 가상 소비자."""
    from agent import improve
    from shelftest import store

    origin = store.load_meta(survey["base_run"])
    if origin is None:
        return []
    base = improve.Base.of(origin["concept"])
    people = list(overlay.assigned(survey["upload_id"]).values())
    out = []
    for values, reason, text in survey_ideas(survey, base, features=bool(origin.get("concept_prompt_version"))):
        if not improve.diff(base, values) or improve.check_values(base, values, price_step=True):
            continue
        d = improve.describe(base, values)
        out.append({"kind": d["kind"], "before": d["before"], "after": d["after"], "change": d["change"],
                    "reason": reason, "evidence": text, "effect": _effect(survey, values, people)})
    return out


def _idea_line(idea: dict[str, Any]) -> str:
    e = idea["effect"] or {}
    line = f"{idea['change']}."
    if e.get("kind") == "price":
        line += f" 낼 수 있는 가상 소비자가 {_pct(e['before'])}에서 {_pct(e['after'])}로 {'늘어요' if e['after'] > e['before'] else '바뀌어요'}."
    elif e.get("kind") == "worry":
        line += f" 맛을 걱정하는 가상 소비자 {e['n']:,}명에게 닿아요."
    elif e.get("kind") == "hope":
        line += f" ‘{e['label']}’{josa(e['label'], '을/를')} 기대하는 가상 소비자 {e['n']:,}명에게 닿아요."
    return line


def _ideas(n: Note, conv_id: str, survey: dict[str, Any]) -> list[Any]:
    """최적화로 나온 개선안. 후속 개선 안에서 끝낸다(개선안 테스트로 넘어가지 않고, 다시 테스트하지 않는다)."""
    from agent.machine import REPORT, _actions, _end
    from shelftest import store

    uid = survey["upload_id"]
    if store.load_meta(survey["base_run"]) is None:
        return _end(n, GONE, None)
    if not overlay.assigned(uid):
        _fit(survey)
    found = ideas_view(survey)
    data.set_state(uid, step="ideas")
    report = _actions(n, "improve", [(REPORT, P.BTN_REPORT)])
    if not found:
        return [Stage(current=TO), card(n, survey, "ideas"), *_end(n, NO_IDEAS, report)]
    k = len(found)
    head = f"최적화한 가상 소비자로 보니 고칠 곳이 {spoken.count(k) if k > 1 else '한'} 가지예요."
    tail = ("아직 매대에서 테스트한 값은 아니에요.\n\n"
            "최적화한 가상 소비자를 가상 소비자 인사이트에 추가할까요? 추가해 두면 다음 조사 결과도 이어서 보정할 수 있어요.")
    text = "\n\n".join([head, "\n".join(_idea_line(i) for i in found), tail])
    offer = _actions(n, "followup-next", [(f"save:{uid}", BTN_SAVE)])
    return [Stage(current=TO), card(n, survey, "ideas"), *_end(n, text, offer)]


CYCLE = "매대 테스트 → 제안서 → 실제 소비자 조사 → 조사 결과 올리기 → 가상 소비자 최적화 → 다시 매대 테스트"


def _save(n: Note, conv_id: str, survey: dict[str, Any]) -> list[Any]:
    """최적화한 가상 소비자를 가상 소비자 인사이트에 남기고, 보정이 이어지는 순서를 알린 뒤 매대 테스트로 돌아가게 한다."""
    from agent.machine import REPORT, _actions, _end

    if not overlay.assigned(survey["upload_id"]):
        _fit(survey)
    row = data.save_insight(survey)
    if row is None:
        return _end(n, GONE, None)
    target = survey["target"]
    text = "\n\n".join([
        f"가상 소비자 인사이트에 추가했어요. 실제 {target} {row['survey_n']:,}명의 답에 맞춘 가상 소비자 {row['people']:,}명의 기록이 남아요.",
        f"보정은 이렇게 이어져요.\n{CYCLE}\n조사를 올릴 때마다 가상 소비자가 실제 소비자에 더 가까워져요.",
        "개선안을 반영해 매대 테스트를 다시 해 볼까요?",
    ])
    offer = _actions(n, "followup-next", [("go-shelf", BTN_SHELF_AGAIN), (REPORT, P.BTN_REPORT)])
    return [Stage(current=TO), card(n, survey, "ideas"), *_end(n, text, offer)]
