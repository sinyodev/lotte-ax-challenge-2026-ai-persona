"""일별 공개 자료에서 발행할 근거와 기획 질문을 고른다."""

from datetime import date, datetime, timedelta
from hashlib import sha256
import re

from . import sites
from .sources import FOOD
from .stories import reference

APPLE_EDITION = date(2026, 11, 24)
APPLE_MENU_DATE = date(2026, 9, 22)
APPLE_MENU_END = date(2026, 11, 30)
APPLE_MENU_URL = "https://ir.newspim.com/news/view/20260922000078"
APPLE_MENU = "백미당은 11월까지 사과청을 넣은 차를 따뜻하게도, 차갑게도 팔아요."
FRUIT = re.compile(r"모과|유자|사과|귤|복숭아|포도|레몬|망고|수박|딸기|오미자|라임|자두|매실|멜론")
COFFEE = re.compile(r"커피|라[테떼]|디카페인|에스프레소|아메리카노|콜드브루")
SNACK = re.compile(r"디저트|쿠키|초콜릿|빵|과자|팝콘|케이크|스낵|샌드위치|젤리|빙수|피스타치오|소르베")


def topic_key(topic: str) -> str:
    return "".join(topic.casefold().split())


def _period(ranks: list[dict]) -> str:
    first, last = date.fromisoformat(ranks[0]["day"]), date.fromisoformat(ranks[-1]["day"])
    return f"{first.month}월 {first.day}일~{last.month}월 {last.day}일"


def _apple(day: date, ranks: list[dict]) -> dict:
    count = sum(rank["rank"] is not None for rank in ranks)
    frequency = "일주일 내내" if count == 7 else f"일주일 중 {count}일"
    observation = f"‘사과’는 {frequency} 네이버 식품 쇼핑 인기 검색어 10위 안에 들었어요."
    return {
        "id": "apple-tea", "topic": "사과", "date": day.isoformat(),
        "title": "사과주스를 기획한다면, 따뜻한 사과차와도 비교해 보세요",
        "observation": observation, "menu": APPLE_MENU,
        "question": "쌀쌀한 아침, 편의점에서 같은 가격이라면 손님은 차가운 사과주스와 따뜻한 사과차 중 무엇을 고를까요?",
        "period": _period(ranks), "ranks": ranks, "searchUrl": sites.NAVER_HOME, "menuUrl": APPLE_MENU_URL,
        "sources": [
            reference("네이버 데이터랩", ranks[-1]["day"], observation, sites.NAVER_HOME),
            reference("뉴스핌, 백미당 발표", APPLE_MENU_DATE.isoformat(), APPLE_MENU, APPLE_MENU_URL),
        ],
        "image": "/api/trends/photos/apple-tea", "alt": "백미당의 사과 펀치 티와 사과 디저트", "photoCredit": "남양유업",
    }


def approved_edition(day: date) -> dict | None:
    """시연 승인 때 확인한 공개 관측값을 수집 장애 시 지난 호로 제공한다."""
    if day < APPLE_EDITION:
        return None
    ranks = [{"day": (APPLE_EDITION - timedelta(days=offset)).isoformat(), "rank": rank}
             for offset, rank in zip(range(7, 0, -1), (4, 4, 5, 5, 7, 5, 2), strict=True)]
    return _apple(APPLE_EDITION, ranks)


def _recent(row: dict, day: date, days: int) -> bool:
    observed = datetime.fromisoformat(row["when"]).date()
    return 0 <= (day - observed).days <= days


def _naver_signal(row: dict, day: date) -> tuple[dict, int] | None:
    ranks = row["week"]
    if len(ranks) != 7 or not _recent(row, day, 2):
        return None
    count = sum(point["rank"] is not None for point in ranks)
    moved_up = row["previousRank"] is not None and row["previousRank"] - row["rank"] >= 2
    if count < 5 or (row["rank"] > 3 and not moved_up):
        return None
    text = f"‘{row['topic']}’는 네이버 식품 쇼핑 인기 검색어 10위 안에 최근 일주일 중 {count}일 들었어요."
    previous = row["previousRank"]
    if previous is not None and previous > row["rank"]:
        text += f" 전날 {previous}위에서 최신 {row['rank']}위로 올랐어요."
    else:
        text += f" 최신 순위는 {row['rank']}위예요."
    return reference("네이버 데이터랩", ranks[-1]["day"], text, row["url"]), count


def _google_signal(row: dict, day: date) -> dict | None:
    if not _recent(row, day, 1):
        return None
    topic = row["topic"]
    text = f"구글 트렌드 한국 급상승 검색어에 ‘{topic}’도 올랐어요."
    if row["label"].startswith("표시 검색량 "):
        text += " " + row["label"] + "예요."
    return reference("구글 트렌드", row["when"][:10], text, row["url"])


def _planning_question(topic: str, headline: str) -> str:
    if FRUIT.search(topic):
        return f"같은 가격·용량의 기존 과일 음료와 ‘{topic}’를 담은 과일 음료를 나란히 놓고, 어느 쪽을 더 자주 고르는지 확인해 볼까요?"
    if COFFEE.search(topic):
        return f"편의점에서 ‘{topic}’를 참고한 커피와 기존 커피를 나란히 놓고, 같은 가격일 때 어느 쪽을 고르는지 확인해 볼까요?"
    if SNACK.search(topic) or SNACK.search(headline):
        return f"편의점 간식 매대에서 ‘{topic}’의 맛을 참고한 한입 간식과 기존 간식을 같은 가격에 놓고, 어떤 맛을 더 자주 고르는지 확인해 볼까요?"
    return f"‘{topic}’ 관련 식품을 편의점에서 기획할 때, 같은 식품이라도 1회분 소포장과 묶음 포장 중 어느 쪽에 손이 가는지 확인해 볼까요?"


def choose_issue(day: date, channels: dict, news: list[dict], published: set[str]) -> dict | None:
    naver_rows = channels["naver"]["rows"] if channels["naver"]["ok"] else []
    google_rows = channels["google"]["rows"] if channels["google"]["ok"] else []
    if "사과" not in published and APPLE_MENU_DATE <= day <= APPLE_MENU_END:
        for row in naver_rows:
            ranks = row["week"]
            if (topic_key(row["topic"]) == "사과" and len(ranks) == 7 and _recent(row, day, 2)
                    and sum(point["rank"] is not None for point in ranks) >= 5):
                return _apple(day, ranks)

    topics = {topic_key(row["topic"]): row["topic"] for row in [*google_rows, *naver_rows]}
    naver = {topic_key(row["topic"]): row for row in naver_rows}
    google = {topic_key(row["topic"]): row for row in google_rows}
    candidates = []
    for key, topic in topics.items():
        if key in published:
            continue
        rank_signal = _naver_signal(naver[key], day) if key in naver else None
        google_signal = _google_signal(google[key], day) if key in google else None
        context = google[key].get("context") if google_signal else None
        matched_news = next((item for item in news
                             if item["date"] <= day.isoformat() and key in topic_key(item["title"])), None)
        if not rank_signal and not (google_signal and (context or matched_news or FOOD.search(topic))):
            continue
        refs = [signal for signal in (rank_signal[0] if rank_signal else None, google_signal) if signal]
        ranks = naver[key]["week"] if rank_signal else []
        # 보도자료가 있을 때는 보도자료 제목 그대로 시장 사례를 붙인다.
        if matched_news:
            refs.append(matched_news["sources"][0])
        if context and all(context["url"] != ref["url"] for ref in refs):
            refs.append(context)
        title = f"‘{topic}’, 식품 쇼핑 검색 상위권에 올랐어요" if rank_signal else f"구글에서 ‘{topic}’ 검색이 급상승했어요"
        observation = refs[0]["text"]
        if context and not matched_news:
            observation += f" 함께 표시된 기사 제목은 ‘{context['text']}’예요."
        headline = matched_news["title"] if matched_news else context["text"] if context else ""
        priority = 10 * len(refs) + (rank_signal[1] if rank_signal else 0)
        item = {
            "id": "daily-" + sha256(key.encode()).hexdigest()[:12], "topic": topic, "date": day.isoformat(),
            "title": title, "observation": observation, "menu": matched_news["title"] if matched_news else None,
            "question": _planning_question(topic, headline),
            "period": _period(ranks) if ranks else None, "ranks": ranks,
            "searchUrl": refs[0]["url"], "menuUrl": matched_news["url"] if matched_news else None,
            "sources": refs, "image": None, "alt": None, "photoCredit": None,
        }
        candidates.append((priority, item))
    return max(candidates, key=lambda candidate: candidate[0])[1] if candidates else None
