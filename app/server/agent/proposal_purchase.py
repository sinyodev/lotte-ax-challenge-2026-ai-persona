"""결과 보고서에 조사 의향과 실구매 실적을 붙인다. 현재 매대의 선택에는 가상임을 표시한다."""

from onsite.concepts import CONCEPTS
from onsite.purchase import measure_lines, outcomes, percent


def add(concept, result, report):
    name = report["head"]["product"]
    data = outcomes()
    if not data["history"] and not data["concepts"]:
        return
    current = next((r for r in data["concepts"] if r["product"] == name), None)
    historical = [r for r in data["history"] if r["product"] == name]
    known = next((c for c in CONCEPTS if c["name"] == name), None)
    category = known["kind"] if known else concept.get("_shelf_kind")
    similar = [r for r in data["history"] if category and category in (r["category"] or "") and r["product"] != name]
    if current:
        lines = measure_lines(current)
    elif len(historical) == 1:
        lines = measure_lines(historical[0])
    else:
        lines = ["이 제품의 조사 구매의향 미측정", "출시 후 12개월 실제 구매경험률 미측정"]
    views = {r["label"]: r["count"] for r in result.get("views", [])}
    answers = sum(views.get(label, 0) for label in ("이번에 산다", "다음에 살 수도 있다", "관심 없다"))
    if answers:
        positive = views.get("이번에 산다", 0) + views.get("다음에 살 수도 있다", 0)
        lines.append(f"참고 · 가상 손님 {answers}명 중 {positive}명이 ‘이번에 산다’ 또는 ‘다음에 살 수도 있다’고 응답")
    n, picked = result.get("n"), result.get("picked")
    if n and picked is not None:
        lines.append(f"참고 · 이번 가상 매대에서 고른 손님 {n}명 중 {picked}명({percent(picked / n)})")
    report["evidence"]["compare"].append({"title": "구매의향과 실제 구매", "lines": lines})
    examples = similar or (historical if len(historical) > 1 else [])
    if examples:
        lines = [f"{r['product']}({r['test_year']}년 조사) · 구매의향 {percent(r['intent_top2'])}, "
                 f"출시 후 12개월 구매경험률 {percent(r['trial_12m'])}" for r in examples]
        report["evidence"]["compare"].append({"title": "과거 컨셉테스트와 출시 실적", "lines": lines})
