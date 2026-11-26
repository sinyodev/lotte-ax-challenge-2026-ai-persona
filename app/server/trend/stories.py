"""승인된 시연용 공개 소식과 원문 근거."""

from pathlib import Path

PHOTO_DIR = Path(__file__).with_name("photos")
PHOTOS = {
    "evening-decaf": ("evening-decaf.jpeg", "image/jpeg"),
    "frozen-smoothie": ("frozen-smoothie.jpeg", "image/jpeg"),
    "dolce-latte": ("dolce-latte.png", "image/png"),
    "dubai-desserts": ("dubai-desserts.png", "image/png"),
    "apple-tea": ("apple-tea.webp", "image/webp"),
}


def reference(source: str, day: str | None, text: str, url: str) -> dict:
    return {"source": source, "date": day, "text": text, "url": url}


def _story(
    id: str, keyword: str, kind: str, title: str, summary: str, detail: str,
    alt: str, photo_credit: str, question: str, sources: list[dict],
) -> dict:
    primary = sources[0]
    return {
        "id": id, "keyword": keyword, "title": title, "source": "web",
        "publisher": primary["source"], "url": primary["url"], "date": primary["date"],
        "verdict": None, "kind": kind, "summary": summary, "detail": detail, "sources": sources,
        "image": f"/api/trends/photos/{id}", "alt": alt, "photoCredit": photo_credit, "question": question,
    }


def stories() -> list[dict]:
    return [
        _story(
            "evening-decaf", "디카페인 커피", "커피", "CU가 매장에서 내리는 커피에 디카페인을 더했어요",
            "CU에선 냉장 디카페인 커피 매출의 28.4%가 저녁 6시부터 자정 사이에 나왔어요. CU는 저녁에도 커피를 찾는 손님을 위해 즉석 원두커피에 디카페인을 더했어요.",
            "따뜻한 아메리카노 큰 잔은 1,800원이에요. 원두커피가 잘 팔리는 점포부터 선보여요.",
            "CU 매장의 원두커피 기계 앞에서 디카페인 커피를 들고 있는 모습", "BGF리테일",
            "저녁에 마실 디카페인 커피를 편의점용으로 기획하고 싶어요.",
            [reference("BGF리테일", "2026-11-17", "저녁 6시부터 자정까지 냉장 디카페인 커피의 매출 비중은 28.4%, 같은 시간대 냉장 아메리카노는 16.9%였어요.",
                       "https://origin.bgf.co.kr/bgflive/view/?categoryId=1&id=2105")],
        ),
        _story(
            "frozen-smoothie", "냉동 과일 스무디", "과일 음료", "냉동 과일을 매장에서 바로 갈아 마시는 점포가 늘었어요",
            "냉동 컵과일을 기계에 올리면 1분 만에 스무디가 나와요. CU에서 이 스무디를 파는 곳은 7월 기준 약 300곳으로 늘었고, 누적 판매량은 50만 잔을 넘었어요.",
            "하루 중 가장 많이 팔린 때는 저녁 8시부터 10시 사이였어요.",
            "CU의 즉석 스무디 기계와 냉동 컵과일 두 종류", "BGF리테일",
            "편의점에서 얼려 먹는 과일 음료를 기획하고 싶어요.",
            [reference("BGF리테일", "2026-07-30", "7월 기준 약 300개 점포에서 팔렸고 누적 판매량은 50만 잔을 넘었어요.",
                       "https://origin.bgf.co.kr/bgflive/view/?categoryId=1&id=1988")],
        ),
        _story(
            "dolce-latte", "저당 라테", "커피", "연유 맛은 살리고 당 부담은 줄인 돌체라테",
            "칸타타가 우유와 연유의 풍미를 살린 340mL 라테를 냈어요. 달콤한 커피를 좋아해도 당 섭취는 신경 쓰는 사람을 겨냥했어요.",
            "", "칸타타 하모니 돌체라떼 340mL 병과 얼음에 따른 라테", "롯데칠성음료",
            "단맛을 살리면서 당을 줄인 라테를 기획하고 싶어요.",
            [reference("롯데칠성음료", "2026-04-02", "칸타타 하모니에 우유와 연유의 풍미를 살린 340mL 라테를 추가했어요.",
                       "https://company.lottechilsung.co.kr/kor/company/news/view.do?detailsKey=1610")],
        ),
        _story(
            "dubai-desserts", "두바이식 디저트", "디저트", "두쫀쿠 검색은 줄고, 두바이식 디저트는 늘었어요",
            "네이버에서 두쫀쿠 검색이 정점의 절반으로 줄기까지 17일이 걸렸어요. 1월엔 한정선이 두바이 찹쌀떡을 선보였고, 2월엔 이마트24가 크림빵과 마카롱을 포함한 신제품 10종을 발표했어요.",
            "", "이마트24 매대에 놓인 두바이식 디저트와 제품 단면", "이마트24",
            "두쫀쿠에서 사람들이 좋아한 점을 음료로 옮길 수 있을까요?",
            [
                reference("이마트24", "2026-02-13", "피스타치오와 카다이프를 활용한 크림빵, 마카롱 등 두바이식 디저트 10종을 발표했어요.",
                          "https://www.shinsegaegroupnewsroom.com/emart24-continues-the-dujjonku-craze-with-the-launch-of-10-new-products/"),
                reference("연합뉴스, 네이버 데이터랩 분석", "2026-02-08", "‘두쫀쿠’ 검색 빈도의 7일 평균이 최고점의 절반으로 내려오기까지 17일이 걸렸어요.",
                          "https://www.yna.co.kr/view/AKR20260206178500004"),
                reference("신세계백화점", "2026-01-19", "강남점에서 한정선은 두바이 찹쌀떡을, 오고르는 두바이식 쫀득 쿠키를 선보였어요.",
                          "https://www.shinsegaegroupnewsroom.com/shinsegae-gangnam-sweet-park-dubai-dessert-popup/"),
                reference("구글코리아, 2025년 올해의 검색어", "2025-12-04", "구글은 한국의 한 해 검색을 돌아보며 ‘두바이 초콜릿’과 홈베이킹 검색어 ‘쫀득쿠키’를 각각 소개했어요.",
                          "https://blog.google/intl/ko-kr/products/explore-get-answers/year-in-search-2025-kr/"),
            ],
        ),
    ]
