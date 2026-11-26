"""음용 상황의 화면에 보이는 이름.

자료(data/ours/occasions.csv)의 상황 이름은 가상 소비자에게 가는 글과 저장된 답의 열쇠에 그대로 쓰인다.
그래서 자료는 두고, 화면·칠성이의 말·보고서로 나가는 길에서만 이 대응표로 바꿔 보인다.
"식사와 함께"는 기록의 정의(식사 자리에서 마신 것: 식사 중과 직후)를 살려 "식사할 때 입가심"으로 부른다(참가자 검수, 11-25).
"""

from __future__ import annotations

SHOWN: dict[str, str] = {
    "밖에서 식사와 함께": "밖에서 식사할 때 입가심",
    "집에서 식사와 함께": "집에서 식사할 때 입가심",
}

_BACK = {new: old for old, new in SHOWN.items()}


def show(name: str) -> str:
    """자료의 이름이면 화면의 이름, 아니면 그대로."""
    return SHOWN.get(name, name) if isinstance(name, str) else name


def data_name(name: str) -> str:
    """화면의 이름이면 자료의 이름, 아니면 그대로."""
    return _BACK.get(name, name) if isinstance(name, str) else name


def same(a: str, b: str) -> bool:
    """옛 이름과 새 이름을 같은 상황으로 본다."""
    return data_name(a.strip()) == data_name(b.strip())
