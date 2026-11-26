"""9차와 같은 손님과 매대를 쓰는 11차 입력. 욕구 코드와 매대 번호로 세 관계를 잇는다."""

import json

from shelftest import method
from tools.shelf_items import FEATURE_LABELS
import pilot


GUIDE = """
입력 JSON의 평소_욕구는 조사로 추정한 0~3점이고, 상황별_욕구_변화는 그 상황에서의 증감(-2~+2)입니다.
종류별_월_구매_횟수는 그 종류 전체의 횟수입니다. 상품별 충족 정도는 상품 특징과 판매 조건에 적용한 규칙의 판단입니다.
욕구마다 해당 매대 번호를 모았습니다.
표시된 단서를 참고해 평소 습관과 오늘 사정에 맞게 결정하세요. 표에 없는 연결은 알 수 없습니다.
1+1은 한 개 값으로 두 개, 2+1은 두 개 값으로 세 개입니다. 집이나 일터에 있는 것으로 해결할 수도 있습니다."""


def profile(ctx, visit):
    uid, occasion = visit["uuid"], visit["상황 번호"]
    age, job, province, family, story, food = ctx["text"][uid]
    h = ctx["profiles"][uid]
    assigned = ctx["purchase_habits"].get(uid, {})
    strength = ctx["strength"][uid]
    shifts = ctx["shifts"].get(occasion, {})
    sources = ctx["shift_sources"].get(occasion, {})
    codes = [n["번호"] for n in ctx["needs"]]
    return {
        "손님": {
            "나이": age, "성별": visit["성별"], "직업": job, "거주지": province, "가구": family,
            "생활": story, "식습관": food,
        },
        "평소_습관": {
            "음료_선호_순서": [h[k] or None for k in ("좋아하는 음료 1순위", "2순위", "3순위")],
            "자주_사는_상품": [ctx["display"][key] for key in assigned.get("products", [])],
            "종류별_월_구매_횟수": assigned.get("monthly", {}),
            "제로_음료_빈도": h["제로 음료 빈도"],
            "다이어트_관심_5점": int(h["다이어트 관심(1~5)"]) if h["다이어트 관심(1~5)"] else None,
            "건강_관심_5점": int(h["건강 관심(1~5)"]) if h["건강 관심(1~5)"] else None,
            "규칙적_운동": h["규칙적 운동"],
        },
        "평소_욕구": {code: int(strength[code]) for code in codes if strength.get(code) not in ("", None)},
        "오늘_상황": {
            "상황": ctx["occasions"][occasion]["상황"], "설명": ctx["occasions"][occasion]["풀어 쓴 설명"],
            "월": visit.get("visit_month"), "월평균_기온": visit.get("temp_c"),
        },
        "상황별_욕구_변화": {code: {"변화": shifts[code], "근거": sources[code]} for code in codes if code in shifts},
    }


# 컨셉을 보이는 방식. "blind-v1"은 고르는 물음에서 새 상품을 따로 짚지 않고(번호·지시 없음) 다른 제품과 같은 줄로 보인 뒤,
# 고른 것이 정해진 다음에 따로 새 상품에 대한 생각을 묻는다(runner._ask). 값이 없으면 옛 방식(같은 글에서 새_상품_번호를 짚음).
# 옛 방식은 가짜 신제품 검사에서 기존 제품의 선택을 크게 부풀렸다(docs/reliability.md "컨셉을 짚어 묻는 방식의 부풀림").
BLIND = "blind-v1"


def blind(plan: method.Plan) -> bool:
    return plan.round_number == 11 and plan.with_concept.get("choice_method") == BLIND


def prompts(plan: method.Plan, visit: dict, condition: str):
    concept = condition == method.CONCEPT
    marked = concept and not blind(plan)
    ctx = plan.with_concept if concept else plan.plain
    order = pilot.shelf_order(ctx["products"], visit, condition, 1, 9)
    system = pilot.shopper_system(ctx["needs"], 9) + GUIDE
    payload = profile(ctx, visit)
    shelf = []
    matches = {need["번호"]: {} for need in ctx["needs"]}
    for number, row in enumerate(order, 1):
        key = row["상품명"]
        item = {"번호": number, "이름": ctx["display"].get(key, key), "가격_원": int(row["가격(원)"])}
        if row["행사"] and not row["행사"].startswith("행사 없음"):
            item["행사"] = row["행사"]
        if int(row["묶음 수량"]) > 1:
            item["묶음_수량"] = int(row["묶음 수량"])
        if concept and key == plan.line:
            if marked:
                payload["새_상품_번호"] = number
            else:  # 실제 매대처럼 신상품 꼬리표만 단다(N08의 '매대에서 확인되는 것'). 가짜 신제품 검사로 부풀리지 않음을 확인했다.
                item["표시"] = "신상품"
            if plan.storage in ("냉장", "냉동"):
                item["진열"] = plan.storage
            for label in (*FEATURE_LABELS.values(), "용기", "용량(ml)"):
                if row.get(label):
                    item[label] = row[label]
        shelf.append(item)
        for code, degree in ctx["fulfills"].get(key, {}).items():
            if code in matches:
                matches[code].setdefault(degree, []).append(number)
    payload.update({"비구매_번호": 0, "매대": shelf, "욕구별_상품_번호": matches})
    if marked:
        system += "\n새 상품도 평소처럼 비교하고 무엇을 골랐든 새_상품_번호에 대한 생각을 new_product에 적으세요. 출시 전이므로 매대 표기로 판단하세요."
    return system, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), order


# ---------- blind-v1: 고른 뒤에 새 상품에 대한 생각을 따로 묻는다 ----------

OPINION_VIEWS = [v for v in method.VIEWS if v != "이번에 산다"]
OPINION = """

[이미 고른 것]
위 매대에서 {chosen} 골랐습니다. 이 결정은 바뀌지 않습니다.

[하나 더]
매대의 {number}번 '{name}'은 출시 전 새 상품입니다. 매대 표기만 보고 이 사람이 든 생각을 new_product에 적으세요.
마셔 본 것처럼 말하지 마세요."""


def opinion_prompt(plan: method.Plan, user: str, order: list, chosen: dict) -> str:
    """고르는 물음의 글 뒤에, 고른 것을 못 박고 새 상품에 대한 생각만 묻는 말을 붙인다."""
    display = plan.with_concept["display"]
    number = next(i for i, row in enumerate(order, 1) if row["상품명"] == plan.line)
    picked = ("아무것도 사지 않기로(0번)" if chosen["number"] == 0
              else f"{chosen['number']}번 '{display.get(chosen['product'], chosen['product'])}'을(를)")
    return user + OPINION.format(chosen=picked, number=number, name=display.get(plan.line, plan.line))


def opinion_schema() -> dict:
    new = json.loads(json.dumps(method.schema(True)["properties"]["new_product"]))
    new["properties"]["view"]["enum"] = OPINION_VIEWS
    new["properties"]["view"]["description"] = "새 제품을 보는 눈"
    return {"type": "object", "additionalProperties": False, "required": ["new_product"],
            "properties": {"new_product": new}}


def parse_opinion(raw) -> dict:
    new = raw.get("new_product") if isinstance(raw, dict) else None
    if not isinstance(new, dict) or new.get("view") not in OPINION_VIEWS:
        raise method.BadAnswer("새 제품에 대한 생각이 없어요")
    barriers = [b for b in new.get("barriers") or [] if b in method.BARRIERS]
    return {"view": new["view"], "barriers": barriers, "said": str(new.get("said") or "").replace("\n", " ")}
