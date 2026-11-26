"""전 연령 탐색 테스트의 작업대 카드."""

from pydantic import BaseModel, ConfigDict, Field


class ExplorePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1)
