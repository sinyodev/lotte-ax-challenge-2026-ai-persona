# 약속: 제공 자료에서 만든 표 (`data/onsite/`)

본선에서 받은 자료(`data/raw/onsite/`)를 W1이 정제해 `data/onsite/`에 만든다. 다른 묶음은 원본을 직접 읽지 않고 이 표만 읽는다. **두 폴더 모두 저장소에 올라가지 않는다.** 원본의 구성은 `docs/background/05-task-and-data.md` 2절, 정제 규칙은 `docs/build-plan.md`의 W1에 있다.

## 읽는 법

```python
import onsite                      # app/server/onsite/

onsite.available()                 # data/onsite/가 만들어져 있으면 True. 없으면 기능은 "자료 없음" 상태로 둔다(오류를 내지 않는다)
onsite.load("pos_clean")           # list[dict]. 열 이름은 아래. 숫자는 숫자, 빈칸은 None, 날짜와 달은 문자열
onsite.load_json("survey_summary") # dict
onsite.frame("pos_clean")          # pandas.DataFrame이 필요할 때
```

- 만들기: `cd app/server && uv run python -m onsite.build` (원본이 없으면 그 사실을 알리고 0이 아닌 값으로 끝난다).
- `load`는 파일을 한 번 읽어 기억한다. 없는 이름이면 `KeyError`, 자료 폴더가 없으면 `onsite.NoData`.
- 폴더 위치는 저장소 뿌리의 `data/onsite/`. 환경 변수 `AX_ONSITE_DIR`로 바꿀 수 있다(테스트용).

## 표

열 이름은 영어 소문자, 값은 원본의 한글 그대로(권역, 채널, 제품명 등).

### `pos_clean.csv` — 월·권역·채널·제품별 판매 (정제 뒤)

| 열 | 뜻 |
|---|---|
| `month` | `YYYY-MM` |
| `region` | 권역 6개 |
| `channel` | 편의점, 대형마트, SSM, 온라인, 자판기·기타 |
| `sku`, `name`, `brand`, `category` | 제품 |
| `units` | 판매수량, **낱개**(상자 단위는 24를 곱함) |
| `amount` | 판매금액(원) |
| `promo` | 없음, 1+1, 2+1, 할인10%, 할인20% |
| `is_own` | 자사 제품이면 true (브랜드가 "경쟁사…", "편의점PB…"로 시작하지 않는 것) |
| `after_end` | 제품 자산 DB의 단종일 뒤의 판매면 true |

### `sellin.csv`

`month`, `channel`, `sku`, `name`, `units`(출고수량, 전국). 소비자 판매가 아니다.

### `temperature.csv`

`month`, `region`, `temp_c`.

### `assets.csv` — 제품 자산 DB (운영, 단종, 개발 중단, 아이디어)

| 열 | 뜻 |
|---|---|
| `asset_id` | 고유 번호. `sku`가 겹치는 행이 있어 따로 만든다(`<sku>-<순번>`) |
| `sku`, `name`, `brand`, `category`, `pack` | 제품과 용기·용량 |
| `launched`, `ended` | `YYYY-MM-DD` 또는 빈칸 |
| `status` | 운영, 단종, 개발중단, 아이디어 |
| `concept` | 컨셉 요약 |
| `peak_sales_100m` | 최고 연매출(억 원) 또는 빈칸 |
| `reason` | 단종·중단 사유. **없으면 빈칸**(지어내지 않는다) |
| `note` | 비고 |
| `flags` | 쉼표로 이은 표시: `duplicate_sku`, `date_reversed`, `reason_missing` |

### `infra.csv`

`channel`, `stores`, `frozen_rate`(냉동 음료 진열 가능 점포율), `chilled_rate`(냉장 쇼케이스 보유율), `note`.

### `past_tests.csv` — 과거 컨셉테스트와 출시 뒤 실적

`product`, `year`, `category`, `intent_top2`, `distribution_6m`(출시 6개월 취급 점포율), `trial_12m`(출시 12개월 실제 구매경험률), `ratio`(실제/의향), `note`.

`GET /api/onsite/purchase-outcomes`는 현재 조사 컨셉(`concepts`)과 과거 출시 제품(`history`)의 구매의향과 실적을 반환한다. 현재 컨셉의 `intent_top2`는 제시 순서 보정값을 우선하고, 없으면 모집단 가중값을 쓴다. 사용한 방법은 `intent_method`에 담는다. 같은 이름의 실적을 하나로 특정할 수 있을 때만 `trial_12m`에 값을 채우며, 미측정은 `null`, 관측된 0%는 `0`이다. 과거 제품의 `actual_to_intent`는 두 집계 비율을 나눈 값이다. 대화에서는 `purchase_outcomes`로 제품명을 찾아볼 수 있다. 결과 보고서는 해당 제품의 두 지표, 이번 가상 매대 선택, 같은 종류의 과거 실적을 출처별로 표시한다.

### `survey_respondents.csv` — 정량 조사 응답자 (정제 뒤, 한 사람 한 줄)

`rid`, `gender`, `birth_year`, `age_band`(19~29세 …), `region`, `job`, `income`(빈칸 가능), `buy_coffee`, `buy_soda`, `buy_juice`(월 구매 횟수), `main_channel`, `novelty`(신제품 시도 성향 1~5), `health`, `price_sens`, `seconds`(응답 시간), `order`(컨셉 제시 순서), **`weight`**(모집단 구성비에 맞춘 가중치, 평균 1).

휴대폰 해시와 응답 일시는 싣지 않는다.

### `survey_ratings.csv` — 응답자·컨셉별 평가 (정제 뒤)

`rid`, `concept`(밀키스 화채, 레쓰비 프리즈, 쥬시모먼트), `understand`, `like`, `distinct`, `intent`, `price_ok`(각 1~5), `wtp`(최대지불의향가격, 빈칸 가능), `monthly`(예상 월 구매 횟수), `shown_price`, `price_format`, `position`(본 순서 1~3), `comment`(자유응답), `leading`(유도 문항·다른 가격 표기면 true).

### `survey_summary.json`

```json
{
  "n": {"raw": 0, "clean": 0},
  "concepts": {
    "밀키스 화채": {
      "top2": {"raw": 0.0, "clean": 0.0, "weighted": 0.0, "order_adjusted": 0.0},
      "by_position": {"1": {"n": 0, "top2": 0.0}, "2": {}, "3": {}},
      "segments": [{"age_band": "19~29세", "gender": "여성", "n": 0, "top2": 0.0}],
      "wtp": {"median": 0, "p25": 0, "p75": 0, "n": 0},
      "leading": false
    }
  }
}
```

`top2`는 구매의향 4·5점의 비율. `segments`의 `top2`는 가중한 값이고 `n`은 가중하지 않은 사람 수다.

### `population.csv` — 모집단 구성비 (가중치와 전체 선택률 계산에 쓴다)

`dimension`(`age_gender` 또는 `region`), `age_band`, `gender`, `region`(해당 없는 칸은 빈칸), `share`.

### `cleaning_report.json` — 걸러 낸 것

```json
[{"source": "survey", "rule": "duplicate_hash", "label": "두 번 답한 응답자", "removed": 0, "flagged": 0, "detail": "…"}]
```

`source`는 `pos`, `assets`, `survey`, `fgi`, `trend`, `journeys_online`. `label`은 화면에 그대로 보일 수 있는 한글 한 줄.

### `fgi.json` — 정성 조사 요약

```json
{
  "method": {"groups": 3, "per_group": 5, "minutes": 100, "cost_10k_won": 1200, "weeks": 6, "recruit_note": "…"},
  "participants": [{"id": "F01", "age": "20대", "gender": "여성", "job": "…", "rtd_per_week": 1, "scores": {"밀키스 화채": 5, "레쓰비 프리즈": 3, "쥬시모먼트": 4}}],
  "quotes": [{"concept": "밀키스 화채", "text": "…", "by": "F01"}],
  "moderator": [{"concept": "레쓰비 프리즈", "text": "…", "claimed": {"n": 12, "of": 15}, "recount": {"score_4plus": 6, "of": 15}, "mismatch": true}],
  "overall": ["…"]
}
```

### `trend.csv` — 검색·SNS (세로로 푼 꼴)

`month`, `keyword`, `search_index`(0~100, 음수는 0으로), `search_raw`(원본 값), `sns_mentions`(음수는 0으로), `sns_raw`, `ad_share`(광고·협찬 비중), `sns_organic`(= `sns_mentions` × (1 − `ad_share`)).

### `trend_related.csv`, `trend_volume.csv`

`keyword`, `related`, `share` / `keyword`, `searches_at_100`.

### `journeys_offline.csv` — 매장 관찰 15건

`oid`, `date`, `store`, `store_type`(편의점, 대형마트), `age`, `gender`, `purpose`, `seconds`(매대 도착에서 선택까지), `compared`(비교한 제품 수), `gaze_new_s`(신제품 매대 시선 고정), `chosen`, `bought`, `memo`, **`style`**(습관형, 탐색형, 행사형, 목적형. 규칙은 `docs/build-plan.md` W8).

### `journeys_online.csv`

`log_id`, `session`, `cookie`, `ts_kst`, `source`, `event`(노출, 클릭, 상세보기, 장바구니, 구매), `sku`, `name`, `dwell_s`, `device`, `promo`, `is_bot`(자동 접속으로 보이면 true. 행은 지우지 않고 표시한다).

## 컨셉 세 가지 (`concepts.json`)

과제 설명 자료의 컨셉 보드를 옮긴 것. W1이 `app/server/onsite/concepts.py`에 상수로 둔다(자료 폴더가 없어도 쓸 수 있게).

```json
[{"id": "milkis-hwachae", "name": "밀키스 화채", "brand": "밀키스", "kind": "탄산", "summary": "…",
  "variants": [{"pack": "슬림캔", "volume_ml": 250, "price": 1200, "factory_price": 780},
               {"pack": "PET", "volume_ml": 500, "price": 1800, "factory_price": 1200}],
  "storage": "상온", "season": "5~9월 한정", "launch": "2027-05", "channels": ["편의점", "대형마트·SSM", "온라인"],
  "keywords": ["수박화채"]}]
```

`storage`는 상온, 냉장, 냉동. 값은 `docs/background/05-task-and-data.md` 1절의 표에서 가져온다.
