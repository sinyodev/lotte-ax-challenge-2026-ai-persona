"""소비자 기록을 읽는다. 모델을 부르지 않는다.

자료(모두 집계 파일이다. 응답자 단위 자료는 읽지 않는다)
- data/clean/knhanes_2024_beverage_occasions.csv  2024 국민건강영양조사 식품섭취조사: 종류 × 집단 × 축의 가중 비율과 마신 자리 수
- data/ours/occasions.csv, occasion_weights.csv, occasion_drink_mix.csv, occasion_needs.csv, needs.csv  우리 상황 12개와 니즈
- data/clean/fis_pos_2024_cvs.csv, fis_pos_2025_cvs.csv  aT 식품산업통계정보 소매 POS의 편의점 매출
- data/clean/knhanes_2024_cofoods.csv, knhanes_2024_beverage_by_job.csv  함께 먹은 음식, 직업 구분 (scripts/knhanes_extra.py)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from tools.occasion_display import same as same_occasion, show as show_occasion

REPO = Path(__file__).resolve().parents[3]
CLEAN = REPO / "data" / "clean"
OURS = REPO / "data" / "ours"

RECORD_SOURCE = "2024 국민건강영양조사 식품섭취조사"
SALES_SOURCE = "aT 식품산업통계정보 소매 POS(마켓링크)"
SMALL_SAMPLE = 100
MIN_FOUND = 30  # 이보다 적은 건수에서 찾은 것은 돌려주지 않는다(지시서 09)

# ---------- 이름 표: 기록의 말 → 화면의 말 (한 곳에만 둔다) ----------

KIND_NAMES: dict[str, str] = {
    "커피(커피만)": "블랙 커피",
    "커피(당·프림 등 첨가)": "믹스 커피",
    "탄산음료": "탄산음료",
    "탄산음료(저칼로리)": "제로 탄산",
    "과일·채소음료": "과일·채소 주스",
    "차": "차",
    "기타 음료": "그 밖의 음료",
    "소주": "소주",
    "맥주": "맥주",
    "막걸리": "막걸리",
    "기타 주류": "그 밖의 술",
}
RECORD_KINDS = list(KIND_NAMES)
ALCOHOL_KINDS = {"소주", "맥주", "막걸리", "기타 주류"}

# 집단: 기록의 값 → (종류, 화면의 말)
AGE_NAMES = {"19-29": "20대", "30-39": "30대", "40-49": "40대", "50-59": "50대", "60-69": "60대", "70+": "70대 이상"}
SEX_NAMES = {"남자": "남자", "여자": "여자"}
_SEX_CODE = {"1.0": "남자", "2.0": "여자"}  # 국민건강영양조사의 성별 부호(1 남자, 2 여자)

# 편의점 매출의 품목 → (화면의 말, 가장 가까운 기록의 종류, 매대의 종류)
FIS_ITEMS: dict[str, tuple[str, str, str]] = {
    "탄산음료": ("탄산음료", "탄산음료", "탄산"),
    "과채음료": ("과채 음료", "과일·채소음료", "주스"),
    "액상차": ("차 음료", "차", "차"),
    "두유": ("두유", "기타 음료", "우유·단백"),
    "액상커피": ("커피 음료", "커피(커피만)", "커피"),
    "단백질음료": ("단백질 음료", "기타 음료", "우유·단백"),
    "우유": ("우유", "기타 음료", "우유·단백"),
    "발효유": ("발효유", "기타 음료", "우유·단백"),
    "탁주": ("막걸리", "막걸리", "막걸리"),
    "맥주": ("맥주", "맥주", "맥주"),
    "소주": ("소주", "소주", "소주"),
}

# 언제의 축에서 쓰는 값의 화면의 말
_WHEN_WORDS = {
    "시간대": {"1 아침(05~09시)": "아침에", "2 오전(09~11시)": "오전에", "3 점심(11~14시)": "점심에",
              "4 오후(14~17시)": "오후에", "5 저녁(17~21시)": "저녁에", "6 밤(21~05시)": "밤에"},
    "장소": {"가정": "집에서", "직장·학교": "직장이나 학교에서", "음식점": "음식점에서", "기타": "그 밖의 곳에서"},
    "동반": {"혼자": "혼자", "가족과": "가족과", "가족이 아닌 사람과": "가족이 아닌 사람과"},
    "음식 동반": {"음식과 함께": "음식과 함께", "음료만": "음료만"},
}


def shelf_of(kind: str | None) -> str:
    """기록의 종류가 속한 매대(음료 또는 주류)."""
    return "주류" if kind in ALCOHOL_KINDS else "음료"


def kind_name(kind: str) -> str:
    return KIND_NAMES.get(kind, kind)


def group_name(group: "Group") -> str:
    return group.label


@dataclass(frozen=True)
class Group:
    """타깃 집단. 기록은 연령대와 성별을 따로 집계해 두었다(둘을 겹친 값은 상황의 비중에만 있다)."""

    age: str | None = None  # "19-29" 등
    sex: str | None = None  # "남자", "여자"
    label: str = ""

    @property
    def id(self) -> str:
        return f"{self.sex or 'all'}|{self.age or 'all'}"

    @staticmethod
    def from_id(gid: str, label: str = "") -> "Group":
        sex, age = gid.split("|")
        g = Group(age=None if age == "all" else age, sex=None if sex == "all" else sex)
        return Group(age=g.age, sex=g.sex, label=label or default_label(g))


def default_label(g: Group) -> str:
    parts = [AGE_NAMES[g.age]] if g.age else []
    parts += [g.sex] if g.sex else []
    return " ".join(parts) or "전체"


# ---------- 자료 읽기 ----------


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _occasion_rows() -> list[dict[str, str]]:
    return _read(CLEAN / "knhanes_2024_beverage_occasions.csv")


@lru_cache(maxsize=1)
def _counts() -> dict[tuple[str, str], int]:
    """(종류, 집단) → 마신 자리 수. 집단은 '전체', 연령대 값, '남자'/'여자'."""
    out: dict[tuple[str, str], int] = {}
    for r in _occasion_rows():
        if r["축"] != "시간대":
            continue
        g = _SEX_CODE.get(r["집단"], r["집단"])
        out[(r["음료 종류"], g)] = int(r["집단의 마신 자리 수"])
    return out


def total(kind: str) -> int:
    """그 종류의 마신 자리 수(전체)."""
    return _counts().get((kind, "전체"), 0)


@dataclass
class WhoRow:
    group: Group
    ratio: float  # 전체 음료(또는 주류) 대비 몇 배
    n: int  # 그 집단이 이 종류를 마신 자리 수

    @property
    def small(self) -> bool:
        return self.n < SMALL_SAMPLE


def who(kind: str) -> list[WhoRow]:
    """연령대와 성별마다 "전체 음료 대비 몇 배 자주 마시나". 배수가 큰 순서.

    (그 종류의 마신 자리 가운데 그 집단의 몫) ÷ (모든 음료의 마신 자리 가운데 그 집단의 몫).
    음료와 주류는 따로 계산한다. 마신 자리 수는 가중하지 않은 건수다.
    """
    counts = _counts()
    same = [k for k in RECORD_KINDS if shelf_of(k) == shelf_of(kind)]
    total_all = sum(counts.get((k, "전체"), 0) for k in same)
    total_kind = counts[(kind, "전체")]
    rows: list[WhoRow] = []
    groups = [Group(age=a, label=AGE_NAMES[a]) for a in AGE_NAMES] + [Group(sex=s, label=s) for s in SEX_NAMES]
    for g in groups:
        key = g.age or g.sex
        n = counts.get((kind, key), 0)
        group_all = sum(counts.get((k, key), 0) for k in same)
        if not total_kind or not group_all:
            continue
        ratio = (n / total_kind) / (group_all / total_all)
        rows.append(WhoRow(group=g, ratio=ratio, n=n))
    rows.sort(key=lambda r: r.ratio, reverse=True)
    return rows


def top_groups(kind: str, k: int = 2) -> list[WhoRow]:
    """타깃 칩에 낼 집단: 연령대 가운데 배수가 큰 것 k개. 표본이 작으면 WhoRow.small로 알린다.
    (성별의 배수는 who()에 있지만 칩에는 내지 않는다. 사람으로 적히는 타깃은 연령대가 먼저다.)"""
    return [r for r in who(kind) if r.group.age][:k]


@dataclass
class WhenTop:
    axis: str
    value: str  # 화면의 말("저녁에")
    pct: float
    n: int
    raw: str = ""  # 기록의 값("5 저녁(17~21시)"). 입말로 바꿀 때 쓴다(tools/spoken.py)


def _record_group_key(group: Group) -> str:
    """기록(시간대·장소 등)은 연령대와 성별을 따로 집계했다. 둘 다 있으면 연령대를 쓴다."""
    if group.age:
        return group.age
    if group.sex:
        return {"남자": "1.0", "여자": "2.0"}[group.sex]
    return "전체"


def record_group_label(group: Group) -> str:
    """when()이 실제로 쓴 집단의 이름(연령대가 있으면 연령대, 없으면 성별)."""
    if group.age:
        return AGE_NAMES[group.age]
    return group.sex or "전체"


def when(kind: str, group: Group) -> dict[str, WhenTop]:
    """시간대, 장소, 동반, 음식 동반에서 가장 큰 값과 비율, 표본 수."""
    key = _record_group_key(group)
    out: dict[str, WhenTop] = {}
    for r in _occasion_rows():
        if r["음료 종류"] != kind or r["집단"] != key or r["축"] not in _WHEN_WORDS:
            continue
        word = _WHEN_WORDS[r["축"]].get(r["값"])
        if word is None:  # 뜻을 모르는 부호(장소 미상)
            continue
        pct = float(r["가중 비율(%)"])
        cur = out.get(r["축"])
        if cur is None or pct > cur.pct:
            out[r["축"]] = WhenTop(axis=r["축"], value=word, pct=pct, n=int(r["집단의 마신 자리 수"]), raw=r["값"])
    return out


def food_share(kind: str, group: Group) -> float | None:
    """음식과 함께 마신 비율(%)."""
    key = _record_group_key(group)
    for r in _occasion_rows():
        if r["음료 종류"] == kind and r["집단"] == key and r["축"] == "음식 동반" and r["값"] == "음식과 함께":
            return float(r["가중 비율(%)"])
    return None


# ---------- 상황과 니즈 ----------


@dataclass
class Occasion:
    code: str
    shelf: str
    name: str
    desc: str


@lru_cache(maxsize=1)
def all_occasions() -> dict[str, Occasion]:
    # 이름은 화면에 보이는 이름(tools.occasion_display). 가상 소비자에게 가는 글은 shelftest.method가 자료의 이름으로 따로 만든다.
    return {r["번호"]: Occasion(r["번호"], r["매대"], show_occasion(r["상황"]), r["풀어 쓴 설명"])
            for r in _read(OURS / "occasions.csv")}


def occasion_code_of(name: str | None) -> str | None:
    """상황 이름(옛 이름이든 새 이름이든) → 번호. 없으면 None."""
    if not name:
        return None
    return next((o.code for o in all_occasions().values() if same_occasion(o.name, name)), None)


@dataclass
class OccasionRank:
    occasion: Occasion
    score: float
    n: int  # 상황 비중을 구할 때 쓴 마신 자리 수


def occasions(kind: str | None, group: Group, shelf: str | None = None) -> list[OccasionRank]:
    """우리 상황의 순서. (집단의 상황 비중) × (상황 안의 종류 비율)에 비례.

    상황 비중은 성별 × 연령대로 있다. 한쪽만 정했으면 다른 쪽을 마신 자리 수로 가중 평균한다.
    종류가 기록에 없으면(kind=None) 상황 비중만으로 줄 세운다.
    """
    shelf = shelf or shelf_of(kind)
    weights: dict[str, list[tuple[float, int]]] = {}
    for r in _read(OURS / "occasion_weights.csv"):
        if r["매대"] != shelf:
            continue
        if group.age and r["연령대"] != group.age:
            continue
        if group.sex and r["성별"] != group.sex:
            continue
        weights.setdefault(r["번호"], []).append((float(r["비중(%)"]), int(r["근거로 쓴 마신 자리 수"])))
    mix: dict[str, float] = {}
    if kind is not None:
        for r in _read(OURS / "occasion_drink_mix.csv"):
            if r["매대"] == shelf and r["음료 종류"] == kind and r["번호"] in all_occasions():
                mix[r["번호"]] = float(r["비율(%)"])
    out: list[OccasionRank] = []
    for code, ws in weights.items():
        n = sum(w[1] for w in ws)
        w = sum(p * c for p, c in ws) / n if n else 0.0
        score = w * (mix.get(code, 0.0) if kind is not None else 1.0)
        out.append(OccasionRank(all_occasions()[code], score, n))
    out.sort(key=lambda o: o.score, reverse=True)
    return out


@dataclass
class NeedChange:
    code: str
    name: str
    desc: str
    change: float
    basis: str  # 자료, 가정, 정의


@lru_cache(maxsize=1)
def _needs() -> dict[str, dict[str, str]]:
    return {r["번호"]: r for r in _read(OURS / "needs.csv")}


def needs(occasion_code: str) -> list[NeedChange]:
    """그 상황에서 커지는 니즈. 근거가 "자료"인 것 먼저, 그 안에서 바뀌는 크기가 큰 순서."""
    out: list[NeedChange] = []
    for r in _read(OURS / "occasion_needs.csv"):
        if r["번호"] != occasion_code:
            continue
        change = float(r["바뀌는 크기(-2~+2)"])
        if change <= 0:
            continue
        info = _needs().get(r["욕구 번호"], {})
        out.append(NeedChange(r["욕구 번호"], r["욕구"], info.get("풀어 쓴 설명", ""), change, r["근거 종류"]))
    out.sort(key=lambda x: (x.basis != "자료", -x.change))
    return out


# ---------- 추천 ----------


@dataclass
class Start:
    """추천의 출발점 하나."""

    id: str
    product: str  # 화면의 말(칩의 이름)
    kind: str  # 기록의 종류
    shelf_kind: str | None  # 매대의 종류
    origin: str  # record | sales
    text: str  # 근거 카드의 문장
    source: str
    note: str | None = None
    extra: dict = field(default_factory=dict)


def sales_growth() -> list[tuple[str, float, int, int]]:
    """편의점 매출의 품목별 (품목, 늘어난 비율 %, 2024, 2025). 늘어난 비율이 큰 순서."""
    y24 = {r["품목"]: int(r["편의점 매출(백만원, 곱한 값)"]) for r in _read(CLEAN / "fis_pos_2024_cvs.csv")}
    y25 = {r["품목"]: int(r["편의점 매출(백만원, 곱한 값)"]) for r in _read(CLEAN / "fis_pos_2025_cvs.csv")}
    rows = [(k, 100 * (y25[k] - y24[k]) / y24[k], y24[k], y25[k]) for k in y24 if k in y25 and y24[k]]
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def recommend() -> list[Start]:
    """출발점 셋: 표본 100건 이상에서 배수가 가장 큰 (종류, 연령대) 둘(종류는 서로 다르게)과,
    편의점 매출이 가장 많이(비율로) 늘어난 품목 하나."""
    counts = _counts()
    pairs: list[tuple[float, str, str, int]] = []
    for kind in RECORD_KINDS:
        for row in who(kind):
            if row.group.age and row.n >= SMALL_SAMPLE:
                pairs.append((row.ratio, kind, row.group.age, row.n))
    pairs.sort(reverse=True)
    starts: list[Start] = []
    used: set[str] = set()
    from tools.shelf import closest_shelf_kind  # 순환을 피한다

    for ratio, kind, age, n in pairs:
        if kind in used:
            continue
        used.add(kind)
        name = kind_name(kind)
        than = "다른 술" if kind in ALCOHOL_KINDS else "다른 음료"
        starts.append(Start(
            id=f"rec-{len(starts) + 1}", product=name, kind=kind, shelf_kind=closest_shelf_kind(kind),
            origin="record", text=f"{name}{josa(name, '은/는')} {AGE_NAMES[age]}가 {than}보다 {ratio:.1f}배 자주 마셔요",
            source=f"{RECORD_SOURCE}, 음용 사례 {n:,}건", extra={"age": age, "n": n, "ratio": ratio, "total": counts[(kind, '전체')]},
        ))
        if len(starts) == 2:
            break
    item, pct, _, _ = sales_growth()[0]
    name, kind, shelf_kind = FIS_ITEMS[item]
    starts.append(Start(
        id=f"rec-{len(starts) + 1}", product=name, kind=kind, shelf_kind=shelf_kind, origin="sales",
        text=f"{name}의 편의점 매출이 2024년보다 2025년에 {pct:.0f}% 늘었어요", source=SALES_SOURCE,
        extra={"item": item, "pct": pct},
    ))
    return starts


# ---------- 언제(시간대 하나), 함께 먹은 것, 직업 ----------

TIME_BANDS = {"아침": "1 아침(05~09시)", "오전": "2 오전(09~11시)", "점심": "3 점심(11~14시)",
              "오후": "4 오후(14~17시)", "저녁": "5 저녁(17~21시)", "밤": "6 밤(21~05시)", "새벽": "6 밤(21~05시)"}


def band_in(text: str | None) -> str | None:
    """글에 든 시간대의 말(아침, 점심 …). 없으면 None."""
    for word in TIME_BANDS:
        if text and word in text:
            return word
    return None


def time_share(kind: str, group: Group, band: str) -> tuple[float, int] | None:
    """그 집단이 그 종류를 마신 자리 가운데 그 시간대의 가중 비율(%)과 마신 자리 수."""
    key = _record_group_key(group)
    raw = TIME_BANDS.get(band)
    for r in _occasion_rows():
        if r["음료 종류"] == kind and r["집단"] == key and r["축"] == "시간대" and r["값"] == raw:
            return float(r["가중 비율(%)"]), int(r["집단의 마신 자리 수"])
    return None


@dataclass
class CoFood:
    food: str
    side: bool  # 곁들임(양념, 김치 등)
    n: int  # 함께 먹은 끼니 수
    pct: float  # 그 음료를 마신 끼니 가운데 가중 비율


@dataclass
class WithFood:
    kind: str
    group: str  # 집단의 이름("20대", "전체")
    base: int  # 그 음료를 마신 끼니 수
    mains: list[CoFood]
    sides: list[CoFood]


@lru_cache(maxsize=1)
def _cofood_rows() -> list[dict[str, str]]:
    return _read(CLEAN / "knhanes_2024_cofoods.csv")


def with_food(kind: str, group: Group | None = None) -> WithFood | None:
    """그 음료를 마신 끼니에 함께 먹은 음식(주된 음식과 곁들임). 집단의 끼니가 적으면 전체로 본다.
    끼니가 MIN_FOUND 미만이거나 주된 음식이 없으면 None."""
    keys = [(AGE_NAMES[group.age], group.age)] if group and group.age else []
    keys.append(("전체", "전체"))
    for label, key in keys:
        rows = [r for r in _cofood_rows() if r["음료 종류"] == kind and r["집단"] == key]
        if not rows or int(rows[0]["그 음료를 마신 끼니 수"]) < MIN_FOUND:
            continue
        foods = [CoFood(r["음식"], r["구분"] == "곁들임", int(r["함께 먹은 끼니 수"]), float(r["가중 비율(%)"]))
                 for r in sorted(rows, key=lambda r: int(r["순위"]))]
        mains = [f for f in foods if not f.side]
        if mains:
            return WithFood(kind, label, int(rows[0]["그 음료를 마신 끼니 수"]), mains, [f for f in foods if f.side])
    return None


# 직업 구분의 입말(카드에는 집계 파일의 이름을 그대로 쓴다)
JOB_SPOKEN = {"1": "관리직이나 전문직", "2": "사무직", "3": "서비스·판매직", "4": "농림어업 일을 하는 분들",
              "5": "기능직이나 기계 조작 일을 하는 분들", "6": "단순노무직", "7": "일하지 않는 분들(주부, 학생 등)"}


@dataclass
class JobRow:
    code: str
    name: str  # 카드의 이름
    spoken: str  # 말의 이름
    n: int
    share: float
    base: float
    ratio: float


@lru_cache(maxsize=1)
def _job_rows() -> list[dict[str, str]]:
    return _read(CLEAN / "knhanes_2024_beverage_by_job.csv")


def by_job(kind: str) -> list[JobRow]:
    """직업 구분마다 다른 음료(술은 다른 술)보다 몇 배 자주 마시나. 배수가 큰 순서. 마신 끼니 30건 이상만 있다."""
    out = [JobRow(r["직업 구분 코드"], r["직업 구분"], JOB_SPOKEN.get(r["직업 구분 코드"], r["직업 구분"]),
                  int(r["마신 끼니 수"]), float(r["가중 비율(%)"]), float(r["모든 음료에서의 가중 비율(%)"]),
                  float(r["몇 배"]))
           for r in _job_rows() if r["음료 종류"] == kind and int(r["마신 끼니 수"]) >= MIN_FOUND]
    out.sort(key=lambda r: r.ratio, reverse=True)
    return out


# ---------- 조사(은/는 등) ----------

_DIGIT_BATCHIM = {"0": True, "1": True, "2": False, "3": True, "4": False, "5": False, "6": True, "7": True, "8": True, "9": False}


def _batchim(word: str) -> tuple[bool, bool]:
    """(받침이 있는가, 받침이 ㄹ인가). 한글이 아니면 받침 없음으로 본다."""
    w = word.rstrip(" )\"'”’")
    if not w:
        return False, False
    ch = w[-1]
    if "가" <= ch <= "힣":
        jong = (ord(ch) - 0xAC00) % 28
        return jong != 0, jong == 8
    if ch in _DIGIT_BATCHIM:
        return _DIGIT_BATCHIM[ch], ch in "178"
    return ch.lower() in "lmnr", ch.lower() == "l"


def josa(word: str, pair: str) -> str:
    """josa("제로 탄산", "은/는") → "은". pair는 받침 있을 때/없을 때."""
    has, is_l = _batchim(word)
    a, b = pair.split("/")
    if pair == "으로/로":
        return "로" if (not has or is_l) else "으로"
    return a if has else b
