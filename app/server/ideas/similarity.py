"""제품 속성과 기획 기록을 이용한 규칙 기반 사례 검색."""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from . import store
from .board import Entry, entries
from .models import IdeaRow

CATEGORIES = {
    "탄산": ("탄산", "소다", "스파클링", "사이다"), "커피": ("커피", "coffee"),
    "주스": ("주스", "쥬스", "juice"),
}
PACKS = {
    "파우치": ("파우치", "pouch"), "페트": ("페트", "pet"), "캔": ("캔", "can"),
    "병": ("병", "bottle"), "팩": ("팩", "carton"), "컵": ("컵", "cup"),
}
FLAVORS = (
    "수박", "딸기", "포도", "청포도", "복숭아", "자몽", "오렌지", "사과", "레몬", "라임", "매실", "청귤",
    "망고", "파인애플", "유자", "보리", "생강", "말차", "바닐라", "초콜릿", "카카오", "밀크티", "요거트",
)
TRAITS = {
    "얼려 먹는 형태": ("냉동", "얼려", "슬러시", "프리즈", "freeze", "frozen"),
    "착즙": ("착즙",), "비가열": ("비가열", "hpp"), "프리미엄": ("프리미엄", "premium"),
    "시즌 한정": ("여름한정", "시즌한정", "계절한정", "한정판"),
}


def normalized(text: str | None) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text or "").casefold())


def _groups(text: str, groups: Mapping[str, tuple[str, ...]]) -> set[str]:
    return {label for label, words in groups.items() if any(word in text for word in words)}


def _flavors(text: str, flavor: str = "") -> set[str]:
    found = {word for word in FLAVORS if word in text}
    if flavor and len(flavor) >= 2 and flavor in text:
        found.add(flavor)
    return found


def _prices(text: str | int | None) -> list[int]:
    if isinstance(text, int):
        return [text] if text > 0 else []
    text = unicodedata.normalize("NFKC", text or "")
    price = r"\d[\d,]*"
    amounts = re.findall(rf"(?:({price})\s*[-~–]\s*)?({price})\s*(?:원|KRW)|[₩￦]\s*({price})", text, re.I)
    return [int(amount.replace(",", "")) for group in amounts for amount in group if amount]


def _volumes(text: str) -> set[int]:
    return {int(v) for v in re.findall(r"(\d+)\s*ml", unicodedata.normalize("NFKC", text).casefold())}


def similar(concept: Mapping) -> list[dict]:
    """같은 이름·브랜드, 또는 적어도 두 가지 속성에서 겹친 과거를 점수순으로 돌려준다."""
    return _similar(concept, entries())


def _similar(concept: Mapping, candidates: Iterable[Entry]) -> list[dict]:
    variants = concept.get("variants") or []
    query_name = normalized(concept.get("name"))
    brand = normalized(concept.get("brand"))
    category = normalized(concept.get("category") or concept.get("kind"))
    pack = " ".join(filter(None, (concept.get("pack"), concept.get("_container"), *(
        f"{v.get('pack') or ''} {v.get('volume_ml') or ''}ml" for v in variants
    ))))
    packs = _groups(normalized(pack), PACKS)
    volumes = _volumes(pack)
    flavor = normalized(concept.get("flavor") or concept.get("_flavor")).removesuffix("맛").removesuffix("향")
    detail = normalized(" ".join(filter(None, (concept.get("name"), concept.get("summary"), concept.get("headline"),
                                                concept.get("benefit"), flavor, *(concept.get("keywords") or []),
                                                *(concept.get("points") or [])))))
    flavors = _flavors(detail, flavor)
    traits = _groups(detail, TRAITS)
    categories = _groups(category, CATEGORIES) or {category} - {""}
    prices = _prices(concept.get("price")) + [p for v in variants for p in _prices(v.get("price"))]

    ranked = []
    for entry in candidates:
        row = entry.row
        name = normalized(row.name)
        if row.id == concept.get("id") or (row.chat_id and row.chat_id == concept.get("chat_id") and name == query_name):
            continue
        text = normalized(f"{row.name} {row.concept or entry.description}")
        own_category = normalized(row.category)
        own_categories = _groups(own_category, CATEGORIES) or {own_category} - {""}
        matched_flavors = flavors & _flavors(text, flavor)
        matched_traits = traits & _groups(text, TRAITS)
        matched_packs = packs & _groups(normalized(row.pack), PACKS)
        known_prices = _prices(row.price)
        nearby_price = any(min(a, b) > 0 and abs(a - b) <= 0.25 * max(a, b) for a in prices for b in known_prices)
        matches = [
            (5, "같은 이름", bool(query_name and name == query_name)),
            (4, "같은 브랜드", bool(brand and brand == normalized(row.brand))),
            (2, "같은 종류", bool(categories & own_categories)),
            (2, "같은 용기", bool(matched_packs)),
            (1, "같은 용량", bool(volumes & _volumes(row.pack or ""))),
            (4, f"맛·향: {', '.join(sorted(matched_flavors))}", bool(matched_flavors)),
            (4, "얼려 먹는 형태", "얼려 먹는 형태" in matched_traits),
            (2, f"제품 특징: {', '.join(sorted(matched_traits - {'얼려 먹는 형태'}))}",
             bool(matched_traits - {"얼려 먹는 형태"})),
            (1, "비슷한 가격대", nearby_price),
        ]
        score = sum(weight for weight, _, hit in matches if hit)
        labels = [label for _, label, hit in matches if hit]
        if score >= 4 and (len(labels) > 1 or any(label in labels for label in ("같은 이름", "같은 브랜드"))):
            ranked.append({**row.model_dump(), "score": score, "matches": labels})
    return sorted(ranked, key=lambda row: row["score"], reverse=True)


CASE_STATUSES = {"출시", "단종", "폐기"}
QUERY_STOPWORDS = {
    "과거", "관련", "기록", "기획", "기획하고", "내부", "대한", "보여", "비슷한", "사례",
    "있어", "있어요", "자료", "찾아", "찾아줘", "출시", "단종", "중단", "확인해", "확인하고",
    "했어요", "해주세요", "주세요", "되는", "있는", "했던", "하려고", "하고", "싶어요", "아이디어",
    "검토하고", "만들고", "제품", "개발",
    "트렌드",
    "docx", "xlsx", "pptx", "pdf", "csv", "txt",
}
PARTICLE = re.compile(r"(?<=[가-힣]{2})(?:으로|에서|에는|부터|까지|보다|처럼|은|는|이|가|을|를|의|에|와|과|도|로)$")


def _query_terms(text: str) -> list[str]:
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text[:2000]).casefold())
    terms = dict.fromkeys(PARTICLE.sub("", word) for word in words if len(word) >= 2 and word not in QUERY_STOPWORDS)
    return [term for term in terms if term not in QUERY_STOPWORDS]


def _case_score(terms: list[str], fields: list[str | None]) -> tuple[int, list[str]]:
    values = [normalized(field) for field in fields if field]
    if len(terms) == 1:
        term = terms[0]
        if any(term in value for value in values):
            return (20 if term in values else 10), [term]
        return 0, []

    hits: list[str] = []
    for term in sorted(terms, key=len, reverse=True):
        if not any(term in hit for hit in hits) and any(term in value for value in values):
            hits.append(term)
    if len(hits) < 2:
        return 0, []
    phrase = "".join(terms)
    return 20 * len(hits) + 10 * any(phrase in value for value in values), hits


def case_status(row: IdeaRow) -> str | None:
    if row.status in CASE_STATUSES:
        return row.status
    return "출시" if row.was_launched else None


def _historical_entries() -> list[Entry]:
    return [entry for entry in entries() if case_status(entry.row)]


@dataclass(frozen=True)
class CaseHit:
    entry: Entry
    conditions: list[str]


def matching_cases(q: str, *, concept: Mapping | None = None) -> list[CaseHit]:
    """기획 원문과 진행 기록까지 검색하고 같은 단어만 겹치는 사례는 걸러낸다."""
    terms = _query_terms(q)
    if not terms and not concept:
        return []
    candidates = _historical_entries()
    attributes = {row["id"]: row for row in _similar(concept, candidates)} if concept else {}
    logs = store.case_log_text([entry.row.id for entry in candidates]) if terms else {}
    ranked = []
    for entry in candidates:
        row = entry.row
        fields = [row.name, row.brand, row.category, row.pack, row.price, row.launched_on, entry.description,
                  row.concept, row.reason, row.verdict, row.last_work, row.work_date]
        fields.extend(logs.get(row.id, ()))
        fields.extend(record.text for record in entry.chat_records)
        score, conditions = _case_score(terms, fields)
        if attribute := attributes.get(row.id):
            score += attribute["score"]
            conditions.extend(attribute["matches"])
        if score:
            ranked.append((score, CaseHit(entry, conditions)))
    return [hit for _, hit in sorted(ranked, key=lambda pair: pair[0], reverse=True)]


def search_cases(q: str) -> list[IdeaRow]:
    """보드 검색에서 사용할 출시·단종·개발 중단 행의 목록."""
    if q.strip():
        return [hit.entry.row for hit in matching_cases(q)]
    return [entry.row for entry in _historical_entries()]
