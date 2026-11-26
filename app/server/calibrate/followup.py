"""후속 개선: 올린 소비자 조사를 정제하고, 테스트한 컨셉과 타깃의 답만 집계한다 (약속 v1.20). 모델을 부르지 않는다.

store/followup/<upload_id>/
  original.xlsx     올린 파일 그대로
  survey.json       집계(화면과 말이 읽는 것)와 이 대화의 처음 테스트
  respondents.json  타깃 응답자의 정제한 답(성별, 가중치, wtp, 갈래, 구매의향). 응답자 번호와 의견의 글은 두지 않는다
  assignment.json   가상 소비자에게 나눠 준 답(calibrate/overlay.py)
  state.json        어디까지 왔는지(step, retest_run)
폴더는 AX_FOLLOWUP_DIR로 바꿀 수 있다. 기본(app/server/store/)은 커밋되지 않는다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from onsite.survey import build_survey
from shelftest import explore, method, result, store
from tools.consumer import Group, default_label

ID_RE = re.compile(r"^fu-[0-9a-f]{12}$")
PRICE_STEP = 100
PRICE_LOW, PRICE_HIGH = 0.7, 1.2  # best_price를 찾는 범위(현재 가격의 배수)
CURVE_BELOW, CURVE_POINTS = 400, 7
SMALL_N = 30
PRICE_BARRIER, TASTE_BARRIER = "가격이 비쌈", "맛이 끌리지 않음"
REMOVED_LABELS = {"duplicate_hash": "중복 응답", "inattentive": "불성실 응답", "age_mismatch": "나이 확인 불가"}


# ---------- 의견의 갈래(핵심어 규칙) ----------


@dataclass(frozen=True)
class Opinion:
    """의견의 갈래 하나. fact는 가상 소비자의 글에 쓰는 말, say는 화면의 말(해요체)."""
    label: str
    good: bool
    pattern: str
    fact: str
    say: str
    group: str = ""  # taste: 맛 걱정, hope: 맛의 호기심과 추억


OPINIONS = (
    Opinion("추억", True, r"추억|어릴\s*때|어렸을|옛날", "어릴 때의 추억이 떠오른다", "추억이 떠올라요", "hope"),
    Opinion("부드러운 맛 기대", True, r"부드러", "맛이 부드러울 것 같다", "부드러운 맛이 기대돼요"),
    Opinion("맛의 호기심", True, r"호기심|맛이\s*궁금", "어떤 맛일지 궁금하다", "맛이 궁금해요", "hope"),
    Opinion("새로운 방식의 호기심", True, r"신선해|새로워|색다르", "새로운 방식이라 궁금하다", "새로운 방식이 궁금해요"),
    Opinion("한정판의 매력", True, r"한정(?:판|이라).{0,12}(?:한\s*번|마셔|사\s*보|끌)",
            "한정판이라 끌린다", "한정판이라 끌려요"),
    Opinion("여름에 시원함", True, r"시원|여름에.*좋", "여름에 시원할 것 같다", "여름에 시원할 것 같아요"),
    Opinion("디자인", True, r"디자인|패키지|사진", "디자인이 마음에 든다", "디자인이 마음에 들어요"),
    Opinion("진한 맛 기대", True, r"과즙.*진|맛이?\s*진할", "맛이 진할 것 같다", "진한 맛이 기대돼요"),
    Opinion("무난한 맛 기대", True, r"괜찮", "맛이 무난할 것 같다", "맛이 무난할 것 같아요"),
    Opinion("브랜드 신뢰", True, r"믿고|믿음이\s*가|믿을\s*수\s*있", "브랜드를 믿을 수 있다", "브랜드를 믿을 수 있어요"),
    Opinion("선물하기 좋음", True, r"선물|정성스", "선물하기 좋을 것 같다", "선물하기 좋을 것 같아요"),
    Opinion("강한 단맛", False, r"너무\s*달|(?<!덜 )(?<!안 )달\s*것\s*같|단맛.{0,4}(?:강|걱정|부담|세)",
            "단맛이 강할 것 같다", "단맛이 걱정돼요", "taste"),
    Opinion("인위적인 맛", False, r"인위|인공", "맛이 인위적일 것 같다", "인위적인 맛이 걱정돼요", "taste"),
    Opinion("낮은 과일 함량", False, r"함량.*(?:낮|적)|과(?:일|즙).*(?:낮다|적다|적어)", "과일이 적게 든 것 같다", "과일 함량이 낮아서 아쉬워요"),
    Opinion("기존 제품과 비슷함", False, r"다르지\s*않|뭐가\s*다른|무엇이\s*다른|다른지\s*모르|비슷",
            "기존 제품과 크게 다르지 않을 것 같다", "기존 제품과 비슷해 보여요"),
    Opinion("한정이라 덜 찾음", False, r"한정.{0,8}(?:굳이|안\s)", "한정 제품이라 굳이 찾지 않을 것 같다", "한정이라 굳이 찾지 않을 것 같아요"),
    Opinion("구매처 걱정", False, r"살\s*수\s*있을지|구하기|구할\s*수", "파는 곳을 찾기 어려울 것 같다", "파는 곳을 찾기 어려울 것 같아요"),
    Opinion("먹는 방법이 어려움", False, r"무슨\s*뜻|어떻게\s*먹", "어떻게 먹는지 알기 어렵다", "어떻게 먹는지 모르겠어요"),
    Opinion("휴대 불편", False, r"녹으면|휴대|들고\s*다니", "들고 다니기 불편할 것 같다", "들고 다니기 불편할 것 같아요"),
    Opinion("카페인 부담", False, r"카페인.*(?:높|많|부담)", "카페인이 부담스럽다", "카페인이 부담스러워요"),
    Opinion("짧은 유통기한", False, r"유통\s*기한", "유통기한이 짧을 것 같다", "유통기한이 걱정돼요"),
    Opinion("낯선 브랜드", False, r"처음\s*보는\s*브랜드|믿음이\s*안", "처음 보는 브랜드라 망설여진다", "처음 보는 브랜드라 망설여져요"),
    Opinion("비싼 가격", False, r"비싸|비싼|이\s*가격이면", "가격이 비싸다", "가격이 비싸요"),
)
BY_LABEL = {o.label: o for o in OPINIONS}
_COMPILED = [(o, re.compile(o.pattern)) for o in OPINIONS]


def classify(comment: Any) -> list[str]:
    """의견 하나의 갈래 이름들. 없으면 빈 목록."""
    if not isinstance(comment, str):
        return []
    return [o.label for o, pattern in _COMPILED if pattern.search(comment)]


# ---------- 파일 ----------


def root() -> Path:
    return Path(os.environ.get("AX_FOLLOWUP_DIR") or store.STORE / "followup")


def valid_id(upload_id: Any) -> bool:
    return isinstance(upload_id, str) and bool(ID_RE.match(upload_id))


def folder(upload_id: str) -> Path:
    if not valid_id(upload_id):
        raise ValueError("올린 조사 파일을 찾을 수 없어요.")
    return root() / upload_id


def read(upload_id: str, name: str) -> Any | None:
    try:
        return json.loads((folder(upload_id) / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def write(upload_id: str, name: str, value: Any) -> None:
    """임시 파일에 쓰고 바꿔치기한다."""
    directory = folder(upload_id)
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{name}-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=1, allow_nan=False)
        os.replace(tmp, directory / name)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load(upload_id: str) -> dict[str, Any] | None:
    return read(upload_id, "survey.json")


def state(upload_id: str) -> dict[str, Any]:
    return read(upload_id, "state.json") or {"step": "diff", "retest_run": None}


def set_state(upload_id: str, **changes: Any) -> dict[str, Any]:
    new = {**state(upload_id), **changes}
    write(upload_id, "state.json", new)
    return new


# ---------- 이 대화의 처음 테스트 ----------


def base_run(note: Any, chat_id: str) -> dict[str, Any]:
    """대화의 마지막 타깃 테스트(개선안이면 그 원래 안)."""
    candidates = [note.last_run, *reversed(list(note.runs.values()))]
    for run_id in candidates:
        meta = store.load_meta(run_id) if store.valid_id(run_id) else None
        if meta and meta.get("base_run_id"):
            meta = store.load_meta(meta["base_run_id"])
        # 조사를 반영해 다시 물은 것은 처음 테스트가 아니다
        if (meta and meta.get("chat_id") == chat_id and meta.get("mode", "target") in ("target", None)
                and not meta.get("change") and not meta.get("overlay")):
            if meta.get("status") == "running":
                raise ValueError("매대 테스트가 끝나면 조사 결과를 올려 주세요.")
            if concept_rows(meta["id"]):
                return meta
    raise ValueError("이 대화에는 아직 매대 테스트 결과가 없어요. 매대 테스트를 마친 뒤 올려 주세요.")


def concept_rows(run_id: str) -> list[dict[str, Any]]:
    """컨셉을 올린 매대의 답(뺀 방문은 빼고)."""
    return [row for _, row in result.concept_visits(store.answers(run_id))[0]]


def picks(run_id: str | None) -> dict[str, int] | None:
    meta = store.load_meta(run_id) if store.valid_id(run_id) else None
    if meta is None:
        return None
    rows = concept_rows(run_id)
    return {"n": len(rows), "picked": sum(r["product"] == meta["line"] for r in rows)}


# ---------- 집계 ----------


def _plain(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).casefold()


def _concept_name(names: list[str], tested: str) -> str | None:
    key = _plain(tested)
    return next((n for n in names if _plain(n) == key), None) or next(
        (n for n in names if key and (_plain(n) in key or key in _plain(n))), None)


def target_label(target: dict[str, Any]) -> str:
    label = default_label(Group(age=target.get("age"), sex=target.get("sex")))
    return "소비자" if label == "전체" else label


def _in_target(frame: pd.DataFrame, target: dict[str, Any]) -> pd.DataFrame:
    if target.get("age"):
        frame = frame[frame["age_band"].map(explore.AGES).eq(target["age"])]
    if target.get("sex"):
        frame = frame[frame["gender"].map(explore.SEXES).eq(target["sex"])]
    return frame


def respondents_of(tables: dict[str, Any], concept: str, target: dict[str, Any]) -> list[dict[str, Any]]:
    people = tables["survey_respondents"]
    rows = tables["survey_ratings"]
    rows = rows[rows["concept"].eq(concept)].merge(
        people[["rid", "age_band", "gender", "weight"]], on="rid", validate="many_to_one")
    out = []
    for row in _in_target(rows, target).to_dict("records"):
        wtp, intent, weight = row["wtp"], row["intent"], row["weight"]
        out.append({"sex": explore.SEXES.get(row["gender"]),
                    "weight": float(weight) if pd.notna(weight) and weight > 0 else 0.0,
                    "wtp": int(wtp) if pd.notna(wtp) and wtp > 0 else None,
                    "intent": int(intent) if pd.notna(intent) else None,
                    "opinions": classify(row["comment"])})
    if out and not sum(r["weight"] for r in out):
        for r in out:
            r["weight"] = 1.0
    return out


def _share(rows: list[dict[str, Any]], yes) -> float:
    """가중 비율(%)."""
    total = sum(r["weight"] for r in rows)
    return 100 * sum(r["weight"] for r in rows if yes(r)) / total if total else 0.0


def price_curve(rows: list[dict[str, Any]], current: int) -> tuple[list[dict[str, Any]], int | None]:
    """낼 수 있는 가격의 곡선과, 가격×비율이 가장 큰 100원 단위 가격(현재 가격의 0.7~1.2배 안)."""
    answered = [r for r in rows if r["wtp"] is not None]
    if not answered:
        return [], None

    def point(price: int) -> dict[str, Any]:
        share = _share(answered, lambda r: r["wtp"] >= price)
        return {"price": price, "share": round(share, 1), "money": round(price * share)}

    low = -(-int(current * PRICE_LOW) // PRICE_STEP) * PRICE_STEP
    grid = {p for p in range(max(PRICE_STEP, low), int(current * PRICE_HIGH) + 1, PRICE_STEP)} | {current}
    best = max((point(p) for p in grid), key=lambda x: (x["money"], -abs(x["price"] - current)))["price"]
    start = max(PRICE_STEP, (current - CURVE_BELOW) // PRICE_STEP * PRICE_STEP)
    shown = {start + PRICE_STEP * i for i in range(CURVE_POINTS)} | {current, best}
    return [point(p) for p in sorted(shown)], best


def _opinions(rows: list[dict[str, Any]], good: bool) -> list[dict[str, Any]]:
    out = []
    for o in OPINIONS:
        mine = [r for r in rows if o.label in r["opinions"]]
        if o.good is good and mine:
            out.append({"text": o.label, "n": len(mine), "intent": _intent(mine)})
    return sorted(out, key=lambda x: -x["n"])


def _intent(rows: list[dict[str, Any]]) -> int:
    answered = [r for r in rows if r["intent"] is not None]
    return round(100 * sum(r["intent"] >= 4 for r in answered) / len(answered)) if answered else 0


def _union(rows: list[dict[str, Any]], labels: set[str]) -> dict[str, Any]:
    mine = [r for r in rows if labels & set(r["opinions"])]
    return {"labels": [o.label for o in OPINIONS if o.label in labels and any(o.label in r["opinions"] for r in mine)],
            "n": len(mine), "intent_n": sum((r["intent"] or 0) >= 4 for r in mine),
            "share": _share(rows, lambda r: bool(labels & set(r["opinions"])))}


def _feeling(rows: list[dict[str, Any]], group: str, good: bool, fallback: str) -> tuple[dict[str, Any], str, bool]:
    """맛 걱정(또는 호기심·추억) 합계. 없으면 가장 많은 갈래 하나. (집계, 화면의 말, 합계인가)"""
    found = _union(rows, {o.label for o in OPINIONS if o.group == group})
    if found["n"]:
        return found, fallback, True
    tops = _opinions(rows, good)
    if tops:
        label = tops[0]["text"]
        return _union(rows, {label}), BY_LABEL[label].say, False
    return found, fallback, True


def aggregate(rows: list[dict[str, Any]], price: int, base: dict[str, Any], target: str) -> dict[str, Any]:
    """집계 하나. base는 처음 테스트의 머리."""
    curve, best = price_curve(rows, price)
    answered = [r for r in rows if r["wtp"] is not None]
    visits = concept_rows(base["id"])

    def barrier(label: str) -> float:
        return 100 * sum(label in (v.get("barriers") or []) for v in visits) / len(visits)

    worry, worry_text, is_taste = _feeling(rows, "taste", False, "맛이 걱정돼요")
    hope, hope_text, _ = _feeling(rows, "hope", True, "맛이 궁금하거나 추억이 떠올라요")
    diffs = []
    if answered:
        able = _share(answered, lambda r: r["wtp"] >= price)
        diffs.append({"id": "price", "text": f"{price:,}원을 낼 수 있어요", "actual": round(able),
                      "actual_n": len(answered), "virtual": round(100 - barrier(PRICE_BARRIER)) if visits else None,
                      "virtual_n": len(visits) or None})
    diffs.append({"id": "worry", "text": worry_text, "actual": round(worry["share"]), "actual_n": len(rows),
                  "virtual": round(barrier(TASTE_BARRIER)) if visits and is_taste else None,
                  "virtual_n": len(visits) if visits and is_taste else None})
    # 가상 소비자의 보는 눈(view)에는 "궁금"에 해당하는 답이 없다
    diffs.append({"id": "hope", "text": hope_text, "actual": round(hope["share"]), "actual_n": len(rows),
                  "virtual": None, "virtual_n": None})
    note = (f"실제는 {target} {len(rows):,}명의 답을 인구 비중에 맞춰 셌어요. 가격은 적어 낸 {len(answered):,}명만 셌어요. "
            f"가상 소비자는 처음 테스트 {len(visits):,}명의 걸린 점에서 셌어요.")
    if len(rows) < SMALL_N:
        note += f" 응답이 {len(rows):,}명뿐이라 참고로만 봐 주세요."
    return {
        "intent": {"n": sum(r["intent"] is not None for r in rows),
                   "weighted": round(_share([r for r in rows if r["intent"] is not None], lambda r: r["intent"] >= 4))},
        "wtp": {"n": len(answered), "able_n": sum(r["wtp"] >= price for r in answered)},
        "curve": curve, "best_price": best,
        "opinions": {"good": _opinions(rows, True), "bad": _opinions(rows, False)},
        "taste": worry if is_taste else None, "diffs": diffs, "note": note,
    }


def create(note: Any, chat_id: str, filename: str, content: bytes) -> str:
    """올린 파일을 정제해 담고 upload_id를 준다. 쓸 수 없으면 ValueError(해요체 한 문장)."""
    if not str(filename).lower().endswith(".xlsx"):
        raise ValueError("엑셀 파일(.xlsx)을 올려 주세요.")
    base = base_run(note, chat_id)
    upload_id = f"fu-{uuid.uuid4().hex[:12]}"
    directory = folder(upload_id)
    directory.mkdir(parents=True)
    try:
        path = directory / "original.xlsx"
        path.write_bytes(content)
        try:
            tables, report = build_survey(path)
        except Exception as err:  # noqa: BLE001 — 형식이 다른 파일은 어디서 막히든 같은 말로 알린다
            raise ValueError("소비자 조사 파일의 시트와 문항을 읽지 못했어요. 조사 양식 그대로인지 확인해 주세요.") from err
        tested = base["concept"]
        ratings = tables["survey_ratings"]
        name = _concept_name(sorted(set(ratings["concept"])), tested["name"])
        if name is None:
            raise ValueError(f"올린 조사에는 ‘{tested['name']}’의 답이 없어요. 테스트한 컨셉의 조사인지 확인해 주세요.")
        rows = respondents_of(tables, name, base["target"])
        target = target_label(base["target"])
        if not rows:
            raise ValueError(f"올린 조사에는 {target}의 답이 없어요. 타깃을 조사한 파일인지 확인해 주세요.")
        price = int(tested["price"])
        write(upload_id, "respondents.json", rows)
        write(upload_id, "survey.json", {
            "upload_id": upload_id, "chat_id": chat_id, "base_run": base["id"],
            "concept": {"id": base["concept_id"], "name": tested["name"], "price": price}, "target": target,
            "n": {"raw": int(tables["survey_summary"]["n"]["raw"]), "clean": int(tables["survey_summary"]["n"]["clean"]),
                  "target": len(rows)},
            "removed": [{"label": REMOVED_LABELS[r["rule"]], "count": int(r["removed"])} for r in report
                        if r["rule"] in REMOVED_LABELS and r["removed"]],
            **aggregate(rows, price, base, target),
        })
        write(upload_id, "state.json", {"step": "diff", "retest_run": None})
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return upload_id


# ---------- 다시 테스트와의 짝 비교 ----------


def _choices(run_id: str) -> dict[tuple, str]:
    return {(r["uuid"], r["visit"], r["occasion"]): r["product"] for r in concept_rows(run_id)
            if all(r.get(k) for k in ("uuid", "visit", "occasion", "product"))}


def paired(before_run: str, after_run: str) -> dict[str, Any] | None:
    """두 테스트에 모두 답한 같은 방문에서 계속 고른 수, 새로 고른 수, 빠진 수."""
    old, new = store.load_meta(before_run), store.load_meta(after_run)
    if not old or not new:
        return None
    before, after = _choices(before_run), _choices(after_run)
    keys = before.keys() & after.keys()
    if not keys:
        return None
    was = {k for k in keys if before[k] == old["line"]}
    now = {k for k in keys if after[k] == new["line"]}
    gained, lost = len(now - was), len(was - now)
    clear = False
    if gained + lost:
        from scipy.stats import binomtest

        clear = binomtest(gained, gained + lost).pvalue < 0.05
    return {"n": len(keys), "before": len(was), "after": len(now), "gained": gained, "lost": lost, "clear": clear}


# ---------- 화면과 보고서 ----------


def can_retest() -> bool:
    from shelftest import runner

    return "overlay" in runner.Spec.__dataclass_fields__


def fitted(survey: dict[str, Any]) -> dict[str, Any] | None:
    """최적화한 가상 소비자의 집계: 조사와 같은 것을 배정에서 다시 센다(%). 아직 맞추지 않았으면 None."""
    from calibrate import overlay

    people = list(overlay.assigned(survey["upload_id"]).values())
    if not people:
        return None
    price = int(survey["concept"]["price"])
    priced = [p for p in people if p["wtp"] is not None]

    def share(labels: set[str]) -> int:
        return round(100 * sum(bool(labels & set(p["opinions"])) for p in people) / len(people))

    taste = set((survey.get("taste") or {}).get("labels") or [])
    hope = {o.label for o in OPINIONS if o.group == "hope"}
    diffs: dict[str, int] = {}
    if priced:
        diffs["price"] = round(100 * sum(p["wtp"] >= price for p in priced) / len(priced))
    if taste:
        diffs["worry"] = share(taste)
    if any(hope & set(p["opinions"]) for p in people):
        diffs["hope"] = share(hope)
    return {"n": len(people), "priced": len(priced), "diffs": diffs}


def save_insight(survey: dict[str, Any]) -> dict[str, Any] | None:
    """최적화한 가상 소비자의 집계를 가상 소비자 인사이트(store/followup/insights.json)에 남긴다. 같은 조사는 한 줄."""
    import json
    from datetime import datetime, timezone

    fit = fitted(survey)
    if fit is None:
        return None
    path = root() / "insights.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        rows = []
    row = {"upload_id": survey["upload_id"], "chat_id": survey["chat_id"], "target": survey["target"],
           "concept": survey["concept"]["name"], "survey_n": survey["n"]["target"], "people": fit["n"],
           "diffs": fit["diffs"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    rows = [r for r in rows if r.get("upload_id") != row["upload_id"]] + [row]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    set_state(survey["upload_id"], saved=True)
    return row


def payload(survey: dict[str, Any], *, step: str, improve: dict[str, Any] | None = None) -> dict[str, Any]:
    """카드 followup의 payload. improve는 대화의 개선안 표(고친 안의 선택을 세는 데 쓴다)."""
    base = store.load_meta(survey["base_run"]) or {}
    retest_run = state(survey["upload_id"]).get("retest_run")
    retest = store.load_meta(retest_run) if retest_run else None
    original = picks(survey["base_run"])
    after = picks(retest_run) if retest and retest.get("status") == "done" else None
    return {
        **{k: survey[k] for k in ("upload_id", "concept", "target", "n", "removed", "diffs", "note", "curve",
                                  "best_price", "opinions")},
        "step": step,
        "track": {"total": int(base.get("total") or (original or {}).get("n") or 0),
                  "original": original["picked"] if original else None, "retest": after["picked"] if after else None,
                  "improved": _improved(survey, improve, retest_run)},
        "base_run": survey["base_run"], "retest_run": retest_run, "can_retest": can_retest(),
        "fit": fitted(survey),
        "saved": bool(state(survey["upload_id"]).get("saved")),
    }


def _improved(survey: dict[str, Any], improve: dict[str, Any] | None, retest_run: str | None) -> int | None:
    """이 조사에서 나온 안 가운데 채택한 안의 선택, 없으면 끝난 안의 가장 많은 선택."""
    plan = improve or {}
    if plan.get("base_run") not in (survey["base_run"], retest_run):
        return None
    counts = {}
    for item in plan.get("items") or []:
        meta = store.load_meta(item["run_id"]) if store.valid_id(item.get("run_id")) else None
        if item.get("followup") == survey["upload_id"] and meta and meta.get("status") == "done":
            counts[item["id"]] = picks(item["run_id"])["picked"]
    return counts.get(plan.get("adopted_item_id"), max(counts.values(), default=None))


def people_view(upload_id: str) -> dict[str, Any] | None:
    """GET /api/followup/{upload_id}/people의 모양. 이름과 uuid는 내보내지 않는다."""
    survey = load(upload_id) if valid_id(upload_id) else None
    base = store.load_meta(survey["base_run"]) if survey else None
    if base is None:
        return None
    from calibrate import overlay

    retest_run = state(upload_id).get("retest_run")
    retest = store.load_meta(retest_run) if retest_run else None
    t = base["target"]
    persons = {p.uuid: p for p in method.people(t.get("age"), t.get("sex"))}
    after = {(r["uuid"], r["occasion"]): r for r in (concept_rows(retest_run) if retest else [])}
    assigned = overlay.assigned(upload_id)
    people = []
    for row in concept_rows(base["id"]):
        person = persons.get(row["uuid"])
        new = after.get((row["uuid"], row["occasion"]))
        picked_before = row["product"] == base["line"]
        picked_after = new["product"] == retest["line"] if new else None
        last, picked = (new, picked_after) if new else (row, picked_before)
        said = str((last.get("sentence") if picked else last.get("said")) or "").strip()
        if person is None or any(w and w in said for w in method.name_words(person)):
            said = ""
        people.append({"id": row["visit"], "who": method.who_line(person) if person else "",
                       "lines": list(assigned.get(row["uuid"], {}).get("lines", [])),
                       "before": picked_before, "after": picked_after, "said": said})
    answered = [p for p in people if p["after"] is not None]
    return {"status": retest["status"] if retest else "applied" if assigned else "ready",
            "total": len(people), "asked": len(answered),
            "before": {"n": len(people), "picked": sum(p["before"] for p in people)},
            "after": {"n": len(answered), "picked": sum(p["after"] for p in answered)}, "people": people}


def report_lines(note: Any, concept: dict[str, Any]) -> list[str]:
    """결과 보고서의 "소비자 조사 반영" 줄(보고서체). 올린 조사가 없거나 다른 컨셉이면 빈 목록."""
    saved = (note.get("followup") if isinstance(note, dict) else getattr(note, "followup", None)) or {}
    survey = load(saved["upload_id"]) if valid_id(saved.get("upload_id")) else None
    if survey is None or concept.get("id") != survey["concept"]["id"]:
        return []
    n, price, target = survey["n"], survey["concept"]["price"], survey["target"]
    removed = ", ".join(f"{r['label']} {r['count']}명" for r in survey["removed"])
    lines = [f"{target} {n['target']:,}명의 응답을 사용함" + (f" ({removed} 제외)" if removed else "")]
    if n["target"] < SMALL_N:
        lines.append(f"응답이 {n['target']:,}명으로 적어 참고로만 사용함")
    lines.append(f"구매 의향이 있다는 응답은 {survey['intent']['weighted']}%임. 가상 소비자에게 더하지 않고 확인에만 사용함")
    able = next((d for d in survey["diffs"] if d["id"] == "price"), None)
    if able:
        best = survey["best_price"]
        at = next((x["share"] for x in survey["curve"] if x["price"] == best), None)
        lines.append(f"{price:,}원을 낼 수 있다는 응답은 {able['actual']}%임"
                     + (f". 조사에서 매출이 가장 큰 가격은 {best:,}원이며 {round(at)}%가 낼 수 있음" if best != price and at else ""))
    for key, title in (("good", "사고 싶은 이유"), ("bad", "망설인 이유")):
        tops = ", ".join(f"{o['text']} {o['n']}명" for o in survey["opinions"][key][:3])
        if tops:
            lines.append(f"{title}: {tops}")
    retest_run = state(survey["upload_id"]).get("retest_run")
    meta = store.load_meta(retest_run) if retest_run else None
    if meta and meta.get("status") == "done" and (p := paired(survey["base_run"], retest_run)):
        lines.append(f"조사를 반영해 다시 물은 결과 {p['n']:,}명 중 {p['before']:,}명에서 {p['after']:,}명으로 바뀜"
                     + ("" if p["clear"] else " (우연일 수 있는 차이임)") + ". 조사 답을 더한 결과이므로 조사와 독립된 검증은 아님")
    return lines
