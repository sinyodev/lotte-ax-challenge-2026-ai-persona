"""칠성이의 이벤트 (약속 app/contract/README.md 2절, v1.7).

서버 안에서는 이 형식만 다룬다. 내보내는 형식(AI SDK 등)은 export_aisdk.py만 안다.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, TypeAdapter, model_validator
from events_shelf import ExplorePayload
from events_research import TrendPayload

StageId = Literal["idea", "concept", "shelf", "result", "improve", "report", "followup"]
CardKind = Literal["brief", "evidence", "ideas", "concepts", "shelf-run", "result", "improve", "report", "explore",
                   "trend", "history", "group", "diagnosis", "followup"]

# 카드 종류마다 놓이는 단계(약속 2절의 표)
Origin = Literal["record", "sales", "shelf", "web", "suggestion", "internal"]

CARD_STAGE: dict[str, str] = {
    "brief": "idea",
    "evidence": "idea",
    "ideas": "idea",
    "concepts": "concept",
    "shelf-run": "shelf",
    "result": "result",
    "improve": "improve",
    "report": "report",
    "explore": "shelf",
    "trend": "idea",
    "history": "idea",
    "group": "result",
    "diagnosis": "concept",
    "followup": "followup",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- 카드의 payload ----------


class BriefField(_Strict):
    key: Literal["product", "channel", "target", "occasion", "need"]
    label: str
    value: str | None
    note: str | None = None
    state: Literal["set", "asking", "empty"]


class BriefPayload(_Strict):
    fields: list[BriefField]
    thoughts: list[str] | None = None  # v1.3: 기획자가 넣은 방향


class EvidenceItem(_Strict):
    id: str
    origin: Origin
    text: str
    source: str
    url: str | None = None
    date: str | None = None
    note: str | None = None


class EvidencePayload(_Strict):
    items: list[EvidenceItem]


IdeaField = Literal["name", "flavor", "pack", "features", "line"]


class VariantRow(_Strict):
    """지시서 33: 규격 하나. 값이 있는 칸만 온다. price는 권장 소비자가, factory_price는 출고가."""
    label: str
    volume_ml: int | None = None
    price: int | None = None
    factory_price: int | None = None
    shelf_life_months: int | None = None
    shelf_life_days: int | None = None
    kcal: int | None = None


class IdeaItem(_Strict):
    id: str
    name: str
    flavor: str
    pack: str
    features: list[str]
    line: str
    diff: str
    by: Literal["chilseong", "planner"] | None = None  # v1.3
    kept: bool | None = None
    changed: list[IdeaField] | None = None
    variants: list[VariantRow] | None = None  # 지시서 33(없어도 되는 칸)
    shelf_variant: int | None = None  # 매대에 올릴 규격의 차례
    estimated: bool | None = None  # 유통기한·열량이 칠성이가 어림한 값인가
    launch: str | None = None
    season: str | None = None
    channels: list[str] | None = None
    storage: str | None = None


class IdeasPayload(_Strict):
    basis: str
    items: list[IdeaItem]


SpecKey = Literal["type", "flavor", "pack", "sugar_caffeine", "carbonation", "target", "occasion", "channel",
                  "price", "rivals", "own", "pod", "storage"]


class SpecRow(_Strict):
    key: SpecKey
    label: str
    value: str = Field(min_length=1)  # 값이 없는 줄은 보내지 않는다


class ConceptItem(_Strict):
    """v1.4: 위쪽 예시 시안(headline, name, benefit, points, price, pack)과 아래쪽 제품 특징(spec)."""
    id: str
    name: str
    headline: str
    benefit: str
    points: list[str]
    price: str
    pack: str
    spec: list[SpecRow]
    insight: str | None = None  # 11-25: 소비자 인식 한 문장(없어도 되는 칸. 옛 컨셉에는 없다)
    confirmed: bool | None = None  # 11-25: 보드가 둘 이상일 때 확정한 보드
    changed: list[str] | None = None  # headline, name, benefit, points 또는 spec의 key
    variants: list[VariantRow] | None = None  # 지시서 33(없어도 되는 칸)
    shelf_variant: int | None = None  # 매대에 올릴 규격의 차례
    estimated: bool | None = None  # 유통기한·열량이 칠성이가 어림한 값인가
    launch: str | None = None
    season: str | None = None
    channels: list[str] | None = None
    storage: str | None = None


class ConceptsPayload(_Strict):
    items: list[ConceptItem]
    locked: bool | None = None  # 지시서 33 후속: 확정한 뒤에는 매대에 올릴 규격을 고를 수 없다


class ShelfConcept(_Strict):
    name: str
    pack: str
    container: str
    volume: int
    price: int


class ShelfRunPayload(_Strict):
    """v1.6(지시서 15): 숫자는 카드가 GET /api/runs/{run_id}에서 읽는다(대화에 박아 두면 낡는다)."""
    run_id: str
    concept: ShelfConcept
    who: str


class ResultPayload(_Strict):
    """v1.6(지시서 15): 결과의 숫자는 카드가 GET /api/runs/{run_id}에서 읽는다."""
    run_id: str


class ImprovementEvidence(_Strict):
    origin: Origin
    text: str
    quote_id: str | None = None
    session_id: str | None = None


class ImproveItem(_Strict):
    """v1.7(지시서 17): 고친 안 한 줄. run_id는 다시 물었을 때만. 숫자는 카드가 GET /api/runs/{id}에서 읽는다."""
    id: str
    change: str
    reason: str
    run_id: str | None = None
    # v1.11(지시서 19): 타일이 그리는 바꾼 것의 종류와 앞뒤 값. 옛 대화의 항목에는 없다
    kind: Literal["price", "name", "pack", "promo", "flavor", "form", "container", "appeal", "volume"] | None = None
    before: str | None = None
    after: str | None = None
    hypothesis: str | None = None
    evidence: list[ImprovementEvidence] | None = None
    paired: dict[str, Any] | None = None
    edit_values: dict[str, str | int] | None = None


class ImprovePayload(_Strict):
    base_run: str
    items: list[ImproveItem]
    price_curve: list[dict[str, Any]] | None = None
    adopted_item_id: str | None = None
    focus_id: str | None = None  # v1.20: 카드를 열면 먼저 보일 안(조사에서 나온 첫 안)


class ReportSection(_Strict):
    title: str
    body: str


class ReportPayload(_Strict):
    sections: list[ReportSection]


class HistoryItem(_Strict):
    id: str
    name: str = Field(max_length=120)
    status: Literal["출시", "단종", "폐기"]
    reason: str | None = Field(max_length=180)
    has_original: bool
    concept_excerpt: str | None = Field(default=None, max_length=160)
    conditions: list[str] = Field(default_factory=list, max_length=3)


class HistoryPayload(_Strict):
    items: list[HistoryItem] = Field(max_length=3)


class DiagnosisPayload(_Strict):
    concept_id: str
    concept_name: str
    sections: list[dict[str, Any]]
    fixes: list[dict[str, Any]]


class GroupDemoPayload(_Strict):
    demo: Literal[True]
    concept: str
    participants: list[dict[str, Any]]
    modes: dict[str, Any]
    diagnosis: dict[str, Any]
    comparison: dict[str, Any]
    quoteId: str | None = None
    view: Literal["room", "diagnosis", "compare"] = "room"
    mode: Literal["fgi", "fgd"] = "fgd"
    turn: int = 1


class GroupLivePayload(_Strict):
    demo: Literal[False]
    view: Literal["setup", "room", "conclusion", "individual"]
    individual: dict[str, Any] | None = None
    run_id: str
    concept: str
    questions: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    suggested: list[str]
    selected_question_id: str | None = None
    session: dict[str, Any] | None = None


class GroupPayload(RootModel[Annotated[GroupDemoPayload | GroupLivePayload, Field(discriminator="demo")]]):
    pass


class FollowupConcept(_Strict):
    id: str
    name: str
    price: int


class FollowupCount(_Strict):
    raw: int
    clean: int
    target: int


class FollowupRemoved(_Strict):
    label: str
    count: int


class FollowupDiff(_Strict):
    id: Literal["price", "worry", "hope"]
    text: str
    actual: float
    actual_n: int
    virtual: float | None
    virtual_n: int | None


class FollowupPoint(_Strict):
    price: int
    share: float
    money: int


class FollowupOpinion(_Strict):
    text: str
    n: int
    intent: int


class FollowupOpinions(_Strict):
    good: list[FollowupOpinion]
    bad: list[FollowupOpinion]


class FollowupTrack(_Strict):
    total: int
    original: int | None
    retest: int | None
    improved: int | None


class FollowupPayload(_Strict):
    """v1.20: 후속 개선. 조사 집계와 처음 테스트, 다시 테스트, 개선안의 선택 수."""
    upload_id: str
    step: Literal["diff", "applied", "retest", "ideas"]
    concept: FollowupConcept
    target: str
    n: FollowupCount
    removed: list[FollowupRemoved]
    diffs: list[FollowupDiff]
    note: str
    curve: list[FollowupPoint]
    best_price: int | None
    opinions: FollowupOpinions
    track: FollowupTrack
    base_run: str
    retest_run: str | None
    can_retest: bool
    fit: dict[str, Any] | None = None
    ideas: list[dict[str, Any]] = []
    saved: bool = False


PAYLOADS: dict[str, type[BaseModel]] = {
    "brief": BriefPayload,
    "evidence": EvidencePayload,
    "ideas": IdeasPayload,
    "concepts": ConceptsPayload,
    "shelf-run": ShelfRunPayload,
    "result": ResultPayload,
    "improve": ImprovePayload,
    "report": ReportPayload,
    "explore": ExplorePayload,
    "trend": TrendPayload,
    "history": HistoryPayload,
    "group": GroupPayload,
    "diagnosis": DiagnosisPayload,
    "followup": FollowupPayload,
}


# ---------- 이벤트 여덟 가지 ----------


class Speaker(_Strict):
    """v1.7(지시서 17): 칠성이가 아닌 화자. 지금은 테스트의 손님 한 명뿐이다. label은 "24세 여자, 대학생"."""
    kind: Literal["shopper"]
    label: str


class Say(_Strict):
    t: Literal["say"] = "say"
    text: str
    speaker: Speaker | None = None  # 없으면 칠성이


class Activity(_Strict):
    t: Literal["activity"] = "activity"
    id: str
    label: str
    status: Literal["running", "done"]


class Option(_Strict):
    id: str
    label: str
    note: str | None = None


class FreeChip(_Strict):
    label: str


class Choices(_Strict):
    t: Literal["choices"] = "choices"
    id: str
    kind: Literal["single", "multi"]
    options: list[Option]
    free: FreeChip | None = None
    on_card: str | None = None


class ActionItem(_Strict):
    id: str
    label: str
    note: str | None = None
    primary: bool | None = None


class Actions(_Strict):
    t: Literal["actions"] = "actions"
    id: str
    actions: list[ActionItem] = Field(min_length=1, max_length=3)


class ConfirmRow(_Strict):
    label: str
    value: str
    note: str | None = None


class ConfirmButton(_Strict):
    id: str
    label: str


class Confirm(_Strict):
    t: Literal["confirm"] = "confirm"
    id: str
    title: str
    desc: str | None = None
    rows: list[ConfirmRow]
    confirm: ConfirmButton
    cancel: ConfirmButton


class Summary(_Strict):
    t: Literal["summary"] = "summary"
    id: str
    title: str
    value: str
    note: str | None = None


class Stage(_Strict):
    t: Literal["stage"] = "stage"
    current: StageId


class Card(_Strict):
    t: Literal["card"] = "card"
    id: str
    stage: StageId
    kind: CardKind
    title: str
    status: Literal["loading", "ready", "error"]
    payload: Any
    origin: Origin | None = None

    @model_validator(mode="after")
    def _check_payload(self) -> "Card":
        # 저장된 인터뷰 카드는 result에 있다. 새 인터뷰는 개선안 테스트에서 진행한다.
        if CARD_STAGE[self.kind] != self.stage and not (self.kind == "group" and self.stage == "improve"):
            raise ValueError(f"카드 {self.kind}의 단계는 {CARD_STAGE[self.kind]}이어야 한다")
        # 준비 중이거나 실패한 카드는 payload를 비워 둘 수 있다
        if self.status == "ready":
            PAYLOADS[self.kind].model_validate(self.payload)
        return self


ChilseongEvent = Annotated[
    Union[Say, Activity, Choices, Actions, Confirm, Summary, Stage, Card],
    Field(discriminator="t"),
]
event_adapter: TypeAdapter[ChilseongEvent] = TypeAdapter(ChilseongEvent)

# 한 차례에 하나만 있는 것(답을 받는 것)
REPLY_KINDS = ("choices", "actions", "confirm")
