"""컨셉의 예시 패키지 이미지를 시키는 글. 코드가 정해진 낱말로만 만든다.

컨셉의 글(이름, 헤드라인 등)을 그대로 넣지 않는다. 정해진 사전에 있는 낱말만 영어로 옮겨 넣으므로
브랜드 이름, 사람 이름, 경로가 들어갈 길이 없다. 그래도 마지막에 브랜드 이름을 한 번 더 걷어 낸다.
같은 컨셉이면 같은 글이 나온다.
"""

from __future__ import annotations

import re
from typing import Any

# 이 저장소 trend/verdicts.py의 PRODUCT_SEARCH에 있는 브랜드와 대회 컨셉의 브랜드, 그리고 영어 표기.
BRANDS = re.compile(
    r"롯데|칠성|밀키스|레쓰비|델몬트|코카콜라|칠성사이다|펩시|칸타타|카누|세븐일레븐|쥬시모먼트|프레시원|"
    r"스타벅스|GS25|\bCU\b|lotte|chilsung|milkis|let'?s\s*be|del\s*monte|coca[- ]?cola|pepsi|cantata|kanu|"
    r"7[- ]?eleven|seven[- ]?eleven|starbucks|sprite",
    re.IGNORECASE,
)

FORBID = "no text, no letters, no logo, no trademark, no brand name, no label wording"

# 제품 종류(노트의 kind, shelf_kind). 앞에서부터 먼저 맞는 것.
KINDS = (
    ("탄산", "carbonated soft drink"),
    ("커피", "ready-to-drink coffee"),
    ("주스", "fruit juice"),
    ("과즙", "fruit juice"),
    ("이온", "sports drink"),
    ("스포츠", "sports drink"),
    ("에너지", "energy drink"),
    ("차", "tea drink"),
    ("우유", "milk drink"),
    ("유제품", "milk drink"),
    ("두유", "soy milk drink"),
    ("물", "bottled water"),
)

# 맛과 좋은 점에 나오는 재료. 긴 말을 먼저 둔다(청포도가 포도보다 먼저).
FLAVORS = (
    ("청포도", "green grape"), ("수박", "watermelon"), ("복숭아", "peach"), ("사과", "apple"),
    ("포도", "grape"), ("오렌지", "orange"), ("레몬", "lemon"), ("라임", "lime"), ("자몽", "grapefruit"),
    ("망고", "mango"), ("딸기", "strawberry"), ("감귤", "tangerine"), ("귤", "tangerine"),
    ("유자", "yuzu"), ("매실", "green plum"), ("블루베리", "blueberry"), ("바나나", "banana"),
    ("파인애플", "pineapple"), ("코코넛", "coconut"), ("키위", "kiwi"), ("체리", "cherry"),
    ("석류", "pomegranate"), ("멜론", "melon"), ("참외", "korean melon"), ("녹차", "green tea leaves"),
    ("홍차", "black tea leaves"), ("말차", "matcha"), ("커피", "coffee beans"), ("초코", "chocolate"),
    ("바닐라", "vanilla"), ("캐러멜", "caramel"), ("우유", "milk splash"), ("요거트", "yogurt"),
    ("민트", "mint leaves"), ("생강", "ginger"), ("보리", "roasted barley"), ("옥수수", "corn"),
)

# 좋은 점(포인트, 혜택)에서 뽑는 시각 단서.
CUES = (
    (("얼려", "얼음", "냉동", "프리즈", "슬러시"), "frost and ice crystals on the package"),
    (("비가열", "착즙", "생과일", "갓 짠"), "fresh-cut fruit slices beside it"),
    (("제로", "무설탕", "무가당", "저칼로리"), "light, clean color palette"),
    (("프리미엄", "고급"), "premium matte finish"),
    (("개운", "시원", "청량", "상쾌"), "cool water droplets"),
    (("여름",), "bright summery lighting"),
    (("부드러운", "크리미", "고소"), "soft creamy tones"),
)

# 용기. 앞에서부터 먼저 맞는 것.
CONTAINERS = (
    ("슬림캔", "slim aluminum can"),
    ("캔", "aluminum can"),
    ("유리", "glass bottle"),
    ("병", "glass bottle"),
    ("페트", "clear plastic bottle"),
    ("pet", "clear plastic bottle"),
    ("파우치", "spout pouch"),
    ("컵", "plastic cup with lid"),
    ("팩", "paper carton"),
)


def _first(text: str, table: tuple[tuple[str, str], ...]) -> str | None:
    low = text.lower()
    return next((en for ko, en in table if ko in low), None)


def _shelf_pack(c: dict[str, Any]) -> tuple[str, int | None]:
    """매대에 올릴 규격의 용기와 용량. 규격 표가 있으면 그 줄, 없으면 컨셉의 칸."""
    vs = c.get("variants") or []
    if vs:
        k = c.get("_shelf_variant") or 0
        v = vs[k] if isinstance(k, int) and 0 <= k < len(vs) else vs[0]
        text = f"{v.get('pack') or ''} {v.get('container') or ''}"
        vol = v.get("volume_ml")
    else:
        text = f"{c.get('pack') or ''} {c.get('_container') or ''}"
        vol = c.get("_volume")
        if not vol:
            m = re.search(r"(\d{2,4})\s*m[lL]", c.get("pack") or "")
            vol = int(m.group(1)) if m else None
    try:
        vol = int(vol) if vol else None
    except (TypeError, ValueError):
        vol = None
    return _first(text, CONTAINERS) or "beverage bottle", vol


def build(concept: dict[str, Any], note: dict[str, Any] | None = None) -> str:
    """컨셉(대화 노트의 concepts 한 칸)과 노트에서 시키는 글을 만든다."""
    note = note or {}
    kind = _first(f"{note.get('kind') or ''} {note.get('shelf_kind') or ''}", KINDS) or "beverage"
    container, volume = _shelf_pack(concept)
    size = f"{volume} ml " if volume else ""

    points = " ".join(str(p) for p in (concept.get("points") or []))
    taste_text = " ".join(str(concept.get(k) or "") for k in ("_flavor", "flavor", "name")) + " " + points
    fruits: list[str] = []
    for ko, en in FLAVORS:
        if ko in taste_text:
            taste_text = taste_text.replace(ko, " ")  # 청포도를 찾은 뒤 포도를 다시 찾지 않게
            if en not in fruits:
                fruits.append(en)
    fruits = fruits[:3]
    flavor = " and ".join(fruits) if fruits else "its flavor"

    cue_text = " ".join(str(concept.get(k) or "") for k in ("benefit", "headline", "season", "storage")) + " " + points
    cues = [en for words, en in CUES if any(w in cue_text for w in words)]
    carb = concept.get("_carb") or ""
    if "탄산" in kind or (carb and carb not in ("없음", "무탄산")) or kind == "carbonated soft drink":
        cues.insert(0, "tiny fizzy bubbles")

    parts = [
        f"Studio product photo of a single {kind} package mockup",
        f"one {size}{container}",
        f"colors and an illustration of {flavor} that evoke the taste" if fruits else "colors that evoke the taste",
        *cues,
        "plain solid-color background, front view, centered, soft studio light",
        FORBID,
        "a generic unbranded design",
    ]
    text = ", ".join(parts) + "."
    return re.sub(r"\s{2,}", " ", BRANDS.sub("", text))
