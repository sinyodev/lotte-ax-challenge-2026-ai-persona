"""매대에 올릴 제품을 고르고, 제품의 특징과 "채워준다" 연결을 만든 뒤, 욕구가 제품을 가르는지 검사한다.

실행:
    python3 scripts/build_shelves.py

입력:  data/ours/beverage_shelf_candidates.csv   (CU 정가 + 세븐일레븐 행사)
       data/ours/alcohol_shelf_candidates.csv    (세븐일레븐 주류 행사 + 한국소비자원 기본 가격)
       data/ours/needs.csv                       (욕구 목록)
출력:  data/ours/shelf_products.csv              (매대 제품, 판매조건, 특징)
       data/ours/fulfills.csv                    (제품 x 욕구의 채워주는 정도와 적용한 규칙)
       data/ours/needs_coverage.csv              (욕구마다 잘 채움·조금 채움·못 채움·거스름 제품 수)

이 파일에 적힌 것은 우리의 판단이다.
- 어떤 제품을 매대에 올릴지(아래 BEVERAGES, ALCOHOLS)는 사람이 골랐다. 종류마다 우리 제품과 다른 회사 제품을 함께 넣었다.
- 특징(당, 카페인, 탄산, 도수 구간 등)은 상품명과 일반 지식으로 적은 것이다. 근거 유형은 "가정"이다.
  식품영양성분 공공 자료와 제조사 정보로 바꿔 넣어야 한다(docs/data-sources.md 2, 3절).
- 채워주는 정도는 아래 규칙으로 정한다. 규칙을 고치면 표 전체가 다시 만들어진다.
"""

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OURS = ROOT / "data" / "ours"
WELL, SOME, NONE, AGAINST = "잘 채움", "조금 채움", "못 채움", "거스름"

# (CU 상품명, 종류, 당, 카페인, 탄산, 성분, 널리 알려진 브랜드)
#   당: 가당 / 제로(감미료) / 저당 / 무가당(단맛 없음)      카페인: 많음 / 조금 / 없음
BEVERAGES = [
    ("롯데)칠성사이다캔355ml", "탄산", "가당", "없음", True, "", True),
    ("롯데)칠성사이다제로P500", "탄산", "제로", "없음", True, "", True),
    ("롯데)펩시콜라캔355ml", "탄산", "가당", "조금", True, "", True),
    ("롯데)펩시제로라임P500ml", "탄산", "제로", "조금", True, "", True),
    ("롯데)밀키스캔340ml", "탄산", "가당", "없음", True, "", True),
    ("롯데)마운틴듀캔355ml", "탄산", "가당", "조금", True, "", False),
    ("코카)코카콜라캔350ml", "탄산", "가당", "조금", True, "", True),
    ("코카)코카콜라제로P500ml", "탄산", "제로", "조금", True, "", True),
    ("코카)스프라이트캔355ml", "탄산", "가당", "없음", True, "", True),
    ("코카)스프라이트제로P500", "탄산", "제로", "없음", True, "", True),
    ("동아)나랑드사이다P500ml", "탄산", "제로", "없음", True, "", False),
    ("코카)환타파인P600ml", "탄산", "가당", "없음", True, "", True),
    ("롯데)핫식스캔250ml", "에너지", "가당", "많음", True, "", True),
    ("롯데)핫식스더킹제로캔355", "에너지", "제로", "많음", True, "", True),
    ("코카)몬스터에너지캔355ml", "에너지", "가당", "많음", True, "", True),
    ("동서)레드불캔355ml", "에너지", "가당", "많음", True, "", True),
    ("롯데)게토레이레몬600ml", "이온", "가당", "없음", False, "전해질", True),
    ("롯데)게토레이제로P600ml", "이온", "제로", "없음", False, "전해질", True),
    ("동아)포카리스웨트P620ml", "이온", "가당", "없음", False, "전해질", True),
    ("코카)파워에이드P600ml", "이온", "가당", "없음", False, "전해질", True),
    ("롯데)칸타타스윗아메리230", "커피", "가당", "많음", False, "", True),
    ("롯데)칸타타블랙아메320ml", "커피", "무가당", "많음", False, "", True),
    ("매일)바리스타라떼P475ml", "커피", "가당", "많음", False, "", True),
    ("매일)바리스타디카페325ml", "커피", "가당", "없음", False, "", True),
    ("티오피)스모키블랙캔275ml", "커피", "무가당", "많음", False, "", True),
    ("티오피)바닐라라떼캔275ml", "커피", "가당", "많음", False, "", True),
    ("스벅)카페라떼컵320ml", "커피", "가당", "많음", False, "", True),
    ("코카)조지아라떼P470ml", "커피", "가당", "많음", False, "", False),
    ("롯데)더하다보리차P500ml", "차", "무가당", "없음", False, "", False),
    ("롯데)실론티제로P500ml", "차", "제로", "조금", False, "", False),
    ("롯데)립톤복숭아P500ml", "차", "가당", "조금", False, "", True),
    ("웅진)하늘보리P500ml", "차", "무가당", "없음", False, "", True),
    ("광동)옥수수수염P500ml", "차", "무가당", "없음", False, "", True),
    ("롯데)아이시스8.0P500ml", "물", "무가당", "없음", False, "", True),
    ("광동)제주삼다수그린500ml", "물", "무가당", "없음", False, "", True),
    ("롯데)트레비레몬P500ml", "탄산수", "무가당", "없음", True, "", False),
    ("롯데)델몬트오렌지P400ml", "주스", "가당", "없음", False, "비타민", True),
    ("코카)미닛오렌지P350ml", "주스", "가당", "없음", False, "비타민", True),
    ("해태)갈아만든배P500ml", "주스", "가당", "없음", False, "", True),
    ("농심)웰치제로포도캔355", "주스", "제로", "없음", True, "", False),
    ("매일)셀렉스프로핏밀크250", "우유·단백", "저당", "없음", False, "단백질", False),
    ("남양)테이크핏프로틴초코", "우유·단백", "저당", "없음", False, "단백질", False),
    ("정식품)베지밀저당두유190", "우유·단백", "저당", "없음", False, "단백질", True),
    # 2026-11-17 보강. 실제 편의점 매출에서 우유·발효유·두유·단백질음료가 31%인데(aT 식품산업통계정보 소매 POS) 매대에는 3개뿐이었다.
    # 세분시장의 순서(흰우유, 바나나우유, 초코우유, 딸기우유 / 검은콩 두유)를 보고 골랐다. 생수도 큰 병과 싼 것을 더했다.
    ("서울)흰우유200ml", "우유·단백", "무가당", "없음", False, "칼슘", True),
    ("서울)흰우유500ml", "우유·단백", "무가당", "없음", False, "칼슘", True),
    ("서울)후레쉬우유900ml", "우유·단백", "무가당", "없음", False, "칼슘", True),
    ("빙그레)바나나우유240ml", "우유·단백", "가당", "없음", False, "", True),
    ("서울)바나나우유300ml", "우유·단백", "가당", "없음", False, "", True),
    ("남양)맛있는우유초코180ml", "우유·단백", "가당", "없음", False, "", True),
    ("남양)맛있는우유딸기180ml", "우유·단백", "가당", "없음", False, "", True),
    ("매일)요구르트플레인280ml", "우유·단백", "가당", "없음", False, "유산균", True),
    ("남양)불가리스딸기150ml", "우유·단백", "가당", "없음", False, "유산균", True),
    ("남양)맛있는두유검은콩190", "우유·단백", "가당", "없음", False, "단백질", True),
    ("광동)제주삼다수그린2L", "물", "무가당", "없음", False, "", True),
    ("동원)먹는샘물무P500ml", "물", "무가당", "없음", False, "", False),
]

# (상품명, 주종, 도수 구간, 당, 묶음이 아닌 낱개의 모양, 널리 알려진 브랜드, 수입·특별, 한정·협업)
#   도수 구간: 무알콜 / 낮음(5도 이하) / 중간(6~9도) / 높음(13도 이상)   당: 보통 / 제로(제로슈거·무가당) / 달콤(과일맛·가당)
ALCOHOLS = [
    ("오비)카스500ml캔", "맥주", "낮음", "보통", "캔", True, False, False),
    ("오비)카스라이트500ml캔", "맥주", "낮음", "제로", "캔", True, False, False),
    ("오비)한맥500ml캔", "맥주", "낮음", "보통", "캔", False, False, False),
    ("테라(500ml)", "맥주", "낮음", "보통", "캔", True, False, False),
    ("롯데)클라우드500ml캔", "맥주", "낮음", "보통", "캔", True, False, False),
    ("롯데)클라우드355ml캔", "맥주", "낮음", "보통", "캔", True, False, False),
    ("롯데)클라우드퓨린컷다운500ml", "맥주", "낮음", "제로", "캔", False, False, False),
    ("롯데)클라우드468ml캔(6입)", "맥주", "낮음", "보통", "캔", True, False, False),
    ("오비)카스370ml캔(6입)", "맥주", "낮음", "보통", "캔", True, False, False),
    ("하이네)하이네켄500ml캔(4입)", "맥주", "낮음", "보통", "캔", True, True, False),
    ("아사히)아사히생맥주캔340ml", "맥주", "낮음", "보통", "캔", True, True, False),
    ("비어)칭따오맥주500ml캔", "맥주", "낮음", "보통", "캔", True, True, False),
    ("오비)호가든500ml캔", "맥주", "낮음", "보통", "캔", True, True, False),
    ("제주)곰표밀맥주500ml캔", "맥주", "낮음", "보통", "캔", False, False, True),
    ("롯데)클라우드논알콜릭350ml", "논알콜", "무알콜", "보통", "캔", False, False, False),
    ("오비)카스제로0.00 350ml캔", "논알콜", "무알콜", "보통", "캔", True, False, False),
    ("하이트)하이트제로500ml캔", "논알콜", "무알콜", "제로", "캔", False, False, False),
    ("처음처럼(360ml)", "소주", "높음", "보통", "병", True, False, False),
    ("참이슬 후레쉬(360ml)", "소주", "높음", "보통", "병", True, False, False),
    ("롯데)새로소주360ml병 6팩", "소주", "높음", "제로", "병", True, False, False),
    ("진로)진로라이트360ml병", "소주", "높음", "제로", "병", True, False, False),
    ("롯데)처음처럼빠삐코360ml병", "소주", "높음", "달콤", "병", False, False, True),
    ("진로)메로나에이슬360ml병", "소주", "높음", "달콤", "병", False, False, True),
    ("롯데)순하리레몬진4.5 355ml캔", "하이볼·RTD", "낮음", "달콤", "캔", False, False, False),
    ("롯데)순하리레몬진7.0 500ml캔", "하이볼·RTD", "중간", "달콤", "캔", False, False, False),
    ("롯데)순하리레몬진제로나인500ml", "하이볼·RTD", "중간", "제로", "캔", False, False, False),
    ("산토리)짐빔하이볼레몬350ml캔", "하이볼·RTD", "중간", "달콤", "캔", False, True, False),
    ("산토리)호로요이피치350ml캔", "하이볼·RTD", "낮음", "달콤", "캔", False, True, False),
    ("세븐브로이)하이볼에빠진레몬500", "하이볼·RTD", "중간", "달콤", "캔", False, True, False),
    ("서울장수생막걸리(750ml)", "막걸리", "중간", "보통", "병", True, False, False),
    ("롯데)로제청하스파클링295ml병", "청주·와인", "중간", "달콤", "병", False, True, False),
    ("타임)와인글라스까버네187ml", "청주·와인", "높음", "보통", "병", False, True, False),
]


def per_100ml(price: float, ml: float) -> float:
    return price / ml * 100 if ml else 0


def beverage_rules(p: dict) -> dict:
    kind, sugar, caffeine, fizzy, extra = p["종류"], p["당"], p["카페인"], p["탄산"] == "있음", p["성분"]
    price, unit = p["가격(원)"], per_100ml(p["가격(원)"], p["용량(ml)"])
    plain = sugar == "무가당"
    r = {}
    r["N01"] = (WELL, "널리 알려진 브랜드") if p["알려진 브랜드"] == "예" else (SOME, "덜 알려진 브랜드")
    r["N02"] = (WELL, "정가 1,500원 이하") if price <= 1500 else (SOME, "정가 2,200원 이하") if price <= 2200 else \
               (AGAINST, "정가 3,000원 이상") if price >= 3000 else (NONE, "정가 2,200원 초과 3,000원 미만")
    r["N03"] = (WELL, "1+1") if p["행사"] == "1+1" else (SOME, p["행사"]) if p["행사"] != "행사 없음" else (NONE, "행사 없음")
    r["N04"] = (WELL, "100ml당 330원 이하") if unit <= 330 else (SOME, "100ml당 450원 이하") if unit <= 450 else \
               (AGAINST, "100ml당 800원 이상") if unit >= 800 else (NONE, "100ml당 450원 초과 800원 미만")
    r["N05"] = (WELL, "제로 또는 단맛 없음") if sugar in ("제로", "무가당") else (SOME, "저당") if sugar == "저당" else (AGAINST, "당이 든 제품")
    r["N06"] = (AGAINST, "감미료를 쓴 제로 제품") if sugar == "제로" else (WELL, "물·무가당 차·블랙커피") if plain else (NONE, "당이나 첨가물이 든 제품")
    r["N07"] = (WELL, "당이 든 원래의 맛") if sugar == "가당" else (SOME, "제로·저당으로 낸 맛") if sugar in ("제로", "저당") else (NONE, "단맛 없음")
    r["N08"] = (NONE, "신상품·한정 표시를 아직 수집하지 못함")
    r["N09"] = (WELL, "탄산음료") if kind == "탄산" else (SOME, "탄산수·무가당 차·물") if kind in ("탄산수", "물") or (kind == "차" and plain) else (NONE, "식사와 잘 곁들이지 않는 종류")
    r["B01"] = (WELL, "카페인 많음") if caffeine == "많음" else (SOME, "카페인 조금") if caffeine == "조금" else (NONE, "카페인 없음")
    r["B03"] = (WELL, "물·탄산수·무가당 차") if plain and kind in ("물", "탄산수", "차") else \
               (SOME, "이온음료 또는 탄산음료") if kind in ("이온", "탄산") else (NONE, "진하거나 걸쭉한 종류")
    r["B04"] = (WELL, "단백질") if extra == "단백질" else (SOME, extra) if extra else (NONE, "내세우는 성분 없음")
    return r


def alcohol_rules(p: dict) -> dict:
    kind, abv, sugar, pack, shape = p["종류"], p["도수 구간"], p["당"], p["묶음 수량"], p["모양"]
    price, unit = p["가격(원)"], per_100ml(p["가격(원)"] / p["묶음 수량"], p["용량(ml)"])
    r = {}
    r["N01"] = (WELL, "널리 알려진 브랜드") if p["알려진 브랜드"] == "예" else (SOME, "덜 알려진 브랜드")
    r["N02"] = (WELL, "내는 돈 2,000원 이하") if price <= 2000 else (SOME, "내는 돈 3,000원 이하") if price <= 3000 else (AGAINST, "내는 돈 4,500원 이상") if price >= 4500 else (NONE, "내는 돈 3,000원 초과 4,500원 미만")
    r["N03"] = (WELL, "묶음 할인") if pack > 1 else (SOME, p["행사"]) if p["행사"] != "행사 없음(기본 가격)" else (NONE, "행사 없음")
    r["N04"] = (WELL, "100ml당 450원 이하") if unit <= 450 else (SOME, "100ml당 600원 이하") if unit <= 600 else (AGAINST, "100ml당 900원 이상") if unit >= 900 else (NONE, "100ml당 600원 초과 900원 미만")
    r["N05"] = (WELL, "제로슈거·라이트·무알콜") if sugar == "제로" or abv == "무알콜" else (AGAINST, "달콤한 과일맛 술") if sugar == "달콤" else (NONE, "보통의 술")
    r["N06"] = (AGAINST, "감미료를 쓴 제로 제품") if sugar == "제로" else (SOME, "맥주·막걸리·와인") if kind in ("맥주", "막걸리", "청주·와인") and sugar == "보통" else (NONE, "첨가물이 든 종류")
    r["N07"] = (WELL, "달콤하거나 진한 맛") if sugar == "달콤" or p["수입·특별"] == "예" else (NONE, "라이트·무알콜") if sugar == "제로" or abv == "무알콜" else (SOME, "보통의 맛")
    r["N08"] = (WELL, "한정·협업 제품") if p["한정·협업"] == "예" else (SOME, "하이볼류") if kind == "하이볼·RTD" else (NONE, "늘 있는 제품")
    r["N09"] = (WELL, "반주로 마시는 주종") if kind in ("소주", "맥주", "막걸리") and sugar != "달콤" else (SOME, "곁들일 수 있는 주종")
    r["A01"] = (WELL, "무알콜") if abv == "무알콜" else (SOME, "5도 이하") if abv == "낮음" else (AGAINST, "13도 이상") if abv == "높음" else (NONE, "6~9도")
    r["A02"] = (WELL, "13도 이상") if abv == "높음" else (SOME, "6~9도") if abv == "중간" else (AGAINST, "무알콜") if abv == "무알콜" else (NONE, "5도 이하")
    r["A03"] = (WELL, "묶음이나 큰 병") if pack > 1 or p["용량(ml)"] >= 640 else (SOME, "따라 나눠 마시는 병") if shape == "병" and p["용량(ml)"] >= 300 else (NONE, "낱개 캔")
    r["A04"] = (AGAINST, "묶음") if pack > 1 else (WELL, "낱개 캔") if shape == "캔" else (SOME, "작은 병") if p["용량(ml)"] < 300 else (NONE, "혼자 마시기에 큰 병")
    r["A05"] = (WELL, "수입 맥주·하이볼·와인류") if p["수입·특별"] == "예" else (SOME, "한정·협업 또는 하이볼류") if p["한정·협업"] == "예" or kind == "하이볼·RTD" else (NONE, "늘 마시는 종류")
    return r


def volume_of(name: str) -> int:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|ML|L)", name) or re.search(r"(\d{3,4})$", name) or re.search(r"(\d{3})", name)
    if not m:
        return 0
    number = float(m.group(1))
    return int(number * 1000) if (len(m.groups()) > 1 and m.group(2) == "L") or number < 10 else int(number)


def main() -> None:
    needs = {r["번호"]: r for r in csv.DictReader(open(OURS / "needs.csv", encoding="utf-8")) if r["상태"] != "보류"}
    products, links, missing = [], [], []

    candidates = {r["CU 상품명"]: r for r in csv.DictReader(open(OURS / "beverage_shelf_candidates.csv", encoding="utf-8"))}
    for name, kind, sugar, caffeine, fizzy, extra, known in BEVERAGES:
        c = candidates.get(name)
        if not c:
            missing.append(name)
            continue
        matched = c["맞춘 상태"] != "못 찾음"
        p = {
            "매대": "음료", "상품명": name, "제조사": c["제조사(통일)"], "우리 제품": "예" if c["제조사(통일)"] == "롯데칠성" else "아니오",
            "종류": kind, "용량(ml)": int(c["용량(ml)"] or 0) or volume_of(name), "묶음 수량": 1, "가격(원)": int(c["CU 정가(원)"]),
            "가격 근거": "CU 홈페이지 정가", "행사": c["세븐일레븐 행사"] if matched else "행사 없음",
            "행사 근거": f"세븐일레븐 홈페이지 ({c['세븐일레븐 상품명']}, 맞춘 상태: {c['맞춘 상태']})" if matched else "세븐일레븐 행사 목록에서 찾지 못함",
            "당": sugar, "카페인": caffeine, "탄산": "있음" if fizzy else "없음", "성분": extra, "도수 구간": "", "모양": "",
            "알려진 브랜드": "예" if known else "아니오", "수입·특별": "", "한정·협업": "", "특징 근거": "가정(상품명과 일반 지식)", "확인한 날": c["확인한 날"],
        }
        products.append(p)
        for code, (degree, rule) in beverage_rules(p).items():
            if code in needs:
                links.append(["음료", name, code, needs[code]["욕구"], degree, rule])

    candidates = {r["상품명"]: r for r in csv.DictReader(open(OURS / "alcohol_shelf_candidates.csv", encoding="utf-8"))}
    for name, kind, abv, sugar, shape, known, special, limited in ALCOHOLS:
        c = candidates.get(name)
        if not c:
            missing.append(name)
            continue
        lotte = name.startswith("롯데)") or "처음처럼" in name
        p = {
            "매대": "주류", "상품명": name, "제조사": "롯데칠성" if lotte else name.split(")")[0] if ")" in name[:8] else "", "우리 제품": "예" if lotte else "아니오",
            "종류": kind, "용량(ml)": volume_of(name), "묶음 수량": int(c["묶음 수량"]), "가격(원)": int(c["표시 가격(원)"]),
            "가격 근거": c["판매처"], "행사": c["행사"], "행사 근거": c["판매처"],
            "당": sugar, "카페인": "", "탄산": "", "성분": "", "도수 구간": abv, "모양": shape,
            "알려진 브랜드": "예" if known else "아니오", "수입·특별": "예" if special else "아니오", "한정·협업": "예" if limited else "아니오",
            "특징 근거": "가정(상품명과 일반 지식)", "확인한 날": "2026-11-17",
        }
        products.append(p)
        for code, (degree, rule) in alcohol_rules(p).items():
            if code in needs:
                links.append(["주류", name, code, needs[code]["욕구"], degree, rule])

    with open(OURS / "shelf_products.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(products[0].keys()))
        writer.writeheader()
        writer.writerows(products)
    with open(OURS / "fulfills.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["매대", "상품명", "욕구 번호", "욕구", "정도", "적용한 규칙"])
        writer.writerows(links)

    # 욕구가 제품을 가르는가
    table = defaultdict(Counter)
    for shelf, _, code, need, degree, _ in links:
        table[(shelf, code, need)][degree] += 1
    size = Counter(p["매대"] for p in products)
    with open(OURS / "needs_coverage.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["매대", "욕구 번호", "욕구", WELL, SOME, NONE, AGAINST, "판정"])
        print(f"매대: {dict(size)}, 우리 제품: {dict(Counter(p['매대'] for p in products if p['우리 제품'] == '예'))}")
        if missing:
            print("후보 표에서 찾지 못한 이름:", missing)
        for (shelf, code, need), count in sorted(table.items()):
            fills = count[WELL] + count[SOME]
            verdict = "제품을 가르지 못함(모두 채움)" if fills == size[shelf] and not count[AGAINST] and count[SOME] == 0 else \
                      "제품을 가르지 못함(아무도 채우지 않음)" if fills == 0 else \
                      "빈자리 후보(잘 채우는 제품 2개 이하)" if count[WELL] <= 2 else "가름"
            writer.writerow([shelf, code, need, count[WELL], count[SOME], count[NONE], count[AGAINST], verdict])
            print(f"  {shelf} {code} {need}: 잘 {count[WELL]}, 조금 {count[SOME]}, 못 {count[NONE]}, 거스름 {count[AGAINST]} -> {verdict}")
    print("행사:", dict(Counter((p["매대"], p["행사"].split(" (")[0]) for p in products)))


if __name__ == "__main__":
    main()
