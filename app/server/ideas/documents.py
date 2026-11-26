"""업로드한 Office 문서를 임시 파일 없이 읽어 확인용 텍스트로 바꾼다."""

import base64
import binascii
import re
from collections.abc import Iterable, Iterator
from io import BytesIO
from pathlib import PurePath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from lxml.etree import XMLSyntaxError
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_BASE64_CHARS = 4 * ((MAX_FILE_BYTES + 2) // 3)
MAX_UNPACKED = 64 * 1024 * 1024
MAX_TEXT_CHARS = 100_000
MAX_SHEET_ROWS = 5_000
MAX_SHEET_COLUMNS = 256

OFFICE_PARTS = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml", ".pptx": "ppt/presentation.xml"}
SLIDE = re.compile(r"ppt/slides/slide(\d+)\.xml\Z")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
LOCAL_PATH = re.compile(r"(?i)(?:/[Uu]sers/|/home/|[a-z]:[\\/]users[\\/])[^\r\n\t\"<>]*")
AUTHOR = re.compile(r"(?m)((?:^|\t)\s*(?:작성자|업로더)\s*[:：]\s*)[^\r\n\t]+")


class DocumentError(ValueError):
    pass


def _docx(stream: BytesIO) -> Iterator[str]:
    for block in Document(stream).iter_inner_content():
        if isinstance(block, Table):
            for row in block.rows:
                yield "\t".join(cell.text for cell in row.cells)
        else:
            yield block.text


def _xlsx(stream: BytesIO) -> Iterator[str]:
    workbook = load_workbook(stream, read_only=True, data_only=True, keep_links=False)
    try:
        for sheet in workbook.worksheets:
            if (sheet.max_row or 0) > MAX_SHEET_ROWS or (sheet.max_column or 0) > MAX_SHEET_COLUMNS:
                raise DocumentError("시트의 읽을 범위가 너무 커요. 필요한 부분을 나눠 올려 주세요.")
            yield f"[{sheet.title}]"
            for row in sheet.iter_rows(values_only=True):
                if any(value is not None for value in row):
                    yield "\t".join(str(value) if value is not None else "" for value in row).rstrip("\t")
    finally:
        workbook.close()


def _pptx(archive: ZipFile) -> Iterator[str]:
    namespace = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    slides = sorted((int(match[1]), path) for path in archive.namelist() if (match := SLIDE.fullmatch(path)))
    for number, path in slides:
        yield f"[슬라이드 {number}]"
        root = ElementTree.fromstring(archive.read(path))
        for paragraph in root.findall(".//a:p", namespace):
            yield "".join(node.text or "" for node in paragraph.findall(".//a:t", namespace))


def _join(lines: Iterable[str]) -> str:
    parts, length = [], 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        length += len(line) + 1
        if length > MAX_TEXT_CHARS:
            raise DocumentError("읽을 글이 너무 많아요. 필요한 부분을 나눠 올려 주세요.")
        parts.append(line)
    return "\n".join(parts)


def extract(filename: str, content_base64: str) -> str:
    extension = PurePath(filename).suffix.casefold()
    if extension not in OFFICE_PARTS:
        raise DocumentError("Word(.docx), Excel(.xlsx), PowerPoint(.pptx) 파일을 올려 주세요.")
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DocumentError("올린 파일을 읽을 수 없어요. 다시 올려 주세요.") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise DocumentError("8MB 이하의 파일을 올려 주세요.")
    try:
        with ZipFile(BytesIO(raw)) as archive:
            if OFFICE_PARTS[extension] not in archive.namelist():
                raise DocumentError("파일 형식이 확장자와 맞지 않아요.")
            if sum(part.file_size for part in archive.infolist()) > MAX_UNPACKED:
                raise DocumentError("펼친 파일의 크기가 너무 커요. 필요한 부분을 나눠 올려 주세요.")
            if extension == ".pptx":
                lines = _pptx(archive)
            elif extension == ".docx":
                lines = _docx(BytesIO(raw))
            else:
                lines = _xlsx(BytesIO(raw))
            text = _join(lines)
    except DocumentError:
        raise
    except (BadZipFile, PackageNotFoundError, InvalidFileException, ElementTree.ParseError, XMLSyntaxError,
            KeyError, ValueError, OSError, RuntimeError, TypeError) as exc:
        raise DocumentError("문서에서 글을 읽을 수 없어요. 파일을 확인해 주세요.") from exc
    if not any(line for line in text.splitlines() if not (line.startswith("[") and line.endswith("]"))):
        raise DocumentError("문서에서 읽을 글을 찾지 못했어요.")
    text = EMAIL.sub("[이메일 생략]", text)
    text = LOCAL_PATH.sub("[경로 생략]", text)
    return AUTHOR.sub(r"\1[이름 생략]", text)
