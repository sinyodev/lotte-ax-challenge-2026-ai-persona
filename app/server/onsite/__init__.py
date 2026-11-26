"""현장 자료 읽기. AX_ONSITE_DIR로 결과 폴더를 지정할 수 있다."""

import csv
import json
import os
from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .schema import BOOLEAN, CSV_COLUMNS, DECIMAL, FILENAMES, INTEGER, JSON_NAMES

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"


class NoData(FileNotFoundError):
    """현장 자료가 아직 만들어지지 않았다."""


def directory() -> Path:
    return Path(os.environ.get("AX_ONSITE_DIR", DATA_ROOT / "onsite"))


def available() -> bool:
    root = directory()
    return all((root / filename).is_file() for filename in FILENAMES.values())


def _value(column: str, value: str):
    if value == "":
        return None
    if column in BOOLEAN:
        return {"true": True, "false": False}[value.lower()]
    if column in INTEGER:
        number = Decimal(value)
        if number != number.to_integral_value():
            raise ValueError(f"{column}: 정수가 필요합니다")
        return int(number)
    if column in DECIMAL:
        return float(value)
    return value


@lru_cache(maxsize=48)
def _read(path: Path, version: tuple, name: str):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        if name in JSON_NAMES:
            return json.load(stream)
        return [{key: _value(key, value) for key, value in row.items()}
                for row in csv.DictReader(stream)]


def _load(name: str, names):
    if name not in names:
        raise KeyError(name)
    path = directory() / FILENAMES[name]
    try:
        info = path.stat()
        data = _read(path, (info.st_ino, info.st_mtime_ns, info.st_size), name)
    except FileNotFoundError as exc:
        raise NoData("현장 자료를 먼저 만들어 주세요.") from exc
    return deepcopy(data)


def load(name: str) -> list[dict]:
    return _load(name, CSV_COLUMNS)


def load_json(name: str):
    return _load(name, JSON_NAMES)


def frame(name: str) -> pd.DataFrame:
    return pd.DataFrame(load(name), columns=CSV_COLUMNS[name])
