"""기획 노트: 대화마다의 상태 (지시서 09의 1절, docs/chilseong-part1.md 0절).

브리프는 채워야 하는 양식이 아니라 대화에서 나온 것을 받아 적은 요약이다. 칸은 비어 있어도 된다.
칸마다 누가 정했는지(planner 기획자, chilseong 칠성이)를 적어 둔다. 기획자의 생각(방향)은 쌓아 두고 잊지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from tools import consumer
from tools.consumer import Group

By = Literal["planner", "chilseong"]
SLOTS = ("product", "target", "occasion", "need")
SLOT_NAMES = {"product": "제품", "target": "타깃", "occasion": "음용 상황", "need": "바라는 것(니즈)"}
IDEA_FIELDS = ("name", "flavor", "pack", "features", "line")


@dataclass
class Slot:
    value: str | None = None
    by: By | None = None


@dataclass
class Note:
    product: Slot = field(default_factory=Slot)
    target: Slot = field(default_factory=Slot)
    occasion: Slot = field(default_factory=Slot)
    need: Slot = field(default_factory=Slot)
    thoughts: list[str] = field(default_factory=list)
    ideas: list[dict[str, Any]] = field(default_factory=list)  # 보드 위의 아이디어(순서대로)
    concepts: list[dict[str, Any]] = field(default_factory=list)
    stage: Literal["idea", "concept"] = "idea"
    confirmed: bool = False
    evidence: list[dict[str, Any]] = field(default_factory=list)  # 근거 카드의 항목(찾아본 것)

    # 찾아볼 때 쓰는 값(노트의 칸에서 코드가 정한다)
    kind: str | None = None  # 소비자 조사의 종류
    shelf_kind: str | None = None  # 매대의 종류
    shelf: str = "음료"  # 음료 또는 주류
    same_kind: bool = True  # 제품이 조사의 종류와 같은가
    group: Group | None = None  # 타깃을 조사의 집단으로 읽은 것
    occasion_code: str | None = None

    # 대화의 흐름
    n: int = 0  # 고유 id를 만드는 셈
    idea_seq: int = 0  # 아이디어 id(a, b, c, …)
    web_done: set[str] = field(default_factory=set)  # 요즘 소식을 찾아본 제품
    said: set[str] = field(default_factory=set)  # 말에서 이미 쓴 찾아본 것의 열쇠
    last_say: str = ""
    said_before: list[str] = field(default_factory=list)  # 칠성이가 앞에서 한 말(되풀이하지 않게 말하기에 넘긴다. 최근 셋)
    last_offer: Any = None  # 칠성이가 방금 내민 묶음(choices 또는 actions)
    retry: Any = None  # 하다가 막힌 일(다시 하기)
    recs: list[Any] = field(default_factory=list)  # 추천받기에서 내민 것

    # 2부 매대 테스트(지시서 15)
    runs: dict[str, str] = field(default_factory=dict)  # 컨셉 id → 매대 테스트 id(마지막으로 올린 것)
    last_run: str | None = None  # 마지막으로 시작한 매대 테스트
    shelf_pending: str | None = None  # 확인을 기다리는 컨셉 id(누구에게 물을지 말하고 "테스트 시작하기"를 기다린다)

    # 지시서 17: 한 손님에게 묻기, 개선안
    # 부른 손님 {run_id, visitor, who, asked: [물음 칩 id], qa: [[물음, 답], …]}. 부른 동안 기획자의 말은 그 손님에게 간다
    interview_plan: dict[str, Any] | None = None  # 대화에서 정하는 질문·방식과 확정 대상
    interview: dict[str, Any] | None = None
    # 개선안 표 {base_run, concept_id, items: [{id, change, reason, values, run_id?}]}. 값(values)은 테스트에 넘기는 change
    improve: dict[str, Any] | None = None
    # 지시서 18의 C: 테스트마다 이미 인터뷰한 손님(테스트 id → 방문 id, 부른 차례대로)
    interviewed: dict[str, list[str]] = field(default_factory=dict)
    # 후속 개선(약속 v1.20): 마지막으로 올린 조사 {upload_id, step}. 집계와 배정은 store/followup에 있다
    followup: dict[str, Any] | None = None

    def remember_say(self, text: str) -> None:
        self.last_say = text
        self.said_before = [*self.said_before, text][-3:]

    def next_id(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}-{self.n}"

    def new_idea_id(self) -> str:
        i = self.idea_seq
        self.idea_seq += 1
        letters = "abcdefghijklmnopqrstuvwxyz"
        return letters[i] if i < 26 else f"i{i}"

    def slot(self, key: str) -> Slot:
        return getattr(self, key)

    def idea(self, idea_id: str) -> dict[str, Any] | None:
        return next((i for i in self.ideas if i["id"] == idea_id), None)

    def concept(self, concept_id: str) -> dict[str, Any] | None:
        return next((c for c in self.concepts if c["id"] == concept_id), None)

    @property
    def kind_name(self) -> str | None:
        return consumer.kind_name(self.kind) if self.kind else None


# ---------- 모델에게 주는 노트의 요약(응답자 단위의 값은 없다. 노트의 글과 찾아본 것의 집계만) ----------


def summary(note: Note, with_board: bool = True) -> str:
    lines = ["기획 노트"]
    for key in SLOTS:
        s = note.slot(key)
        who = {"planner": "기획자가 정함", "chilseong": "칠성이가 정함"}.get(s.by or "", "")
        lines.append(f"- {SLOT_NAMES[key]}: {s.value or '(비어 있음)'}" + (f" [{who}]" if who else ""))
    if note.thoughts:
        lines.append("- 기획자의 생각(방향. 잊지 말고 반영한다): " + " / ".join(note.thoughts))
    lines.append(f"- 단계: {'컨셉 보드' if note.stage == 'concept' else '아이디어 회의'}"
                 + (" (확정함)" if note.confirmed else ""))
    if with_board:
        lines.append(board(note))
        if note.concepts:
            lines.append(concept_board(note))
    return "\n".join(lines)


ORDINALS = ["첫 번째", "두 번째", "세 번째", "네 번째", "다섯 번째", "여섯 번째", "일곱 번째", "여덟 번째"]


def _ord(i: int) -> str:
    return ORDINALS[i] if i < len(ORDINALS) else f"{i + 1}번째"


def board(note: Note) -> str:
    if not note.ideas:
        return "아이디어 보드: (아직 없음)"
    lines = ["아이디어 보드(위에서부터 차례)"]
    for i, it in enumerate(note.ideas):
        tags = []
        if it.get("by") == "planner":
            tags.append("기획자가 올림")
        if it.get("kept"):
            tags.append("남기기로 함")
        tag = f" [{', '.join(tags)}]" if tags else ""
        lines.append(f"- id {it['id']} ({_ord(i)}): {it['name']} / 맛 {it['flavor']} / {it['pack']} / "
                     f"특징 {', '.join(it['features'])} / {it['line']}{tag}")
    return "\n".join(lines)


def concept_board(note: Note) -> str:
    lines = ["컨셉 보드(위에서부터 차례)"]
    for i, c in enumerate(note.concepts):
        lines.append(f"- id {c['id']} ({_ord(i)} 컨셉): {c['name']} / {c['headline']} / {c.get('pack') or c.get('volume', '')} / {c.get('price', '')}")
    return "\n".join(lines)
