"""전 연령 탐색을 성별·연령대 축으로 묶어 판정하고 칠성이가 그 판정대로 말하는지 본다(지어낸 집계)."""

from agent import explore as agent_explore
from agent.note import Note
from agent.voice import BANNED_WORDS
from shelftest import explore, runner

LINE = "견본 음료"


def _meta(status="done"):
    return {"status": status, "line": LINE, "participants": [], "population_weights": None}


def _study(picks: dict, per_cell=40, status="done", answered=None):
    """picks: {(age, sex): 고른 수}. answered가 있으면 칸마다 그만큼만 응답한 것으로 한다."""
    meta, pairs = _meta(status), []
    for age, sex in explore.CELLS:
        for j in range(per_cell):
            v = f"{age}-{sex}-{j}"
            meta["participants"].append({"visit": v, "age": age, "sex": sex})
            if answered is not None and j >= answered:
                continue
            chose = j < picks.get((age, sex), 0)
            pairs.append((None, {"visit": v, "occasion": "D1", "product": LINE if chose else "기존"}))
    return explore.summarize(meta, pairs)


# 참가자가 본 실행과 같은 모양의 집계: 여성 51/160, 남성 29/160, 연령대 21·20·19·20
SEX_SPLIT = {("19-29", "여자"): 13, ("19-29", "남자"): 8, ("30-39", "여자"): 13, ("30-39", "남자"): 7,
             ("40-49", "여자"): 12, ("40-49", "남자"): 7, ("50-59", "여자"): 13, ("50-59", "남자"): 7}


def _spec(age="19-29", sex=None):
    return runner.Spec(chat_id="c", concept_id="a", name="n", container="캔", volume=250, price=1000,
                       age=age, sex=sex, total=300)


def _say(study, spec):
    events = agent_explore._offer_targets(Note(), "run-x", study, spec)
    text = next(e.text for e in events if getattr(e, "text", None))
    return text, [o.label for o in events[-1].options]


def _clean(text):
    for w in ("오차", "구간", "감안", *BANNED_WORDS):
        assert w not in text, w


def test_sex_split_is_clear_and_age_is_not():
    study = _study(SEX_SPLIT)
    sex, age = study["axes"]["sex"], study["axes"]["age"]
    assert [(g["label"], g["n"], g["picked"], g["rate"]) for g in sex["groups"]] == [
        ("여성", 160, 51, 31.9), ("남성", 160, 29, 18.1)]
    assert sex["clear"] is True and 2.7 < sex["stat"] < 2.9
    assert [g["picked"] for g in age["groups"]] == [21, 20, 19, 20] and {g["n"] for g in age["groups"]} == {80}
    assert age["clear"] is False
    # 옛 칸은 그대로 남는다.
    assert len(study["cells"]) == 8 and "suggested" in study and "overlap" in study

    text, options = _say(study, _spec())
    _clean(text)
    assert text.startswith("여성이 남성보다 많이 골랐어요. 여성 160명 중 51명(31.9%), 남성 160명 중 29명(18.1%)이에요. "
                           "연령대별로는 차이가 없었어요(24~26%).")
    assert "원래 타깃인 19~29세로 본 테스트를 해도 좋아요." in text
    assert options[0] == "19~29세 (추천)" and "여성 (전 연령)" in options

    # 원래 타깃이 뚜렷이 낮은 쪽이면 그 사실을 말하고 높은 쪽을 권한다.
    text, options = _say(study, _spec(sex="남자"))
    _clean(text)
    assert "원래 타깃은 19~29세 남성인데, 남성은 여성보다 적게 골랐어요." in text
    assert "19~29세 여성 300명에게" in text and options[0] == "19~29세 여성 (추천)"


def test_nothing_splits():
    study = _study({cell: 10 for cell in explore.CELLS})
    assert study["axes"]["sex"]["clear"] is False and study["axes"]["age"]["clear"] is False
    text, options = _say(study, _spec())
    _clean(text)
    assert text.startswith("연령대와 성별 어느 쪽으로도 뚜렷한 차이가 없었어요. 전체로는 320명 중 80명(25%)이 골랐어요.")
    assert options == ["19~29세 (추천)", "다른 대상 고르기"]


def test_age_split_names_highest_and_lowest():
    picks = {(a, s): {"19-29": 4, "30-39": 8, "40-49": 12, "50-59": 16}[a] for a, s in explore.CELLS}
    study = _study(picks)
    assert study["axes"]["age"]["clear"] is True and study["axes"]["sex"]["clear"] is False
    text, options = _say(study, _spec())
    _clean(text)
    assert text.startswith("50~59세가 19~29세보다 많이 골랐어요. 50~59세 80명 중 32명(40%), 19~29세 80명 중 8명(10%)이에요. "
                           "성별로는 차이가 없었어요(25%).")
    assert "원래 타깃은 19~29세인데, 19~29세는 50~59세보다 적게 골랐어요." in text
    assert options[0] == "50~59세 (추천)"


def test_incomplete_or_small_has_no_verdict():
    partial = _study(SEX_SPLIT, status="running", answered=20)
    assert partial["axes"]["sex"]["clear"] is None and partial["axes"]["age"]["clear"] is None
    assert partial["axes"]["sex"]["groups"][0]["n"] == 80
    small = _study({}, per_cell=3)
    assert small["axes"]["sex"]["clear"] is None
    assert agent_explore.axis_finding(small, "19-29", None) is None
    text, _ = _say(small, _spec())
    _clean(text)
