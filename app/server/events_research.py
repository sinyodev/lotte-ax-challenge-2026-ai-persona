"""1부에서 확인한 트렌드의 작업대 카드."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TrendMonth(BaseModel):
    month: str
    search_index: float | None = None
    sns_mentions: float | None = None
    sns_organic: float | None = None
    ad_share: float | None = None


class RelatedSearch(BaseModel):
    related: str
    share: float | None = None


class Verdict(BaseModel):
    keyword: str
    stage: list[str]
    reasons: list[str]
    series: list[TrendMonth]
    related: list[RelatedSearch]
    ad_share_peak: float | None = None
    product_search_share: float | None = None


class TrendItem(BaseModel):
    keyword: str
    title: str
    source: Literal["internal", "web"]
    publisher: str
    url: str | None = None
    date: str | None = None
    verdict: Verdict | None = None


class TrendPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[TrendItem]
