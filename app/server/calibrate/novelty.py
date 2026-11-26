"""가상 손님의 '새로운 것 맛보기'(N08) 세기를 제공 조사의 신제품 시도 성향 분포에 맞춘다.

패널의 N08(0~3)은 조사(정제 뒤 276명)의 신제품 시도 성향(1~5)보다 훨씬 세다(20대 3점 34% 대 5점 14%).
연령대 안에서 지금의 N08이 높은 사람부터(같으면 md5(uuid) 순) 목표 분포의 높은 단계를 채운다.
무작위를 쓰지 않으므로 같은 입력이면 늘 같은 결과다. data/ours/persona_needs.csv는 고치지 않는다.

- off: 그대로.
- survey: 조사 5점 → 3, 4점 → 2, 3점 → 1, 1~2점 → 0.
- strict: 5점 → 2, 4점 → 1, 3점 이하 → 0. 살 의향과 실제 구매의 간극을 반영한 더 낮은 안.
"""

from __future__ import annotations

import hashlib
import json
import os

NEED = "N08"
MODES = ("off", "survey", "strict")
DEFAULT = "strict"  # docs/reliability.md "새로움 욕구의 세기를 조사에 맞춘 보정"의 측정으로 정했다

# data/onsite/survey_respondents.csv(정제 뒤 276명)의 novelty를 weight로 가중한 연령대별 분포(집계만 적는다).
# 열쇠는 조사 점수 묶음: "5", "4", "3", "1-2".
TARGET = {
    "19-29": {"5": 0.1375, "4": 0.4634, "3": 0.2976, "1-2": 0.1015},
    "30-39": {"5": 0.1157, "4": 0.3683, "3": 0.3250, "1-2": 0.1909},
    "40-49": {"5": 0.0482, "4": 0.3623, "3": 0.4790, "1-2": 0.1105},
    "50-59": {"5": 0.0979, "4": 0.1908, "3": 0.3594, "1-2": 0.3519},
}
# 조사에 60대 이상이 없으므로 60-69와 70+는 50~59세의 값을 쓴다.
BAND_ALIAS = {"60-69": "50-59", "70+": "50-59"}

MAPPING = {
    "survey": {"5": 3, "4": 2, "3": 1, "1-2": 0},
    "strict": {"5": 2, "4": 1, "3": 0, "1-2": 0},
}


def mode() -> str:
    value = os.getenv("AX_NOVELTY", DEFAULT).strip() or DEFAULT
    if value not in MODES:
        raise ValueError(f"AX_NOVELTY는 {', '.join(MODES)} 중 하나여야 합니다.")
    return value


def signature(mode_name: str) -> str:
    """상수와 대응의 해시. off면 빈 문자열."""
    if mode_name == "off":
        return ""
    body = json.dumps({"need": NEED, "target": TARGET, "alias": BAND_ALIAS, "mapping": MAPPING[mode_name],
                       "mode": mode_name, "v": 1}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def levels(band: str, mode_name: str) -> dict[int, float]:
    """연령대의 목표 분포를 N08 단계(0~3)의 비율로 바꾼다."""
    target = TARGET[BAND_ALIAS.get(band, band)]
    out: dict[int, float] = {}
    for group, share in target.items():
        level = MAPPING[mode_name][group]
        out[level] = out.get(level, 0.0) + share
    return out


def quotas(n: int, shares: dict[int, float]) -> dict[int, int]:
    """n명을 비율대로 나눈다(최대 나머지 방식, 같으면 높은 단계 먼저)."""
    total = sum(shares.values())
    raw = {k: n * v / total for k, v in shares.items()}
    out = {k: int(v) for k, v in raw.items()}
    rest = n - sum(out.values())
    for k in sorted(raw, key=lambda k: (-(raw[k] - out[k]), -k))[:rest]:
        out[k] += 1
    return out


def _md5(uuid: str) -> str:
    return hashlib.md5(uuid.encode()).hexdigest()


def apply(strength: dict[str, dict], mode_name: str) -> dict[str, dict]:
    """N08만 바꾼 새 dict. 원본 dict와 행은 건드리지 않는다. 행에는 '연령대'가 있어야 한다."""
    if mode_name not in MODES:
        raise ValueError(f"알 수 없는 보정 방식: {mode_name}")
    if mode_name == "off":
        return strength
    bands: dict[str, list[str]] = {}
    for uid, row in strength.items():
        if row.get(NEED) in ("", None):
            continue
        bands.setdefault(row["연령대"], []).append(uid)
    out = dict(strength)
    for band, uids in bands.items():
        uids.sort(key=lambda u: (-int(strength[u][NEED]), _md5(u)))
        q = quotas(len(uids), levels(band, mode_name))
        i = 0
        for level in sorted(q, reverse=True):
            for uid in uids[i:i + q[level]]:
                out[uid] = {**strength[uid], NEED: str(level)}
            i += q[level]
    return out


_cache: dict[tuple[int, str], tuple[dict, dict]] = {}


def calibrated(strength: dict[str, dict], mode_name: str | None = None) -> dict[str, dict]:
    """같은 원본 dict와 방식이면 한 번만 계산한다."""
    mode_name = mode() if mode_name is None else mode_name
    key = (id(strength), mode_name)
    hit = _cache.get(key)
    if hit is None or hit[0] is not strength:
        hit = (strength, apply(strength, mode_name))
        _cache[key] = hit
    return hit[1]
