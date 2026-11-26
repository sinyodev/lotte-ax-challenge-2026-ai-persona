"""매대 테스트를 담는 파일 (지시서 15의 1절). 저장소에 올리지 않는다(맨 위 .gitignore의 app/server/store/).

store/runs/<id>.json     테스트의 머리: 무엇을 누구에게 몇 명 물었는지, 상태. 상태가 바뀔 때만 통째로 바꿔치기해 쓴다.
store/runs/<id>.jsonl    답이 올 때마다 한 줄씩 덧붙인다(통째로 다시 쓰지 않는다. 끊겨도 앞의 줄은 남는다).
store/runs/<id>.usage.jsonl  실행별 모델 호출과 경과 시간 기록.
store/baselines/<판>-<모델>.jsonl  컨셉이 없는 매대의 답. (매대 자료의 판, 모델, 손님, 상황)이 같으면 다시 쓴다.

파일에 사용자의 이름이나 컴퓨터의 경로를 넣지 않는다. 손님은 합성 자료의 uuid로만 적는다(서술은 적지 않는다).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

STORE = Path(__file__).resolve().parents[1] / "store"
RUNS_DIR = STORE / "runs"
BASE_DIR = STORE / "baselines"
ID_RE = re.compile(r"^run-[0-9a-f]{12}$")


def valid_id(run_id: Any) -> bool:
    return isinstance(run_id, str) and bool(ID_RE.match(run_id))


def _meta_path(run_id: str) -> Path:
    if not valid_id(run_id):
        raise ValueError("테스트 id가 맞지 않아요")
    return RUNS_DIR / f"{run_id}.json"


def _answers_path(run_id: str) -> Path:
    return _meta_path(run_id).with_suffix(".jsonl")


def _usage_path(run_id: str) -> Path:
    return _meta_path(run_id).with_suffix(".usage.jsonl")


def save_meta(meta: dict[str, Any]) -> None:
    """임시 파일에 쓰고 바꿔치기한다."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{meta['id']}-", suffix=".tmp", dir=RUNS_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _meta_path(meta["id"]))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_meta(run_id: str) -> dict[str, Any] | None:
    try:
        return json.loads(_meta_path(run_id).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def all_meta() -> list[dict[str, Any]]:
    out = []
    if RUNS_DIR.exists():
        for p in sorted(RUNS_DIR.glob("run-*.json")):
            m = load_meta(p.stem)
            if m:
                out.append(m)
    return out


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
    with path.open("a+b") as f:
        if f.tell():
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                encoded = b"\n" + encoded
        f.write(encoded)
        f.flush()
        os.fsync(f.fileno())


def _read_lines(path: Path) -> list[dict[str, Any]]:
    """끝줄이 쓰다 끊겼으면 그 줄만 버린다."""
    out = []
    try:
        text = path.read_bytes()
    except FileNotFoundError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def append_answer(run_id: str, row: dict[str, Any]) -> None:
    _append(_answers_path(run_id), row)


def answers(run_id: str) -> list[dict[str, Any]]:
    return _read_lines(_answers_path(run_id))


def append_usage(run_id: str, row: dict[str, Any]) -> None:
    _append(_usage_path(run_id), row)


def usage_entries(run_id: str) -> list[dict[str, Any]]:
    return _read_lines(_usage_path(run_id))


def delete(run_id: str) -> None:
    for p in (_meta_path(run_id), _answers_path(run_id), _usage_path(run_id)):
        p.unlink(missing_ok=True)


# ---------- 컨셉이 없는 매대의 답 ----------


def _base_path(shelf_v: str, model: str) -> Path:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", model)
    return BASE_DIR / f"{shelf_v}-{safe}.jsonl"


def baselines(shelf_v: str, model: str) -> dict[tuple[str, str], dict[str, Any]]:
    """(손님, 상황) → 답. 같은 열쇠가 여럿이면 처음 것."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for r in _read_lines(_base_path(shelf_v, model)):
        key = (r.get("uuid", ""), r.get("occasion", ""))
        out.setdefault(key, r)
    return out


def append_baseline(shelf_v: str, model: str, row: dict[str, Any]) -> None:
    _append(_base_path(shelf_v, model), row)
