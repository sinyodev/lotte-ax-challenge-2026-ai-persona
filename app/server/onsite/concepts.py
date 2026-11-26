"""과제 설명의 컨셉 보드 세 가지. 자료를 생성하기 전에도 참조할 수 있다.

맛(flavor)은 같은 표의 "한 줄"에 맛으로 적힌 것만(밀키스 화채), 규격(variants)의 shelf_life_months와 kcal은 docs/background/05-task-and-data.md 1절 "컨셉 세 가지"의
"소비기한"과 "그 밖" 줄에 적힌 값만 옮겼다(지시서 33). 적혀 있지 않으면 None이다.
"""

import re
from typing import Any

CONCEPTS = [
    {
        "id": "milkis-hwachae", "name": "밀키스 화채", "brand": "밀키스", "kind": "탄산", "flavor": "수박화채맛",
        "summary": "수박화채 맛과 과일 일러스트 패키지를 더한 여름 한정 밀키스.",
        "variants": [
            {"pack": "슬림캔", "volume_ml": 250, "price": 1200, "factory_price": 780,
             "shelf_life_months": 12, "kcal": 130},
            {"pack": "PET", "volume_ml": 500, "price": 1800, "factory_price": 1200,
             "shelf_life_months": 9, "kcal": 260},
        ],
        "storage": "상온", "season": "5~9월 한정", "launch": "2027-05",
        "channels": ["편의점", "대형마트·SSM", "온라인"], "keywords": ["수박화채"],
    },
    {
        "id": "letsbe-freeze", "name": "레쓰비 프리즈", "brand": "레쓰비", "kind": "커피", "flavor": None,
        "summary": "냉동 파우치를 슬러시처럼 먹는 레쓰비 커피.",
        "variants": [{"pack": "스파우트 파우치", "volume_ml": 170, "price": 1800,
                      "factory_price": 1250, "shelf_life_months": 12, "kcal": 100}],
        "storage": "냉동", "season": None, "launch": "2027-05",
        "channels": ["편의점(냉동)", "대형마트·SSM"], "keywords": ["얼려먹는 커피", "슬러시 커피"],
    },
    {
        "id": "juicy-moment", "name": "쥬시모먼트", "brand": "쥬시모먼트", "kind": "주스", "flavor": None,
        "summary": "과즙 100%를 비가열 HPP로 처리해 유리병에 담은 프리미엄 주스 3종.",
        # 소비기한이 개월이 아니라 45일로 적혀 있어 shelf_life_months는 비우고 shelf_life_days에 둔다. 열량은 적혀 있지 않다
        "variants": [{"pack": "유리병", "volume_ml": 300, "price": 3000, "factory_price": 2100,
                      "shelf_life_months": None, "shelf_life_days": 45, "kcal": None}],
        "storage": "냉장", "season": None, "launch": "2027-03",
        "channels": ["편의점(냉장)", "프리미엄 SSM·백화점", "온라인(새벽배송)", "카페"],
        "keywords": ["착즙주스", "프리미엄 주스"],
    },
]


# 과제의 규격 이름 → 매대의 용기(tools.shelf.CONTAINERS)
_PACK_CONTAINER = {"슬림캔": "캔", "캔": "캔", "PET": "페트", "페트": "페트", "유리병": "병", "병": "병",
                   "스파우트 파우치": "기타", "파우치": "기타", "팩": "팩"}


def _key(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def match(name: str) -> dict[str, Any] | None:
    """아이디어의 이름이 과제의 컨셉 이름과 같거나(공백·대소문자 무시) 그 이름을 담으면 그 컨셉."""
    k = _key(name)
    if not k:
        return None
    for c in CONCEPTS:
        ck = _key(c["name"])
        if k == ck or ck in k:
            return c
    return None


def container_of(pack: str) -> str:
    return _PACK_CONTAINER.get((pack or "").strip(), "기타")


def spec_of(c: dict[str, Any]) -> dict[str, Any]:
    """아이디어·컨셉에 옮겨 적는 사양(지시서 33의 1절 형식). 값은 CONCEPTS 그대로다."""
    variants = []
    for v in c.get("variants") or []:
        variants.append({
            "container": container_of(v.get("pack", "")), "pack": v.get("pack"), "volume_ml": v.get("volume_ml"),
            "price": v.get("price"), "factory_price": v.get("factory_price"),
            "shelf_life_months": v.get("shelf_life_months"), "shelf_life_days": v.get("shelf_life_days"),
            "kcal": v.get("kcal"),
        })
    return {"variants": variants, "launch": c.get("launch"), "season": c.get("season"),
            "channels": list(c.get("channels") or []), "storage": c.get("storage")}
