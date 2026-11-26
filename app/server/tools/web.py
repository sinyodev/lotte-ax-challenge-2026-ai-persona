"""웹 검색의 규칙과 결과 저장 (docs/chilseong-part1.md 4절).

- 검색 자체는 모델(흐름 찾기, agent/steps.py)이 한다. 이 파일은 받은 묶음을 코드의 규칙으로 거른다.
- 출처의 주소가 없거나 http로 시작하지 않는 주장은 버린다.
- 글의 날짜가 1년이 넘었으면 "오래된 글이에요", 날짜를 모르면 "날짜를 확인하지 못했어요".
- 결과는 제품 이름을 열쇠로 cache/web/에 저장해 같은 제품에 다시 쓴다(저장소에 올리지 않는다).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache" / "web"
MAX_CLAIMS = 3
OLD_NOTE = "오래된 글이에요"
NO_DATE_NOTE = "날짜를 확인하지 못했어요"


@dataclass
class Claim:
    text: str
    source: str
    url: str
    date: str | None
    note: str | None


def parse_date(raw: str | None) -> date | None:
    """'2026-03-05', '2026.03', '2026년 3월' 같은 글의 날짜. 일이 없으면 1일, 달이 없으면 1월로 본다."""
    if not raw:
        return None
    m = re.search(r"(20\d\d)\D{0,3}(\d{1,2})?\D{0,3}(\d{1,2})?", raw)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
    try:
        return date(y, mo, d)
    except ValueError:
        try:
            return date(y, mo, 1)
        except ValueError:
            return None


def filter_claims(raw: list[dict], today: date | None = None) -> list[Claim]:
    today = today or date.today()
    out: list[Claim] = []
    for c in raw:
        url = (c.get("url") or "").strip()
        text = (c.get("claim") or "").strip()
        if not url.startswith("http") or not text:
            continue
        d = parse_date(c.get("date"))
        if d is None:
            note, shown = NO_DATE_NOTE, None
        else:
            shown = d.isoformat()
            note = OLD_NOTE if (today - d).days > 365 else None
        out.append(Claim(text=text, source=(c.get("source") or "").strip() or url, url=url, date=shown, note=note))
        if len(out) == MAX_CLAIMS:
            break
    return out


def _path(product: str) -> Path:
    key = hashlib.sha1(product.strip().encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{key}.json"


def load(product: str) -> list[dict] | None:
    """저장해 둔 모델의 답(거르기 전). 없으면 None."""
    p = _path(product)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data["claims"] if data.get("product") == product.strip() else None
    except (json.JSONDecodeError, KeyError):
        return None


def save(product: str, claims: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path(product).write_text(json.dumps({"product": product.strip(), "claims": claims}, ensure_ascii=False, indent=1),
                              encoding="utf-8")


def as_dict(c: Claim) -> dict:
    return asdict(c)
