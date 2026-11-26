"""매대 테스트 안에서 전 연령 탐색과 타깃 선택을 진행한다."""

from __future__ import annotations

from agent.note import Note
from agent import phrases as P
from events import ActionItem, Actions, Card, Choices, Option, Say, Stage
from shelftest import runner
from shelftest.explore import AGES, CELLS, MIN_AXIS_N, SEXES
from tools.consumer import AGE_NAMES, josa

START, SKIP, RESULT = "explore-start", "explore-skip", "explore-result"
TARGET = "explore-target/"
LABELS = {START: "전 연령으로 테스트하기", SKIP: "기존 타깃으로 바로 테스트하기", RESULT: "탐색 결과 보기"}


def command(ids: list[str], text: str, note: Note) -> str | None:
    if ids:
        value = ids[0]
        return value if value in LABELS or value.startswith(TARGET) else None
    offer = note.last_offer
    choices = offer.options if isinstance(offer, Choices) else offer.actions if isinstance(offer, Actions) else []
    return next((x.id for x in choices if x.label == text.strip() and
                 (x.id in LABELS or x.id.startswith(TARGET))), None)


def entry(n: Note, concept: dict) -> list:
    from agent.machine import _end

    n.shelf_pending = concept["id"]
    concept["_shelf_flow"] = {"step": "entry"}
    total = len(CELLS) * runner.explore_per_cell()
    offer = Actions(id=n.next_id("shelf-path"), actions=[
        ActionItem(id=START, label=LABELS[START], primary=True),
        ActionItem(id=SKIP, label=LABELS[SKIP]),
        ActionItem(id="shelf-cancel", label="그만두기"),
    ])
    name = concept["name"]
    return [Stage(current="shelf"), *_end(n, f"먼저 19~59세 소비자 {total:,}명에게 {name}{josa(name, '을/를')} "
            "보여주고, 어떤 손님이 가장 많이 고르는지 볼까요?", offer)]


def _label(age: str | None, sex: str | None) -> str:
    age_text = f"{age.replace('-', '~')}세" if age in AGES.values() else AGE_NAMES.get(age, "")
    return " ".join(filter(None, [age_text, {"남자": "남성", "여자": "여성"}.get(sex)])) or "전체 소비자"


def _pct(rate: float) -> str:
    return f"{rate:g}%"


def _group_text(g: dict) -> str:
    return f"{g['label']} {g['n']:,}명 중 {g['picked']:,}명({_pct(g['rate'])})"


def _spread(axis: dict) -> str:
    rates = sorted(round(g["rate"]) for g in axis["groups"])
    return f"{rates[0]}%" if rates[0] == rates[-1] else f"{rates[0]}~{rates[-1]}%"


def _ends(axis: dict) -> tuple[dict, dict]:
    ordered = sorted(axis["groups"], key=lambda g: g["picked"] / g["n"], reverse=True)
    return ordered[0], ordered[-1]


def axis_finding(study: dict, age: str | None, sex: str | None) -> dict | None:
    """탐색 결과를 성별·연령대 축으로 말한다. 판정이 없으면 None."""
    axes = study.get("axes")
    if not axes or axes["sex"]["clear"] is None or axes["age"]["clear"] is None:
        return None
    sex_axis, age_axis = axes["sex"], axes["age"]
    names = {"sex": "성별로는", "age": "연령대별로는"}
    clear = [a for a in (sex_axis, age_axis) if a["clear"]]
    if not clear:
        n = sum(g["n"] for g in sex_axis["groups"])
        k = sum(g["picked"] for g in sex_axis["groups"])
        text = (f"연령대와 성별 어느 쪽으로도 뚜렷한 차이가 없었어요. "
                f"전체로는 {n:,}명 중 {k:,}명({_pct(round(100 * k / n, 1) if n else 0)})이 골랐어요.")
    else:
        heads = []
        details = []
        for axis in clear:
            hi, lo = _ends(axis)
            heads.append(f"{hi['label']}{josa(hi['label'], '이/가')} {lo['label']}보다")
            details.append(f"{_group_text(hi)}, {_group_text(lo)}이에요.")
        text = f"{', '.join(heads)} 많이 골랐어요. " + " ".join(details)
        if len(clear) == 1:
            other = age_axis if clear[0] is sex_axis else sex_axis
            text += f" {names[other['axis']]} 차이가 없었어요({_spread(other)})."
    # 원래 타깃이 뚜렷하게 갈린 축에서 가장 낮은 쪽이면 그 축만 가장 높은 쪽으로 바꿔 권한다.
    rec_age, rec_sex, low = age, sex, []
    if sex_axis["clear"]:
        hi, lo = _ends(sex_axis)
        if sex == lo["key"]:
            rec_sex, low = hi["key"], [*low, (lo["label"], hi["label"])]
    if age_axis["clear"]:
        hi, lo = _ends(age_axis)
        if age == lo["key"]:
            rec_age, low = hi["key"], [*low, (lo["label"], hi["label"])]
    # 뚜렷하게 갈린 축의 가장 높은 그룹을 다른 대상으로도 보인다(원래 타깃의 다른 축은 그대로, 또는 전 연령·남녀 모두).
    extra = []
    for axis in clear:
        hi, _ = _ends(axis)
        pairs = [(age, hi["key"]), (None, hi["key"])] if axis is sex_axis else [(hi["key"], sex), (hi["key"], None)]
        extra += [p for p in pairs if p not in extra and p not in ((age, sex), (rec_age, rec_sex))]
    return {"text": text, "recommend": (rec_age, rec_sex), "low": low, "extra": extra}


def _few_answers(study: dict) -> bool:
    """성별·연령대 어느 그룹이라도 결론을 낼 만큼(MIN_AXIS_N) 답하지 않았는가."""
    axes = study.get("axes") or {}
    groups = [g for axis in axes.values() for g in axis.get("groups", [])]
    return not groups or any(g["n"] < MIN_AXIS_N for g in groups)


def _offer_targets(n: Note, run_id: str, study: dict, spec: runner.Spec, lead: str | None = None) -> list:
    """탐색 결과로 다음 타깃을 고르게 한다. lead가 있으면(멈춘 탐색) 말의 첫머리에 붙이고,
    답이 적으면 어느 그룹이 낫다고 말하지 않는다."""
    from agent.machine import _end

    original = _label(spec.age, spec.sex)
    if lead is not None and _few_answers(study):
        prefix = f"{TARGET}{run_id}/"
        options = [Option(id=prefix + "board", label=original + " (추천)"),
                   Option(id=prefix + "ages", label="다른 대상 고르기")]
        next_step = f"본 테스트는 원래 타깃인 {original} {spec.total:,}명에게 해볼 수 있어요. 누구에게 물어볼까요?"
        return _end(n, f"{lead} {P.FEW_ANSWERS}\n\n{next_step}",
                    Choices(id=n.next_id("explore-target"), kind="single", options=options))
    axis = axis_finding(study, spec.age, spec.sex)
    if axis is not None:
        out = _offer_by_axes(n, run_id, axis, spec, original)
        return _lead(n, out, lead)
    cells = study["cells"]
    measured = [c for c in cells if c["n"]]
    best = max((c["picked"] / c["n"] for c in measured), default=0)
    leaders = [c for c in measured if best and c["picked"] / c["n"] == best]
    leader = leaders[0] if len(leaders) == 1 else None
    if leader:
        who = _label(leader["age"], leader["sex"])
        finding = (f"{who}의 구매 반응이 가장 좋았어요. "
                   f"{leader['n']}명 중 {leader['picked']}명({leader['rate']:g}%)이 골랐어요.")
    elif leaders:
        if len(leaders) == 2:
            a, b = (_label(c["age"], c["sex"]) for c in leaders)
            finding = f"{a}{josa(a, '과/와')} {b}의 선택률이 {leaders[0]['rate']:g}%로 함께 가장 높았어요."
        else:
            finding = f"가장 높은 선택률은 {leaders[0]['rate']:g}%였고, {len(leaders)}개 그룹이 같았어요."
        finding += " 어느 한쪽의 구매 반응이 더 좋다고 보기는 어려워요."
    else:
        finding = "이번에 응답한 손님 중 이 제품을 고른 사람은 없었어요." if measured else "응답이 없어 구매 반응을 비교할 수 없었어요."
    if measured and len(measured) < len(cells):
        finding += " 일부 그룹은 응답이 없어 전체를 비교하기 어려워요."
    elif leader:
        finding += (" 다른 그룹보다 선택률이 높아요." if study["suggested"]
                    else " 다만 다른 그룹과 차이가 뚜렷하지 않아요.")

    prefix = f"{TARGET}{run_id}/"
    board = Option(id=prefix + "board", label=original)
    options = [board]
    recipient = f"원래 타깃인 {original}"
    if leader and (leader["age"], leader["sex"]) != (spec.age, spec.sex):
        other = Option(id=prefix + leader["age"] + "/" + leader["sex"], label=who)
        if study["suggested"]:
            options = [other, board]
            finding += f" 원래 타깃은 {original}{josa(original, '이에요/예요')}."
            recipient = who
        else:
            options.append(other)
    options[0].label += " (추천)"
    options.append(Option(id=prefix + "ages", label="다른 대상 고르기"))
    next_step = f"본 테스트는 {recipient} {spec.total:,}명에게 해보길 추천해요. 누구에게 물어볼까요?"
    return _lead(n, _end(n, f"{finding}\n\n{next_step}",
                         Choices(id=n.next_id("explore-target"), kind="single", options=options)), lead)


def _lead(n: Note, events: list, lead: str | None) -> list:
    """첫 말의 앞에 lead를 붙인다(멈춘 탐색의 "N명 중 M명에서 멈췄어요")."""
    if not lead:
        return events
    out = []
    for ev in events:
        if isinstance(ev, Say) and lead:
            ev = Say(text=f"{lead} {ev.text}")
            n.last_say = ev.text
            if n.said_before:
                n.said_before = [*n.said_before[:-1], ev.text]
            lead = None
        out.append(ev)
    return out


def _offer_by_axes(n: Note, run_id: str, axis: dict, spec: runner.Spec, original: str) -> list:
    from agent.machine import _end

    prefix = f"{TARGET}{run_id}/"
    board = Option(id=prefix + "board", label=original)
    rec_age, rec_sex = axis["recommend"]
    if (rec_age, rec_sex) == (spec.age, spec.sex):
        options = [board]
        board.label += " (추천)"
        next_step = (f"원래 타깃인 {original}{josa(original, '으로/로')} "
                     "본 테스트를 해도 좋아요. 누구에게 물어볼까요?")
    else:
        who = _label(rec_age, rec_sex)
        options = [Option(id=f"{prefix}group/{rec_age or '*'}/{rec_sex or '*'}", label=who + " (추천)"), board]
        lows = "고, ".join(f"{lo}{josa(lo, '은/는')} {hi}보다" for lo, hi in axis["low"])
        next_step = (f"원래 타깃은 {original}인데, {lows} 적게 골랐어요. "
                     f"본 테스트는 {who} {spec.total:,}명에게 해보길 추천해요. 누구에게 물어볼까요?")
    for age, sex in axis["extra"]:
        label = _label(age, sex) + (" (전 연령)" if age is None else "")
        options.append(Option(id=f"{prefix}group/{age or '*'}/{sex or '*'}", label=label))
    options.append(Option(id=prefix + "ages", label="다른 대상 고르기"))
    return _end(n, f"{axis['text']}\n\n{next_step}",
                Choices(id=n.next_id("explore-target"), kind="single", options=options))


def respond(n: Note, concept: dict, spec: runner.Spec, action: str, ids: list[str]) -> list | None:
    """타깃 확정을 눌렀으면 spec을 채워 공통 실행 경로로 넘긴다."""
    from agent.machine import _end

    flow = concept.get("_shelf_flow") or {}
    step, run_id = flow.get("step"), flow.get("run_id")
    if action == START and step == "entry":
        spec.mode = "explore"
        run_id = runner.create(spec)
        concept["_shelf_flow"] = {"step": "exploring", "run_id": run_id}
        card = Card(id=f"explore-{run_id}", stage="shelf", kind="explore", title="전 연령 탐색 테스트",
                    status="ready", payload={"run_id": run_id})
        return [Stage(current="shelf"), card, *_end(n, "손님들이 매대에서 어떤 음료를 고르는지 보고 있어요.", None)]
    if action == RESULT and run_id and ids[1:] == [run_id] and step in ("exploring", "choose"):
        view = runner.view(run_id)
        if view and view["status"] == "stopped":  # 멈춘 탐색: 지금까지 답한 손님으로 말한다(11-25)
            if not view["asked"] or not view.get("explore"):
                return _end(n, P.STOPPED_EMPTY, None)
            flow["step"] = "choose"
            return _offer_targets(n, run_id, view["explore"], spec,
                                  lead=P.stopped_line(int(view["asked"]), int(view["total"])))
        if view and view["status"] == "done" and view.get("explore"):
            flow["step"] = "choose"
            return _offer_targets(n, run_id, view["explore"], spec)
        return _end(n, "아직 탐색 결과를 열 수 없어요. 매대 카드에서 진행 상황을 확인해 주세요.", None)
    if step == "choose" and run_id and action.startswith(f"{TARGET}{run_id}/"):
        choice = action.removeprefix(f"{TARGET}{run_id}/")
        prefix = f"{TARGET}{run_id}/"
        if choice == "ages":
            options = [Option(id=f"{prefix}age/{age}", label=label) for label, age in AGES.items()]
            return _end(n, "다음 테스트의 연령대를 골라 주세요.",
                        Choices(id=n.next_id("target-age"), kind="single", options=options))
        if choice.startswith("age/") and choice[4:] in AGES.values():
            age = choice[4:]
            options = [Option(id=f"{prefix}{age}/{sex}", label=_label(age, sex)) for sex in SEXES.values()]
            return _end(n, "이 연령대에서 누구에게 물어볼까요?",
                        Choices(id=n.next_id("target-sex"), kind="single", options=options))
        if choice.startswith("group/"):
            parts = choice.split("/")[1:]
            age, sex = (None if v == "*" else v for v in (parts + ["*", "*"])[:2])
            if len(parts) != 2 or (age, sex) == (None, None) or age not in (None, *AGES.values()) \
                    or sex not in (None, *SEXES.values()):
                return _end(n, "탐색 결과에 있는 집단을 골라 주세요.", n.last_offer)
            spec.age, spec.sex = age, sex
            spec.target_basis = f"전 연령 탐색 후 기획자가 {_label(age, sex)} 집단을 선택함"
        elif choice == "board":
            spec.target_basis = "전 연령 탐색 후 컨셉 보드의 기존 타깃을 선택함"
        else:
            selected = tuple(choice.split("/"))
            if selected not in CELLS:
                return _end(n, "탐색 결과에 있는 집단을 골라 주세요.", n.last_offer)
            spec.age, spec.sex = selected
            spec.target_basis = f"전 연령 탐색 후 기획자가 {_label(spec.age, spec.sex)} 집단을 선택함"
        study = runner.view(run_id)["explore"]
        cells = [c for c in study["cells"] if spec.age in (None, c["age"]) and spec.sex in (None, c["sex"])]
        answered, picked = sum(c["n"] for c in cells), sum(c["picked"] for c in cells)
        spec.target_basis += f" (탐색 응답 {answered}명 중 {picked}명 선택)" if answered else " (탐색 응답 없음)"
        spec.explore_id = run_id
        return None
    return _end(n, "현재 매대 테스트의 선택지를 확인해 주세요.", n.last_offer)
