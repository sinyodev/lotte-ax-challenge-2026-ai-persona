"""현장 자료를 생성한다. app/server에서 uv run python -m onsite.build."""

import fcntl
import json
import os
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp

from docx import Document
from pandas import DataFrame

from . import DATA_ROOT, directory
from .concepts import CONCEPTS
from .schema import CSV_COLUMNS, FILENAMES


def _source(root: Path, prefix: str, extension: str) -> Path:
    paths = sorted(root.glob(f"{prefix}_*.{extension}"))
    if len(paths) != 1:
        raise ValueError(f"{prefix} {extension} 원본이 한 개 필요합니다. 발견한 파일 {len(paths)}개.")
    return paths[0]


def _write_tables(stage: Path, tables: dict) -> None:
    if tables.keys() != FILENAMES.keys():
        raise ValueError(f"약속과 다른 표 목록: {sorted(tables.keys() ^ FILENAMES.keys())}")
    for name, filename in FILENAMES.items():
        value = tables[name]
        if name in CSV_COLUMNS:
            columns = list(CSV_COLUMNS[name])
            if not isinstance(value, DataFrame) or set(value.columns) != set(columns) or value.columns.has_duplicates:
                raise ValueError(f"{name}의 열이 약속 문서와 다릅니다.")
            value.to_csv(stage / filename, columns=columns, index=False, lineterminator="\n")
        else:
            with (stage / filename).open("w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.write("\n")


def publish(destination: Path, tables: dict) -> None:
    """다 만든 판만 한 번에 공개한다. 다른 묶음은 늘 같은 CSV·JSON 경로를 읽는다."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    snapshots = destination / ".snapshots"
    snapshots.mkdir(exist_ok=True)
    with (destination / ".build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = destination / ".current"
        previous = current.resolve() if current.is_symlink() else None
        stage = Path(mkdtemp(prefix="build-", dir=snapshots))
        try:
            _write_tables(stage, tables)
            for filename in FILENAMES.values():
                public = destination / filename
                target = Path(".current") / filename
                if public.is_symlink() and public.readlink() == target:
                    continue
                alias = stage / ".public-link"
                alias.symlink_to(target)
                os.replace(alias, public)
            pointer = stage / ".current-link"
            pointer.symlink_to(stage.relative_to(destination))
            os.replace(pointer, current)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        # 한 판 전까지 보존해 교체 직전에 읽던 프로세스도 끝까지 읽을 수 있게 한다.
        for old in snapshots.glob("build-*"):
            if old.resolve() not in (previous, stage.resolve()):
                shutil.rmtree(old)


def build(raw: Path, destination: Path) -> None:
    guide = _source(raw, "3-0", "docx")
    sales = _source(raw, "3-1", "xlsx")
    survey = _source(raw, "3-2", "xlsx")
    journeys = _source(raw, "3-3", "xlsx")
    fgi = _source(raw, "3-4", "docx")
    if not any(p.text.strip() for p in Document(guide).paragraphs):
        raise ValueError("데이터 안내서의 내용을 읽을 수 없습니다.")

    from .journeys import build_journeys
    from .sales import build_sales
    from .survey import build_survey

    tables = {"concepts": CONCEPTS}
    report = []
    for result, rules in (build_sales(sales), build_survey(survey), build_journeys(journeys, fgi)):
        tables.update(result)
        report.extend(rules)
    tables["cleaning_report"] = report
    publish(destination, tables)


if __name__ == "__main__":
    try:
        build(DATA_ROOT / "raw" / "onsite", directory())
    except (OSError, ValueError) as exc:
        sys.exit(f"현장 자료 생성 실패: {exc}")
    print(f"현장 자료 {len(FILENAMES)}개를 만들었습니다.")
