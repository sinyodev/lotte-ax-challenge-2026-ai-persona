"""조사 답을 가상 소비자에게 나눠 준다 (약속 v1.20 "조사 답을 가상 소비자에게 더하기").

- 더하는 것: 낼 수 있는 가격(wtp), 의견의 갈래. 구매의향(intent)은 배정 파일에 확인용으로만 둔다.
- 성별을 맞추고(그 성별의 응답이 없으면 전체) 조사 가중치의 비율대로 나눈다. 가상 소비자는 씨앗으로 섞고 응답자는 값의
  차례로 늘어놓아 같은 간격으로 뽑는다(체계적 배정). 그래서 전체 비율이 조사와 맞고 다시 해도 같다.
- 줄은 조사에서 답한 사실만 적는다. 응답자가 쓴 의견의 글은 쓰지 않는다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from calibrate import followup

SEED = "followup-overlay-v1"
_CACHE: dict[tuple, dict[str, Any]] = {}


def _order(uuid: str) -> str:
    return hashlib.md5(f"{SEED}|{uuid}".encode()).hexdigest()


def _person(p: Any) -> tuple[str, str | None]:
    return (p["uuid"], p.get("sex")) if isinstance(p, dict) else (p.uuid, p.sex)


def _facts(r: dict[str, Any]) -> list[str]:
    out = []
    if r["wtp"] is not None:
        out.append(f"이 제품에 낼 수 있는 가격은 {r['wtp']:,}원까지라고 답했습니다.")
    for label in r["opinions"]:
        o = followup.BY_LABEL[label]
        out.append(f"이 제품의 {'기대' if o.good else '걱정'}: {o.fact}")
    return out


def assign(respondents: list[dict[str, Any]], people: Iterable[Any]) -> dict[str, dict[str, Any]]:
    groups: dict[str | None, list[str]] = {}
    for uuid, sex in sorted(map(_person, people)):
        groups.setdefault(sex, []).append(uuid)
    out: dict[str, dict[str, Any]] = {}
    for sex, members in groups.items():
        pool = [r for r in respondents if r["sex"] == sex and r["weight"] > 0] or [
            r for r in respondents if r["weight"] > 0]
        if not pool:
            continue
        pool = sorted(pool, key=lambda r: (r["wtp"] is None, r["wtp"] or 0, r["opinions"], r["intent"] or 0))
        step = sum(r["weight"] for r in pool) / len(members)
        index, edge = 0, pool[0]["weight"]
        for i, uuid in enumerate(sorted(members, key=_order)):
            while edge <= (i + 0.5) * step and index < len(pool) - 1:
                index += 1
                edge += pool[index]["weight"]
            r = pool[index]
            out[uuid] = {"lines": _facts(r), "wtp": r["wtp"], "opinions": r["opinions"], "intent": r["intent"]}
    return out


def build(upload_id: str, people: Iterable[Any]) -> None:
    """people은 method.Person이나 {uuid, sex}의 목록. 배정을 store/followup/<upload_id>/assignment.json에 둔다."""
    respondents = followup.read(upload_id, "respondents.json")
    if not respondents:
        raise ValueError("올린 조사 파일을 찾을 수 없어요. 다시 올려 주세요.")
    followup.write(upload_id, "assignment.json", assign(respondents, people))


def assigned(upload_id: str) -> dict[str, dict[str, Any]]:
    """가상 소비자(uuid)마다의 배정. 아직 나눠 주지 않았으면 빈 것."""
    path = followup.folder(upload_id) / "assignment.json"
    try:
        stamp = path.stat()
    except FileNotFoundError:
        return {}
    key = (str(path), stamp.st_ino, stamp.st_mtime_ns)
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = followup.read(upload_id, "assignment.json") or {}
    return _CACHE[key]


def lines(upload_id: str, uuid: str) -> list[str]:
    """컨셉을 올린 매대의 글에 끼울 줄. 배정이 없는 조사면 ValueError(조사를 더하지 않은 채 돌지 않게)."""
    table = assigned(upload_id)
    if not table:
        raise ValueError("가상 소비자에게 아직 조사 답을 나눠 주지 않았어요.")
    return list(table.get(uuid, {}).get("lines", []))
