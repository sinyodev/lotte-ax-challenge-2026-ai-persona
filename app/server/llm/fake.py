"""테스트용 어댑터: 정해진 답을 돌려준다. pytest는 이것만 쓴다(모델을 부르지 않는다).

FakeLLM(answers={일의 이름: 답})으로 바꿔 끼운다. 답은
- dict: 그대로 돌려준다
- list: 부를 때마다 앞에서 하나씩 꺼낸다(형식이 틀린 답 다음에 맞는 답 등)
- 함수 (system, user, schema) -> dict
- 예외(LLMError 등): 던진다
정하지 않은 일은 아래의 기본 답(제로 탄산의 보통의 길)을 쓴다. 기본 읽기는 낱말로 짐작하는 흉내다(진짜 읽기는 evals/read_live.py가 잰다).
"""

from __future__ import annotations

import asyncio
import itertools
import os
import re
from typing import Any

from llm.base import LLMError

PRODUCTS = [
    ("제로", {"value": "제로 탄산", "product_kind": "탄산음료(저칼로리)", "shelf_kind": "탄산"}),
    ("말차", {"value": "말차 라떼", "product_kind": "차", "shelf_kind": "차"}),
    ("막걸리", {"value": "막걸리", "product_kind": "막걸리", "shelf_kind": "막걸리"}),
    ("삼각김밥", {"value": "삼각김밥", "product_kind": "없음", "shelf_kind": "없음"}),
]
ORDINALS = ["첫 번째", "두 번째", "세 번째", "네 번째", "다섯 번째"]
_seq = itertools.count()


def _planner(user: str) -> str:
    return user.split("기획자의 말:\n", 1)[-1]


def _board_ids(user: str, concept: bool = False) -> list[str]:
    pat = r"- id (\w+) \([^)]*번째 컨셉\)" if concept else r"- id (\w+) \([^)]*번째\):"
    return re.findall(pat, user)


def _task(do: str, slot: str = "", value: str = "", ids: list[str] | None = None, text: str = "") -> dict:
    return {"do": do, "slot": slot, "value": value, "ids": ids or [], "text": text}


def _read(system: str, user: str, schema: dict) -> dict:
    said = _planner(user)
    ideas, concepts = _board_ids(user), _board_ids(user, True)
    out: dict[str, Any] = {"tasks": [], "lookups": [], "product_kind": "없음", "shelf_kind": "없음",
                           "target_age": "없음", "target_sex": "없음", "occasion_code": "없음"}
    tasks, looks = out["tasks"], out["lookups"]
    m = re.search(r"누른 칩의 id: ([^)\n]+)", said)
    chip_ids = [x.strip() for x in m.group(1).split(",")] if m else []

    def ordinal(ids: list[str]) -> list[str]:
        return [ids[k] for k, w in enumerate(ORDINALS) if w in said and k < len(ids)]

    if chip_ids:
        cid = chip_ids[0]
        if cid == "make-concepts":
            tasks.append(_task("concepts"))
        elif cid == "confirm-concepts":
            tasks.append(_task("confirm"))
        elif cid == "more-ideas":
            tasks.append(_task("more"))
        elif cid in ("ideas", "ideas-again"):
            tasks.append(_task("ideas"))
        elif cid.startswith("target:"):
            age = cid.split("|")[-1]
            out["target_age"] = age
            tasks.append(_task("note", "target", {"19-29": "20대", "30-39": "30대"}.get(age, age)))
        elif cid == "go-shelf":
            tasks.append(_task("shelf_test"))
        elif cid == "download":
            tasks.append(_task("download"))
        elif all(c in ideas for c in chip_ids):
            tasks.append(_task("concepts", ids=chip_ids))
        return out
    if "추천" in said:
        tasks.append(_task("recommend"))
        return out
    if "중고차" in said:
        tasks.append(_task("out_of_scope"))
        return out
    for word, ans in PRODUCTS:
        if word in said:
            out["product_kind"], out["shelf_kind"] = ans["product_kind"], ans["shelf_kind"]
            tasks.append(_task("note", "product", ans["value"]))
            looks.append({"tool": "who", "arg": ""})
            break
    age = re.search(r"([2-6])0대", said)
    if age and "왜" not in said:
        out["target_age"] = {"2": "19-29", "3": "30-39", "4": "40-49", "5": "50-59", "6": "60-69"}[age.group(1)]
        tasks.append(_task("note", "target", said.split("\n")[0].strip()))
        looks.append({"tool": "when", "arg": ""})
    if "왜" in said or "어디서 나왔" in said:
        tasks.append(_task("answer", text=said.split("\n")[0]))
        looks.append({"tool": "who", "arg": ""})
    elif "확정" in said:
        tasks.append(_task("confirm"))
    elif "매대에 올려" in said:
        tasks.append(_task("shelf_test"))
    elif "결과 보여" in said:
        tasks.append(_task("shelf_result"))
    elif "결과 보고서" in said:
        tasks.append(_task("report"))
    elif "다시 물은 결과" in said or "고친 안은" in said:
        tasks.append(_task("improve_result"))
    elif "개선안" in said:
        tasks.append(_task("improve"))
    elif "다시 물어" in said or "붙여 봐" in said or "다시 돌려" in said:
        tasks.append(_task("improve_run", text=said.split("\n")[0]))
    elif "내려받" in said or "뽑아" in said:
        tasks.append(_task("download"))
    elif "컨셉" in said and "만들" in said:
        ids = [x.lower() for x in re.findall(r"\b([A-E])\b", said)] or ordinal(ideas)
        tasks.append(_task("concepts", ids=[i for i in ids if i in ideas]))
    elif concepts and any(w in said for w in ("용량", "헤드라인", "가격")):
        tasks.append(_task("edit_concept", ids=ordinal(concepts) or concepts[:1], text=said))
    else:
        if "빼" in said:
            tasks.append(_task("drop", ids=ordinal(ideas)))
        if "남겨" in said:
            tasks.append(_task("keep", ids=ordinal(ideas)))
        if "내 아이디어" in said or "내 생각은" in said:
            tasks.append(_task("my_idea", text=said.split("아이디어로")[-1].strip()))
        elif "맛을" in said and ideas:
            tasks.append(_task("edit_idea", ids=ordinal(ideas) or ideas[:1], text=said))
        elif "다른 아이디어" in said:
            tasks.append(_task("more" if ideas else "ideas"))
        elif "아이디어" in said:
            tasks.append(_task("ideas", text="아침" if "아침" in said else ""))
        elif "아침" in said or "용" in said or "면 좋겠" in said:
            tasks.append(_task("thought", text=said.strip()))
            looks.append({"tool": "when", "arg": "아침" if "아침" in said else ""})
    if not tasks:
        tasks.append(_task("answer", text=said))
    out["tasks"], out["lookups"] = tasks[:3], looks[:3]
    return out


def _trend(system: str, user: str, schema: dict) -> dict:
    return {"claims": [
        {"claim": "제로 탄산 시장에서 과일 향을 더한 제품이 잇따라 나오고 있어요", "source": "견본 신문",
         "url": "https://example.com/news/1", "date": "2026-09-01"},
        {"claim": "식사와 함께 마시는 탄산의 수요가 늘었다는 업계의 이야기가 있어요", "source": "견본 업계지",
         "url": "https://example.com/news/2", "date": "2026-06-15"},
    ]}


BASE_IDEAS = [
    ("청귤 제로 스파클링", "청귤", "페트", 500, ["제로 칼로리", "청귤 과즙 향"], "기름진 저녁에 상큼하게", "새콤한 과일 향으로 입가심"),
    ("보리 제로 소다", "볶은 보리", "캔", 355, ["제로 칼로리", "구수한 보리 향"], "밥과 어울리는 구수한 탄산", "식사에 맞춘 곡물 맛"),
    ("레몬 진저 제로", "레몬과 생강", "페트", 500, ["제로 칼로리", "생강의 알싸함"], "느끼함을 잡는 알싸한 한 모금", "강한 맛으로 개운함"),
    ("자몽 제로 토닉", "자몽", "캔", 355, ["제로 칼로리", "쌉싸름한 자몽"], "쌉싸름하게 깔끔한 한 캔", "어른스러운 쓴맛"),
    ("매실 제로 소다", "매실", "페트", 500, ["제로 칼로리", "매실 향"], "속이 편한 새콤함", "소화를 떠올리는 맛"),
]


def _ideas(system: str, user: str, schema: dict) -> dict:
    n = schema["properties"]["items"]["minItems"]
    items = []
    for _ in range(n):
        k = next(_seq)
        name, f, c, v, fe, li, d = BASE_IDEAS[k % len(BASE_IDEAS)]
        items.append({"name": f"{name}" + (f" {k // len(BASE_IDEAS) + 1}" if k >= len(BASE_IDEAS) else ""),
                      "flavor": f, "container": c, "volume_ml": v, "features": fe, "line": li, "diff": d,
                      # 11-25: 칠성이가 제안하는 사양(PET 500mL 1,800원 9개월, 캔 355mL 1,500원 12개월)
                      "price": 1800 if c == "페트" else 1500, "shelf_life_months": 9 if c == "페트" else 12,
                      "kcal": 220 if c == "페트" else 150, "launch": "2027-05", "season": "",
                      "channels": ["편의점", "대형마트·SSM"]})
    return {"need": "기름진 저녁을 당 걱정 없이 개운하게", "items": items}


def _field(user: str, label: str) -> str:
    m = re.search(rf"- {label}: (.*)", user)
    return m.group(1).strip() if m else ""


def _edit_idea(system: str, user: str, schema: dict) -> dict:
    said = user.split("기획자의 말(이대로 고친다): ", 1)[-1]
    flavor = _field(user, "맛")
    name = _field(user, "이름")
    m = re.search(r"맛을 (\S+?)(?:으로|로)", said)
    if m:
        name = name.replace(flavor, m.group(1)) if flavor in name else f"{m.group(1)} {name}"
        flavor = m.group(1)
    return {"name": name, "flavor": flavor, "container": _field(user, "용기"), "volume_ml": int(_field(user, r"용량\(ml\)")),
            "features": [x.strip() for x in _field(user, "특징").split(",")], "line": _field(user, "한 줄 설명"),
            "diff": _field(user, "다른 점")}


def _my_idea(system: str, user: str, schema: dict) -> dict:
    text = user.split("기획자의 아이디어(이 말을 살려 받아 적는다): ", 1)[-1].split("\n")[0].strip()
    name = re.sub(r"\s*(넣어|올려).*$", "", text) or "기획자의 아이디어"
    # 지시서 33: "캔 250ml"처럼 규격을 말했으면 그 규격 하나만 옮긴다(숫자는 말한 것만)
    m = re.search(r"(캔|페트|병|팩)\s*(\d+)\s*ml", name)
    out = {"name": name, "flavor": name.split()[0], "container": "캔", "volume_ml": 355,
           "features": ["제로 칼로리"], "line": f"{name} 한 캔", "diff": "기획자가 낸 맛"}
    if m:
        name = name[:m.start()].strip() or name
        out.update(name=name, flavor=name.split()[0], container=m.group(1), volume_ml=int(m.group(2)), line=f"{name} 한 병"
                   if m.group(1) == "병" else f"{name} 한 {m.group(1)}")
        out["variants"] = [{"container": m.group(1), "pack": "", "volume_ml": int(m.group(2)), "price": None,
                            "factory_price": None, "shelf_life_months": None, "shelf_life_days": None, "kcal": None}]
    return out


def _concepts(system: str, user: str, schema: dict) -> dict:
    props = schema["properties"]["items"]["items"]["properties"]
    ids = props["idea_id"]["enum"]
    guess = "price_guess" in props
    carb = props["carbonation"]["enum"][0]
    items = []
    for i in ids:
        rivals = re.search(rf"- id {i}: .*경쟁 제품: (.*?)(?: / 매대에|$)", user, re.M)
        has_rivals = bool(rivals) and not rivals.group(1).startswith("(")
        it = {"idea_id": i, "name": f"컨셉 {i}", "headline": "저녁 한 끼를 개운하게 끝내는 한 병",
              "benefit": "입안을 개운하게 정리해요", "insight": "더운 날 늘 마시던 탄산은 금방 물려요",
              "points": ["청귤 과즙", "당 0g", "다시 닫는 뚜껑"],
              "sugar_caffeine": "당 0g, 카페인 없음", "carbonation": carb, "occasion": "",
              "pod": "더 상큼한 청귤 향" if has_rivals else ""}
        if guess:
            it["price_guess"] = 2350
        items.append(it)
    return {"items": items}


def _edit_concept(system: str, user: str, schema: dict) -> dict:
    said = user.split("기획자의 말(이대로 고친다): ", 1)[-1]
    volume = int(_field(user, r"용량\(ml\)"))
    m = re.search(r"용량을 (\d+)", said)
    if m:
        volume = int(m.group(1))
    headline = _field(user, "상황 한 줄")
    if "헤드라인" in said:
        headline = "아침을 깨우는 한 모금"
    carb = _field(user, "탄산")
    if carb not in schema["properties"]["carbonation"]["enum"]:
        carb = schema["properties"]["carbonation"]["enum"][0]
    sugar = _field(user, "당, 카페인")
    pod = _field(user, "차별점")
    insight = _field(user, "소비자 인식")
    return {"name": _field(user, "제품명"), "headline": headline, "benefit": _field(user, "혜택 한 줄"),
            "insight": "" if insight == "(없음)" else insight,
            "points": [x.strip() for x in _field(user, "이런 점이 좋아요").split(" / ")][:3],
            "flavor": _field(user, "맛"), "container": _field(user, "용기"), "volume_ml": volume,
            "sugar_caffeine": "" if sugar == "(없음)" else sugar, "carbonation": carb, "occasion": "",
            "pod": "" if pod == "(없음)" else pod, "price_guess": 1800}


def _pod(system: str, user: str, schema: dict) -> dict:
    return {"pod": "더 작은 용량에 청귤 향"}


def _voice(system: str, user: str, schema: dict) -> dict:
    """검사를 통과하는 짧은 말: 찾아본 곳의 이름이 있으면 넣고, 물을 것이 있으면 물음으로 끝낸다."""
    m = re.search(r"찾아본 곳의 이름\(말에 한 번 넣는다\): (.+)", user)
    head = f"{m.group(1).strip()}를 찾아보니 그렇더라고요. " if m else ""
    return {"text": head + ("그렇게 해 볼까요?" if "\n(3) 물을 것:" in user else "그렇게 해 볼게요.")}


def _proposal(system: str, user: str, schema: dict) -> dict:
    """제안서의 요지와 배경(지시서 14): 요지는 컨셉의 값으로, 배경은 "배 자주 마셔요"인 찾아본 것 하나를 보고서체로."""
    ev = re.search(r"- id (ev-\d+): (.*?배 자주 )마셔요", user)
    pages = []
    for cid in schema["properties"]["pages"]["items"]["properties"]["concept_id"]["enum"]:
        block = user.split(f"[컨셉 {cid}]", 1)[-1]
        pack, price = _field(block, "용기와 용량"), _field(block, "목표 판매가")
        pages.append({"concept_id": cid, "gist": f"식사에 곁들이는 손님을 겨냥해 상큼한 탄산({pack}, {price})을 제안함",
                      "concept": "식사에 곁들이는 상큼한 탄산",
                      "background": [{"text": ev.group(2) + "마심", "evidence_ids": [ev.group(1)]}] if ev else []})
    return {"pages": pages}


SHOPPER_PICK = 0.2  # 새 제품을 집는 손님의 몫(대략)


def _shopper(system: str, user: str, schema: dict) -> dict:
    """가상 손님(지시서 15): 손님마다 정해지는 답. 손님 한 사람의 글("[당신]" 부분)로 정하므로 매대의 순서가 바뀌어도
    같은 손님은 같은 제품을 고른다. 몇 명은 새 제품을 집는다. 열에 하나쯤은 사지 않는다."""
    import hashlib

    person = user.split("[평소 습관]", 1)[0]
    h = int(hashlib.md5(person.encode("utf-8")).hexdigest()[:8], 16)
    lines = re.findall(r"^(\d+)\. (.+?) — ", user, re.M)
    new = re.search(r"매대의 (\d+)번 '", user)
    asked = "new_product" in schema["properties"]
    picked_new = bool(new) and (h % 1000) / 1000 < SHOPPER_PICK
    if picked_new:
        number = int(new.group(1))
    elif h % 10 == 0:
        number = 0
    else:
        others = sorted((name, int(num)) for num, name in lines if not (new and num == new.group(1)))
        number = others[h % len(others)][1]
    out: dict[str, Any] = {"choice_number": number, "reason_needs": ["N01"], "reason_other": "",
                           "reason_sentence": "늘 마시던 걸로 골랐어요." if not picked_new else "새로 나와서 한번 마셔 볼래요."}
    if asked:
        barriers = schema["properties"]["new_product"]["properties"]["barriers"]["items"]["enum"]
        views = schema["properties"]["new_product"]["properties"]["view"]["enum"]
        out["new_product"] = {
            "view": views[0] if picked_new else views[1 + (h >> 4) % 2],
            "barriers": [] if picked_new else [barriers[(h >> 8) % len(barriers)]],
            "said": "궁금하긴 한데 오늘은 다른 걸로 할래요." if not picked_new else "이건 한번 마셔 보고 싶어요.",
        }
    return out


def _interview(system: str, user: str, schema: dict) -> dict:
    """한 손님에게 묻기(지시서 17): 물음에 따라 정해진 짧은 답. 값을 물으면 숫자로."""
    q = user.rsplit("[기획자의 물음]", 1)[-1].strip()
    if "얼마" in q:
        return {"text": "1,500원이면 한번 집어 볼 것 같아요."}
    if "평소" in q:
        return {"text": "평소엔 늘 마시던 걸로 사요."}
    return {"text": "처음 보는 거라 오늘은 그냥 지나쳤어요."}


_GROUP_CONDITIONS = {
    "지금 상황에 안 맞음": "어떤 음용 상황에 어울리는지 알면",
    "맛이 끌리지 않음": "단맛을 덜 낸 안이 있다면",
    "가격이 비쌈": "가격이 낮아지면",
    "처음 보는 제품이라 망설여짐": "처음에 어떤 맛인지 쉽게 알 수 있으면",
    "용량이나 용기가 안 맞음": "작은 용량도 있다면",
    "늘 마시는 것이 있음": "익숙한 제품과 어떤 점이 다른지 보이면",
    "어떤 제품인지 모르겠음": "음료의 맛과 제형이 앞면에 분명하면",
}


def _group_turn(system: str, user: str, schema: dict) -> dict:
    """받은 방문 선택, 물음과 앞 발언으로 한 사람의 답을 구성한다."""
    import hashlib
    import json

    data = json.loads(user)
    p, memory = data["participant"], data["observed"]
    question, kind = data["question"], data["question_id"]
    before = memory["before"] or {}
    number = int.from_bytes(hashlib.sha256(p["id"].encode()).digest()[:2])
    known = [b for b in memory["barriers"] if b in _GROUP_CONDITIONS]
    barrier = next((b for b in known if b in question), known[0] if known else None)
    condition = _GROUP_CONDITIONS.get(barrier, "지금 고른 음료와 다른 점을 알 수 있으면")
    form = data["concept"].get("form") or ""
    if barrier == "지금 상황에 안 맞음" and "탄산" in form and "무탄산" not in form and "비탄산" not in form:
        condition = "탄산 없는 안이 있다면"
    choice = p["choice"]
    observed = ("오늘은 음료를 사지 않았어요." if choice == "아무것도 사지 않음" else
                f"오늘은 {choice} 쪽을 골랐어요.")
    consider = f"{condition} 다음에는 비교해 볼래요."
    if p["picked"]:
        reason = p["reason"]
        detail = ("다음에도 새 맛이 당기면 고려해 볼래요." if "새로" in reason else
                  "지금처럼 이 특징이 눈에 띄면 다시 고려해 볼래요.")
        if kind in ("own", "inflow") and before.get("choice") and before["choice"] != choice:
            observed = f"컨셉이 없는 매대에서는 {before['choice']} 쪽이었는데 이번에는 {choice} 쪽을 골랐어요."
            detail = "익숙한 쪽과 차이가 분명하면 다시 비교해 볼래요."
        elif kind == "barrier":
            detail = "매대에서 새 제품이라는 점이 눈에 띄어서 다음에도 고려해 볼래요."
        position = "consider"
    elif kind == "barrier" and barrier and barrier in question:
        position, detail = (("consider", consider) if number % 4 == 0 else
                            ("pass", f"{condition} 다시 보겠지만 그대로라면 지나칠래요."))
    elif kind == "own" or kind == "inflow":
        position, detail = "pass", "기존에 보던 제품이 있으면 지금 조건에선 다른 음료를 고를래요."
    elif barrier:
        position, detail = "consider", consider
    elif "늘" in p["reason"]:
        position, detail = "pass", "익숙한 음료가 편해서 다음에도 지금 조건이라면 지나칠래요."
    else:
        position, detail = "unsure", "이 컨셉이 제가 찾는 음료일지는 아직 모르겠어요."
    if choice == "아무것도 사지 않음" and position == "pass":
        detail = "오늘처럼 마실 이유가 뚜렷하지 않으면 다음에도 지나칠래요."

    peer_id = quote = stance = None
    peers = data["previous_others"]
    if peers:
        # 앞 발언의 관점을 다시 읽고, 자기 매대 선택과 견줘 답한다.
        peer = peers[number % len(peers)]
        peer_id = peer["id"]
        quote = peer["text"].split(". ")[-1]
        cues = (("가격", "가격을 낮춘 안이 있으면 비교해 볼래요."),
                ("단맛", "단맛을 줄인 안이라면 비교해 볼래요."),
                ("용량", "작은 용량도 있다면 비교해 볼래요."),
                ("제형", "앞면에서 맛과 제형을 알 수 있으면 비교해 볼래요."),
                ("탄산 없는", "탄산을 뺀 안도 있으면 비교해 볼래요."),
                ("새 맛", "새 맛이 필요한 날이라면 고려해 볼래요."),
                ("어울리", "지금 마실 상황에 어울리는지 알면 고려해 볼래요."))
        response = next((line for cue, line in cues if cue in quote), None)
        cited = f"‘{quote.removesuffix('.')}’라는 말"
        if response and (p["picked"] or number % 3 != 0):
            stance, position, detail = "agree", "consider", response
            observed = f"{cited}에 저도 공감해요."
            previous = data["previous_self"][-1]["text"]
            if "지나칠래요" in previous or "모르겠어요" in previous or "다른 음료를 고를래요" in previous:
                observed += " 아까와 달리"
        elif p["picked"] == ("지나칠" not in quote and "다른 음료를 고를" not in quote):
            stance = "agree"
            observed = f"{cited}에는 저도 공감해요."
        else:
            stance = "disagree"
            observed = f"{cited}에는 저는 생각이 달라요."
            if p["picked"]:
                position, detail = "consider", "익숙한 것과 다른 맛이 필요하면 다시 고려해 볼래요."
            else:
                position, detail = "pass", f"제 경우에는 {condition} 다시 보겠지만 지금 조건이라면 지나칠래요."
    return {"text": f"{observed} {detail}", "choice": choice, "reply_to": peer_id, "reply_quote": quote,
            "stance": stance, "position": position, "position_quote": detail}


def _improve(system: str, user: str, schema: dict) -> dict:
    """개선안(지시서 17): 가격을 200원 낮추는 안과 1+1 행사를 붙이는 안. 까닭은 가장 많이 걸린 점의 사람 수를 든다."""
    m = re.search(r"컨셉: (.+?) / (\d+)ml (\S+) / ([\d,]+)원", user)
    name, volume, container, price = m.group(1), int(m.group(2)), m.group(3), int(m.group(4).replace(",", ""))
    b = re.search(r"걸린 점\(많은 순\): ([^,\n]+?) (\d+)명", user)
    count = b.group(2) if b else "1"
    same = {"price": price, "container": container if container in ("캔", "페트", "병", "팩") else "캔",
            "volume_ml": volume, "name": name, "promo": "없음"}
    return {"items": [
        {**same, "kind": "price", "price": price - 200, "reason": f"걸린 손님이 {count}명이라 200원 낮춰 봐요."},
        {**same, "kind": "promo", "promo": "1+1", "reason": f"처음 보는 제품에 망설인 손님이 {count}명이라 행사를 붙여 봐요."},
    ]}


def _improve_extract(system: str, user: str, schema: dict) -> dict:
    """기획자가 말한 값(지시서 17): "1,500원", "1+1", "500ml"만 낱말로 뽑는 흉내."""
    said = user.split("기획자의 말: ", 1)[-1]
    out = {"price": 0, "container": "그대로", "volume_ml": 0, "name": "", "promo": "그대로"}
    m = re.search(r"(\d{1,3}(?:,\d{3})+|\d+)\s*원", said)
    if m:
        out["price"] = int(m.group(1).replace(",", ""))
    m = re.search(r"(\d+)\s*ml", said)
    if m:
        out["volume_ml"] = int(m.group(1))
    for p in ("1+1", "2+1"):
        if p in said:
            out["promo"] = p
    return out


def _ideas_import(system: str, user: str, schema: dict) -> dict:
    """가짜 응답기는 문서의 이름 열이 명시된 표만 옮긴다."""
    items = []
    headings = []
    name_columns = {"아이디어", "아이디어 이름", "이름", "제품명", "컨셉", "컨셉명", "name"}
    for line in user.splitlines():
        columns = [cell.strip() for cell in line.split("\t")]
        if columns and any(cell in name_columns for cell in columns):
            headings = ["name" if cell in name_columns else "price" if cell == "판매가" else cell for cell in columns]
        elif headings and len(columns) == len(headings) and not line.startswith("["):
            record = dict(zip(headings, columns))
            if record.get("name"):
                items.append(record)
        else:
            headings = []
    return {"items": items}


DEFAULTS = {"ideas_import": _ideas_import, "read": _read, "trend": _trend, "ideas": _ideas, "edit_idea": _edit_idea, "my_idea": _my_idea,
            "concepts": _concepts, "edit_concept": _edit_concept, "pod": _pod, "voice": _voice,
            "proposal": _proposal, "shopper": _shopper, "interview": _interview, "improve": _improve,
            "improve_extract": _improve_extract, "group_turn": _group_turn}


class FakeLLM:
    def __init__(self, answers: dict[str, Any] | None = None) -> None:
        global _seq
        _seq = itertools.count()  # 아이디어의 기본 답을 처음부터 다시 낸다
        self.answers = dict(answers or {})
        self.calls: list[dict[str, Any]] = []

    async def ask(self, task: str, system: str, user: str, schema: dict[str, Any], *,
                  web: bool = False, timeout: float = 60.0, model: str | None = None) -> dict[str, Any]:
        if delay := float(os.environ.get("AX_FAKE_DELAY", "0")):
            await asyncio.sleep(delay)
        self.calls.append({"task": task, "system": system, "user": user, "web": web, "timeout": timeout,
                           "model": model})
        ans = self.answers.get(task, DEFAULTS.get(task))
        if isinstance(ans, list):
            ans = ans.pop(0) if ans else None
            if ans is None:
                ans = DEFAULTS.get(task)
        if isinstance(ans, BaseException) or (isinstance(ans, type) and issubclass(ans, BaseException)):
            raise ans
        if callable(ans):
            ans = ans(system, user, schema)
        if ans is None:
            raise LLMError(f"{task}: 정한 답이 없어요")
        return ans
