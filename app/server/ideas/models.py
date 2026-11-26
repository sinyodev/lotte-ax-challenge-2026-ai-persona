"""아이디어 보드의 공개 행과 사람이 바꿀 수 있는 칸."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal, get_args

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, field_validator

Status = Literal["기획 중", "가상 테스트 중", "가상 테스트 완료", "소비자 조사 진행", "정성 조사 중", "정량 조사 중",
                 "출시", "보류", "폐기", "단종"]
STATUSES = get_args(Status)
LAUNCHED_STATUSES = ("출시", "단종")


def launch_date(value: str) -> str:
    try:
        if date.fromisoformat(value).isoformat() == value:
            return value
    except ValueError:
        pass
    raise ValueError("출시일을 YYYY-MM-DD 형식으로 적어 주세요.")


LaunchDate = Annotated[str, AfterValidator(launch_date)]


class BoardModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CheckPatch(BoardModel):
    virtual_test: StrictBool | None = None
    qual: StrictBool | None = None
    quant: StrictBool | None = None
    launched: StrictBool | None = None


class Checks(BoardModel):
    virtual_test: StrictBool = False
    qual: StrictBool = False
    quant: StrictBool = False
    launched: StrictBool = False


class LastTest(BoardModel):
    selection_rate: float | None = Field(default=None, ge=0, le=1)
    own_share: float | None = Field(default=None, ge=0, le=1)
    virtual_sales: str | None = None


class IdeaRow(BoardModel):
    id: str = ""
    name: str = Field(min_length=1, max_length=300)
    brand: str | None = None
    category: str | None = None
    pack: str | None = None
    price: str | None = None
    owner: str | None = None
    concept: str | None = None
    launched_on: LaunchDate | None = None
    last_work: str | None = None
    work_date: str | None = None
    status: Status = "기획 중"
    checks: Checks = Field(default_factory=Checks)
    last_test: LastTest | None = None
    verdict: str | None = None
    reason: str | None = None
    trend: str | None = None
    started: str | None = None
    updated: str | None = None
    source: Literal["chat", "assets", "import", "manual", "concept"] = "import"
    chat_id: str | None = None
    attachment_count: int = 0

    @property
    def was_launched(self) -> bool:
        return bool(self.launched_on or self.checks.launched or self.status in LAUNCHED_STATUSES)

    @field_validator("brand", "category", "pack", "owner", "verdict", "reason", "trend", "started", "updated", "concept",
                     "last_work", "work_date")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("price")
    @classmethod
    def price_with_unit(cls, value: str | None) -> str | None:
        if value and not (any(c.isalpha() for c in value) or any(c in value for c in "₩$€¥£")):
            raise ValueError("가격에 단위를 적어 주세요.")
        return value or None


class IdeaPatch(BoardModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    status: Status | None = None
    reason: str | None = None
    verdict: str | None = None
    owner: str | None = None
    concept: str | None = None
    launched_on: LaunchDate | None = None
    checks: CheckPatch | None = None

    def changes(self) -> dict:
        out = self.model_dump(exclude_unset=True)
        if self.status is None:
            out.pop("status", None)
        if self.name is None:
            out.pop("name", None)
        for key in ("reason", "verdict", "owner", "concept"):
            if out.get(key) == "":
                out[key] = None
        checks = self.checks.model_dump(exclude_none=True) if self.checks else {}
        if checks:
            out["checks"] = checks
        else:
            out.pop("checks", None)
        return out


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def date_key(value: str | None) -> datetime:
    """저장된 날짜 표시를 보존하면서 날짜 순서만 UTC로 비교한다."""
    for text in (value or "", f"{value}-01", f"{value}-01-01"):
        try:
            date = datetime.fromisoformat(text)
            return date.astimezone(UTC) if date.tzinfo else date.replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=UTC)
