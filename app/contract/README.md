# 약속: 서버와 화면이 주고받는 것 (v1.22, 2026-11-24)

서버(`app/server`)와 화면(`app/web`)은 이 문서에 적힌 형식으로만 주고받는다. 한쪽을 고치려면 이 문서를 먼저 고친다. 구현 세션은 이 문서를 고치지 않는다. 고쳐야 하면 멈추고 보고한다.

## 1. 큰 그림

```
화면 useChat ──POST /api/chat──▶ 서버
                                   칠성이(상태 기계 또는 재생)가 "칠성이의 이벤트"를 낸다   ← 2절
                                   내보내는 곳 한 군데가 AI SDK의 UI 메시지 스트림으로 바꾼다 ← 3절
화면 ◀──────── SSE ───────────────┘
```

- 서버 안에서는 **칠성이의 이벤트**(2절)만 다룬다. 내보내는 형식(AI SDK, 나중에 AG-UI)은 `export` 한 곳만 안다.
- 칠성이가 화면에 내보낼 수 있는 것은 2절의 여덟 가지가 전부다. 화면은 모르는 종류를 받으면 무시하고 콘솔에 경고만 남긴다.

## 2. 칠성이의 이벤트

| 종류 `t` | 뜻 | 놓이는 곳 |
|---|---|---|
| `say` | 칠성이의 말 | 대화 |
| `activity` | 지금 하는 일 한 줄("세븐일레븐 음료 매대를 보고 있어요") | 대화, 말 위 |
| `choices` | 질문의 답 고르기(선택지 칩) | 대화, 말 아래 |
| `actions` | 다음에 할 일(버튼 묶음, 많아야 셋) | 대화, 말 아래 |
| `confirm` | 되돌리기 어려운 일의 확인 카드 | 대화, 말 아래 |
| `summary` | 대화에 남기는 한 줄 결과 | 대화, 말 아래 |
| `stage` | 지금 단계 | 단계 표시줄 |
| `card` | 작업대의 카드를 열거나 고친다 | 작업대 |

규칙: 칠성이의 한 차례에는 `choices`, `actions`, `confirm` 중 **하나만** 있다. `say` 없이 이들만 보내지 않는다.

### 형식

```ts
type StageId = "idea" | "concept" | "shelf" | "result" | "improve" | "report"

type Say      = { t: "say"; text: string;
                  speaker?: { kind: "shopper"; label: string } }  // v1.7: 없으면 칠성이. 테스트의 손님 한 명("24세 여자, 대학생")
type Activity = { t: "activity"; id: string; label: string; status: "running" | "done" }
type Choices  = { t: "choices"; id: string; kind: "single" | "multi";
                  options: { id: string; label: string; note?: string }[];
                  free?: { label: string };   // 있으면 마지막에 "직접 정할게요" 같은 칩. 누르면 입력창으로 간다
                  on_card?: string }          // 있으면 그 id의 카드 안에서 고른다(options의 id = 카드 항목의 id)
type Actions  = { t: "actions"; id: string;
                  actions: { id: string; label: string; note?: string; primary?: boolean }[] }
type Confirm  = { t: "confirm"; id: string; title: string; desc?: string;
                  rows: { label: string; value: string; note?: string }[];
                  confirm: { id: string; label: string };
                  cancel: { id: string; label: string } }
type Summary  = { t: "summary"; id: string; title: string; value: string; note?: string }
type Stage    = { t: "stage"; current: StageId }
type Card     = { t: "card"; id: string; stage: StageId; kind: CardKind; title: string;
                  status: "loading" | "ready" | "error"; payload: unknown;
                  origin?: Origin }           // 카드 전체의 근거 표시(예: 아이디어 카드는 "suggestion")
type Origin   = "record" | "sales" | "shelf" | "web" | "suggestion"
                // 소비자 기록, 편의점 매출, 매대, 웹에서 찾은 것, 칠성이의 제안
```

- `id`는 대화 하나 안에서 고유하다. 같은 `id`의 `activity`나 `card`를 다시 보내면 **앞의 것을 바꾼다**(브리프가 채워지는 것, 진행 상황).
- `label`, `title`, `text`, `note`, `value`는 화면에 그대로 나오는 글이다. 서버가 완성된 문장을 보낸다. 화면은 이 글을 고치지 않는다.

### 카드의 종류 `CardKind`와 `payload`

| `kind` | 단계 | `payload` |
|---|---|---|
| `brief` | idea | (v1.3) `thoughts?: string[]`가 더해진다: 기획자가 넣은 방향("아침용", "유자"). 칸의 `state`는 `"set"`과 `"empty"`만 쓴다(`"asking"`은 보내지 않는다). 빈 칸은 화면에 보이지 않는다. `{ fields: { key: "product"\|"channel"\|"target"\|"occasion"\|"need"; label: string; value: string \| null; note?: string; state: "set"\|"asking"\|"empty" }[] }` |
| `evidence` | idea | `{ items: { id: string; origin: Origin; text: string; source: string; url?: string; date?: string; note?: string }[] }` 근거 카드. `source`는 자료나 글의 이름, `note`는 "기록이 적어서 참고만 해 주세요", "오래된 글이에요" 같은 주의 |
| `ideas` | idea | `{ basis: string; items: { id: string; name: string; flavor: string; pack: string; features: string[]; line: string; diff: string; by?: "chilseong" \| "planner"; kept?: boolean; changed?: string[] }[] }` `by`는 누가 낸 것인지, `kept`는 기획자가 남기기로 한 것, `changed`는 방금 고쳐진 칸의 이름(`"name"`, `"flavor"`, `"pack"`, `"features"`, `"line"`) |
| `concepts` | concept | `{ items: { id: string; name: string; headline: string; need: string; benefit: string; rtb: string; volume: string; price: string; price_basis: string; promo: string; basis: string; diff: string }[] }` |
| `shelf-run` | shelf | `{ run_id: string; concept: { name; pack; container; volume; price }; who: string }` 숫자는 카드가 `GET /api/runs/{id}`에서 읽는다 |
| `result` | result | `{ run_id: string }` 숫자는 카드가 `GET /api/runs/{id}`에서 읽는다 |
| `improve` | improve | (v1.7, v1.11) `{ base_run: string; items: { id: string; kind?: "price" \| "name" \| "pack" \| "promo"; change: string; before?: string; after?: string; reason: string; run_id?: string }[] }` 처음 안(기존안)의 테스트와 고친 안(변경안)들. 숫자는 카드가 `GET /api/runs/{id}`에서 읽는다 |
| `report` | report | `{ sections: { title: string; body: string }[] }` |

- 화면이 제대로 그리는 것은 `brief`, `evidence`, `ideas`, `concepts`다(1부 컨셉 기획). 나머지는 제목과 받은 값을 단순한 목록으로 보여 주는 임시 모습이면 된다. 카드마다의 모습은 뒤의 지시서에서 정한다.
- 카드의 `status`가 `loading`이면 뼈대(스켈레톤), `error`면 "불러오지 못했어요"와 다시 하기.

## 3. 내보내는 형식: AI SDK의 UI 메시지 스트림

`POST /api/chat`의 응답은 SSE이고 머리에 `x-vercel-ai-ui-message-stream: v1`을 넣는다. 형식의 원문은 `app/web/node_modules/ai/docs/04-ai-sdk-ui/50-stream-protocol.mdx`다. 구현하기 전에 읽고, 아래와 다르면 원문을 따르고 보고한다.

| 칠성이의 이벤트 | 스트림의 파트 |
|---|---|
| 차례의 시작과 끝 | `start`, `start-step` … `finish-step`, `finish`, 마지막 줄 `data: [DONE]` |
| `say` | `text-start`, `text-delta`(몇 글자씩 끊어서), `text-end`. (v1.7) `speaker`가 있으면 `text-start`의 `providerMetadata`에 `{ "chilseong": { "speaker": … } }`로 싣는다(AI SDK가 글 파트의 `providerMetadata`로 옮긴다. 저장한 대화의 글 파트에도 같이 남는다) |
| 나머지 일곱 가지 | 자료 파트 `{ "type": "data-<t>", "id": <id>, "data": <t와 id를 뺀 나머지> }` |

- `stage`의 자료 파트 `id`는 늘 `"stage"`다.
- 자료 파트는 메시지에 남는다(잠깐 쓰고 버리는 파트로 보내지 않는다). 화면은 메시지들의 파트를 처음부터 차례로 읽어 단계와 작업대의 상태를 만든다. 그래서 대화를 다시 불러와도 같은 화면이 된다.
- 도구 호출 파트는 v1에서 쓰지 않는다.

## 4. 화면이 서버에 보내는 것

`useChat`의 기본 전송(`DefaultChatTransport`, `api: "/api/chat"`)을 쓴다. 본문에 더하는 것:

```ts
{ mode: "manual" | "suggest" | "delegate" }   // 진행 방식: 직접 바꾸기, 추천받기, 칠성이에게 맡기기
```

기획자의 답은 늘 **기획자의 말(글 메시지)** 로 보낸다. 칩이나 버튼을 눌러도 대화에 기획자의 말풍선으로 남는다.

- 글: 고른 것의 `label`(여럿이면 쉼표로 잇는다).
- 메시지의 `metadata`: `{ reply: { to: <choices·actions·confirm의 id>, ids: <고른 것의 id들> } }`. 직접 써서 보낸 말에는 `metadata.reply`가 없다.

## 5. 재생 방식

모델 없이 대본 파일을 흘려보내는 방식이다. 화면 개발과 시연의 폴백에 쓴다.

- 대본: `app/server/replay/<이름>.json`. `{ "name", "sample": true, "turns": [ [이벤트, …], … ], "after": [이벤트, …] }`
- 기획자의 n번째 말에 `turns[n-1]`을 내보낸다(무슨 말을 했는지는 보지 않는다). 대본이 끝난 뒤의 말에는 `after`를 내보낸다.
- 대본에서만 쓰는 것: `{ "t": "wait", "ms": 600 }`(잠깐 쉼). 내보내지 않는다. `activity`는 대본에 `{ "t":"activity","id","label","ms" }`로 적고, 서버가 `running`을 보낸 뒤 `ms`만큼 쉬고 `done`을 보낸다.
- `sample: true`인 대본의 숫자는 모양을 보이려고 넣은 견본이다. 화면은 이때 단계 표시줄 옆에 "견본 대화"라고 표시한다. 서버는 차례의 첫머리에 자료 파트 `{ "type": "data-session", "id": "session", "data": { "source": "replay", "sample": true } }`를 보낸다.

## 6. 바뀐 것

- v1.5 (2026-11-21, 지시서 14 신제품 제안서): `concepts`의 `spec`에 `own` 줄(이름 "자사 유사 제품")이 생긴다. `rivals` 다음, `pod` 앞에 오고 값의 모양은 `rivals`의 한 줄과 같다. 자사(롯데칠성)에 비슷한 제품이 없으면 줄이 없다. `rivals`에는 이제 다른 회사 제품만 온다. 더한 것뿐이라 옛 화면도 그대로 맞는다. 확정한 뒤의 버튼 묶음의 `download`(이름 "제안서로 내려받기")는 말을 보내지 않고 화면이 `/proposal/<대화 id>`를 새 탭으로 연다. 제안서는 `GET /api/chats/{id}/proposal`(컨셉이 없으면 404)로 받는다. 형식은 `app/tasks/14-proposal-download.md` 2절.
- v1.4 (2026-11-21, 컨셉 카드를 예시 시안과 제품 특징으로): `concepts`의 항목이 바뀐다. `{ id; name; headline; benefit; points: string[]; price: string; pack: string; spec: { key: string; label: string; value: string }[]; changed?: string[] }`. 위쪽 "예시 시안"에 쓰는 것은 `headline`(상황을 담은 한 줄), `name`, `benefit`(혜택 한 줄), `points`("이런 점이 좋아요"의 세 줄), `price`와 `pack`("1,500원", "250ml 캔"). 아래쪽 "제품 특징"은 `spec`의 줄을 순서대로 그린다. `spec`의 `key`는 컨셉끼리 같은 줄을 맞추는 데 쓴다(`type`, `flavor`, `pack`, `sugar_caffeine`, `carbonation`, `target`, `occasion`, `channel`, `price`, `rivals`, `pod`). 값 안의 줄바꿈(`\n`)은 줄을 나눠 그린다. `changed`에는 `headline`, `name`, `benefit`, `points`나 `spec`의 `key`가 온다. 앞선 칸(`need`, `rtb`, `volume`, `promo`, `price_basis`, `basis`, `diff`)은 보내지 않는다.
- v1.3 (2026-11-21, 열린 대화): 아이디어 회의와 컨셉 보드는 횟수 없이 이어진다. 같은 `id`의 `ideas`, `concepts`, `brief` 카드가 차례마다 다시 온다. `ideas`의 항목에 `by`, `kept`, `changed`를, `brief`에 `thoughts`를 더했다. `concepts`의 항목에도 `changed?: string[]`가 올 수 있다. 근거 카드의 이름표는 `origin`의 분류 이름이 아니라 `source`(출처의 이름)를 보인다. `origin`은 "웹에서 찾은 것인지"를 모양으로 구별하는 데만 쓴다. 화면이 카드에서 보내는 일(남기기, 빼기)은 따로 형식을 두지 않고 기획자의 말로 보낸다("○○은 남겨 줘").
- v1.2 (2026-11-20, 진짜 칠성이): 근거 카드(`evidence`)와 근거 표시(`Origin`, 카드의 `origin`)를 더했다. `choices`에 직접 쓰는 길(`free`)과 카드 안에서 고르기(`on_card`)를 더했다. `data-session`의 `source`는 `"replay"` 또는 `"live"`다. 모두 더한 것이라 v1.1의 대본은 그대로 맞는다.
- v1.1 (2026-11-20, 참가자의 검토): `actions`의 버튼과 `confirm`에 설명(`note`, `desc`)을 더했다. `brief`의 칸에 덧말(`note`), `ideas`에 정해진 칸(맛 `flavor`, 용기와 용량 `pack`, 특징 `features`), `concepts`에 컨셉보드의 요소(니즈, 혜택, 믿을 근거, 가격의 근거, 도출 근거)를 더했다. 일을 1부 컨셉 기획(`idea`, `concept`)와 2부 매대 테스트(`shelf`, `result`, `improve`, `report`)로 나눈다. 단계의 이름(`StageId`)은 그대로다.
- v1.10 (2026-11-24, 지시서 18 참가자의 지적): 손님 인터뷰의 `choices`에 칩 `interview-next`(다른 손님 인터뷰하기: 지금 손님을 보내고 아직 안 부른 손님을 부른다)를 `interview-end`(인터뷰 마치기) 앞에 더했다(많아야 다섯). `ask-shopper`(손님 인터뷰하기)와 `interview-next`는 테스트마다 아직 안 부른 손님을 차례대로 부르고, 모두 불렀으면 처음부터 돈다. 테스트를 한 대화의 버튼 묶음에 `show-result`(결과 보기)를 더했다(`go-shelf`, `report`와 함께). 개선안 뒤의 `improve-compare` 묶음에도 `report`가 함께 온다. 확인 카드의 손님 줄에는 `note`를 싣지 않는다. 결과 카드는 `who.occasion`, `who.occasion_share`를 그리지 않는다(서버는 그대로 보낸다).
- v1.11 (2026-11-24, 지시서 19): `improve` 항목에 `kind`(바꾼 것: price, name, pack, promo), `before`, `after`(타일에 그리는 앞뒤 값. 예: "2,200원", "1,800원")를 더했다. `change`는 그대로 온다. 옛 대화의 항목에는 없으니 화면은 `change`를 "→"로 갈라 쓴다. 안의 이름은 서버(`improve.plan_name`)와 화면(`planName`)이 같은 규칙으로 만든다(기존안, 가격 변경안, 같은 종류가 둘이면 "가격 변경안 2"). 버튼 `improve-all`의 이름은 "남은 안 모두 테스트하기", `improve-compare`는 "변경안 결과 보기"이고, 개선안 카드가 그 이름을 그대로 보내도 같은 일을 한다.
- v1.12 (2026-11-24, 지시서 20): 개선안 카드도 이 화면에서 도는 것을 본 변경안이 모두 결과를 말할 만해지면(끝났거나 100명이 다녀감) "변경안 결과 보기"를 `metadata.reply { to: "auto", ids: [] }`와 함께 한 번 스스로 보낸다. 변경안을 돌리기 시작한 뒤와 아직 도는 중의 버튼 묶음(`improve-wait`)에는 `improve-compare`가 없고 `report`만 온다.
- v1.13 (2026-11-24, 지시서 22 결과 보고서): 제안서(`GET /api/chats/{id}/proposal`)의 종이 `test`의 모양을 바꿨다(옛 `lines`, `improve`, `progress`는 없다). 문장은 모두 서버가 규칙과 글틀로 만들고(`agent/review.py`, 모델 없음) 화면은 그리기만 한다.
- v1.14 (2026-11-24, 지시서 25 제공 자료 정제): `/api/onsite/status`, `/cleaning-report`, `/concepts`를 더했다. 표의 형식은 [제공 자료 약속](onsite-data.md). 상세는 이 문서 끝의 "W1 추가".
- v1.15 (2026-11-24, 지시서 27 매대 결합과 탐색 테스트): 매대의 제품에 `sku`, `is_own`, 진열 조건 `placement`가 붙었다. 카드 `explore`(전 연령 탐색 테스트)와 타깃 고르기, 실행 기록의 `requested`·`total`·`usage`를 더했다. 서버 테스트는 기본으로 "제공 자료 없음" 상태에서 돈다(`conftest.py`가 `AX_ONSITE_DIR`를 빈 임시 폴더로 둔다). 상세는 이 문서 끝의 "W4·W5 추가".
- v1.16 (2026-11-24, 지시서 26 트렌드): `/api/trends`, `/api/trends/tracking`, `/api/trends/refresh`, `/api/trends/{keyword}`(판정)를 더했다. 카드 `trend`, 근거 표시 `internal`(내부 자료). 서버가 서울 시각 오전 8시 30분에 뉴스레터를 한 번 발행한다(`AX_TREND_SCHEDULE=0`이면 끈다. 시험에서는 꺼 둔다). 상세는 이 문서 끝의 "W2 추가".
- v1.17 (2026-11-24, 지시서 31 아이디어 보드): `/api/ideas`(만들기, 조회, 고치기, 진행 기록과 첨부, 가져오기), `/api/ideas/dashboard`(출시 집계 `launches`, `undated_launches`), `/api/ideas/cases`(과거 사례 검색), 카드 `history`(비슷한 과거, 보드 상세 `/ideas?idea=<id>`로 이어짐). **아직 없는 것**: `ideas.attach_research`와 `/panel?idea=<id>`로 가는 "조사 결과 넣기"(W6과 함께 만든다). 상세는 이 문서 끝의 "W3 추가".
- v1.18 (2026-11-24, 지시서 32 결과 화면과 보고서): 실행 조회에 없어도 되는 칸 `brief`(알게 된 것, 근거 세 줄, 다음 행동), 제안서의 `pages[].test`가 `kind: "result-report"`의 새 모양(결재용 첫 장 → 근거 → 다음 실제 조사 → 부록), `PUT /api/chats/{id}/proposal/opinion`. 다른 묶음이 얹는 자리: 다음 행동은 `result_brief.RULES`, 보고서의 `evidence.voices`(W7)와 `evidence.compare`(W6)는 `proposal.REPORT_EXTRAS`. 상세는 이 문서 끝의 "결과 화면과 보고서 (지시서 32)".
- v1.19 (2026-11-24, 지시서 29 W7): 카드 `diagnosis`(컨셉 진단), `group`(소비자 인터뷰 FGI·FGD), 개선안의 같은 소비자 짝비교(`evidence.variants[].pair`, 채택 `adopted`)와 가격 세 점, 보고서의 `evidence.voices`, `metadata.reply.to`의 `w7-diagnose`·`improve`·`w7-adopt`·`w7-group`, 공개 `POST /api/runs`가 맛·제형·소구점을 받고 견줄 수 없으면 422. 컨셉을 올린 매대의 글에 컨셉 보드의 사실이 붙는다(원래 안과 고친 안은 같은 글틀, 컨셉이 없는 매대의 글과 열쇠는 그대로). `w7-demo-` 대화의 창작 대본은 가짜 응답기에서만 열린다. 상세는 이 문서 끝의 "W7 추가".
- v1.20 (2026-11-24, 지시서 33 제품 사양): 아이디어와 컨셉에 없어도 되는 칸 `variants[]`(규격, 권장 소비자가 `price`, 출고가 `factory_price`, 유통기한, 열량), `shelf_variant`(매대에 올릴 규격), `launch`, `season`, `channels`, `storage`. 과제의 세 컨셉은 이름이 맞으면 코드가 채운다. 매대에 올릴 규격은 `metadata.reply {to: "variant", ids: [컨셉 id, index]}`로 바꾼다. 상세는 이 문서 끝의 "제품 사양 (지시서 33)".
- v1.21 (2026-11-24, 지시서 24 W0 첫 커밋): 응답기 `AX_LLM=codex`(Codex 워크스페이스), 역할별 모델 `AX_MODEL_<ROLE>`·`AX_EFFORT_<ROLE>`(read, plan, shopper, interview, voice), 사용량 기록 `llm.usage`(실행 기록의 토큰과 API 추정 비용). 상세는 이 문서 끝의 "W0 추가".
- v1.22 (2026-11-24, W6): 단계 `followup`("후속 개선": 결과 보고서 다음에 같은 대화에 조사 엑셀을 올려 지금의 컨셉을 고친다), 카드와 올리기 주소, 조사에서 나온 개선안(`focus_id`), 가상 매출 `calibrate.sales.estimate`(W7의 가격 세 점에 금액이 붙는다), 보고서의 `evidence.compare`. 조사 답을 더해 다시 묻기(`runner.Spec.overlay`)는 아직 이어지지 않았다. 상세는 이 문서 끝의 "W6 추가".
  `test: { review: { text: string; tone: "weak" | "cannibal" | "ok" }; overview: string[]; findings: string[]; inflow: { label: string; n: number; share: string }[]; compare: { name: string; change: string; n: number; rank: number | null; rate: number; value: string; verdict: "base" | "better" | "same" | "worse"; best: boolean; line: string | null }[]; voices: { picked: { factor: string; quote: string; who: string } | null; passed: { factor: string; n: number; quote: string | null; who: string | null; others: string | null } | null }; plans: { title: string; body: string }[]; caution: string } | null`.
  `review`는 종이 맨 위의 검토 의견(weak·cannibal이면 화면은 경고의 면으로 그린다). `inflow`는 수요 유입 경로의 세 줄(선택이 없으면 빈 목록). `compare`는 변경안을 하나라도 돌렸을 때만(첫 줄은 기존안 `verdict: "base"`, `line`은 그 아래 줄글이고 기존안은 null, `rate`는 선택률 %로 막대의 길이, `best`는 가장 나은 better 하나). `voices`의 인용은 결과의 `quotes` 그대로, `who`는 나이대만. `plans`의 마지막은 늘 "실제 소비자 조사 연계". `caution`은 종이 맨 아래 유의 사항.
  `test`가 있는 종이는 `plan`이 빈 목록이고 `notices`에 테스트의 알림 줄이 없다(유의 사항은 `caution`). 종이의 차례: 검토 의견 → 테스트 개요 → 주요 결과 → 변경안 비교(있을 때) → 소비자 반응 → 시사점 및 향후 계획 → 제안 배경, 제품 개요, 경쟁 제품 및 차별점(번호를 이어서) → 유의 사항. 저장해 두는 것(대화 파일의 `proposal`)은 모델이 쓴 요지와 배경뿐이고 `test`는 열 때마다 새로 만드므로 옛 저장분도 새 모양으로 나온다.
- v1.9 (2026-11-24, 매대 테스트의 대화 흐름): 매대 테스트 카드는 기다리던 결과가 나오면(100명이 다녀갔거나 끝남) "먼저 온 결과 보기"/"결과 보기"를 `metadata.reply { to: "auto", ids: [] }`와 함께 스스로 보낸다. 화면은 이 말을 기획자의 말풍선으로 그리지 않는다. 결과 뒤의 버튼에 `ask-shopper`(손님에게 물어보기: 서버가 집은 손님, 없으면 안 집은 손님 한 명을 부른다)를 더했다. 확인 카드는 두 줄(컨셉, 손님)이고 자세한 것은 줄의 `note`에 싣는다. 작업대는 `shelf-run`과 `result` 카드를 가장 최근 것 하나만 보인다.
- v1.8 (2026-11-23, 컨셉을 올린 매대부터 묻기): `GET /api/runs/{id}`의 `asked`와 `result.n`은 컨셉을 올린 매대의 답이 온 손님 수다(전에는 두 답이 모두 온 손님). 컨셉이 없는 매대의 답은 뒤에 채워지므로 `result.from`에 `pending?: number`(집은 손님 가운데 전에 집던 것을 아직 모르는 수)를 더했다.
- v1.7 (2026-11-23, 지시서 17 한 손님에게 묻기·개선안 테스트·결과 보고서). 모두 더한 것이다.
  - `say`에 `speaker?: { kind: "shopper"; label: string }`. 없으면 칠성이. 스트림에서는 3절대로 `providerMetadata.chilseong.speaker`.
  - 결과 카드의 "이 손님에게 묻기"는 `metadata.reply { to: "visitor", ids: [run_id, visitor] }`로 보낸다(`visitor`는 결과의 `quotes[].visitor`). 부른 동안 기획자의 말은 읽기를 거치지 않고 그 손님에게 간다. 손님의 차례에는 `choices`(아직 하지 않은 물음과 "그만 묻기", 많아야 넷)가 온다.
  - `improve` 카드의 payload는 `{ base_run, items: { id, change, reason, run_id? }[] }`(옛 `caution`은 지웠다. 쓰는 곳이 견본뿐이었다). 줄의 "이 안으로 다시 묻기"는 `metadata.reply { to: "improve", ids: [안의 id] }`로 보내고, 서버가 그 값을 `change`로 `POST /api/runs`와 같은 길로 테스트를 시작한 뒤 `run_id`를 채운 카드를 다시 보낸다.
  - 버튼 id: `improve`(개선안 보기), `improve-all`(고친 안 모두 다시 묻기), `improve-compare`(다시 물은 결과 보기), `report`(결과 보고서 내려받기). `report`는 단계를 `report`로 옮기고 `download` 버튼을 낸다.
  - 제안서(`GET /api/chats/{id}/proposal`)의 종이마다 `test: { lines: string[]; improve: { label; change; picked; rank; note: string | null }[]; progress: string | null } | null`과 `notices: string[]`를 더했다. `test`가 있으면 화면은 "매대 테스트 결과"를 향후 계획 앞에 넣고 향후 계획의 번호를 민다. `notice`는 그대로 온다(옛 화면용).
- v1.6 (2026-11-23, 매대 테스트): `shelf-run`과 `result`의 payload를 테스트의 id로 바꿨다(숫자를 대화에 박아 두면 낡는다). 통로 `POST /api/runs`, `GET /api/runs/{id}`, `POST /api/runs/{id}/stop`을 더했다(모양은 `app/tasks/15-shelf-test-run.md` 1절). `/api/chats`의 항목에 확정한 컨셉(`concepts`)이 붙는다.

## W1 추가 (v1.14)

- `GET /api/onsite/status`는 `{available, built_at, tables}`를 돌려준다. 생성 시각은 UTC 문자열이고 표 목록은 확장자를 뺀 이름이다. 생성 전 응답은 `{available: false, built_at: null, tables: []}`다.
- `GET /api/onsite/cleaning-report`는 규칙별 정제 내역 목록을, `GET /api/onsite/concepts`는 컨셉 세 가지의 목록을 돌려준다. 생성 전에는 둘 다 빈 목록이다. 서버 코드에서는 자료 생성 전에도 `onsite.concepts.CONCEPTS`를 참조할 수 있다.
- 표와 JSON의 필드는 [제공 자료 약속](onsite-data.md)에 있다.

## W4 추가 (v1.15)

서버 테스트는 기본으로 제공 자료가 없는 임시 폴더를 쓴다. 정제표가 필요한 검사는 각자 견본 폴더를 지정하며, W1의 원본 검사는 실제 원본으로 임시 폴더에 표를 만든다.

편의점 음료 목록과 작업대는 같은 결합 매대를 쓴다. 제품에 판매 자료의 `sku`(없으면 null)와 `is_own`을 더한다. 기존 화면용 `ours`도 같은 자사 판정을 쓴다. 냉장·냉동 컨셉의 실행 조회에는 `placement: {storage, store_rate}`를 더한다. `store_rate`는 편의점 진열 가능 점포의 백분율이며 근거가 없으면 null이다.

## W5 추가 (v1.15)

- `shelf` 단계에서 탐색하거나 바로 타깃 테스트로 갈 수 있다. 새 카드 `explore`의 내용은 `{run_id}`다. 탐색 완료 카드는 ‘탐색 결과 보기’를 `reply.ids = ["explore-result", run_id]`로 보낸다. 기획자는 기존 타깃이나 구매 반응이 가장 높았던 대상을 고를 수 있다. 추천 대상이 첫 선택지이며, ‘다른 대상 고르기’에서는 연령대와 성별을 차례로 고른다.
- 실행 조회 `GET /api/runs/{id}`의 탐색 결과 `explore`에는 셀별 `cells[{age,sex,label,total,n,picked,rate,low,high}]`, 상황별 `occasions[{occasion,n,picked,rate}]`, 가중 전체 선택률 `overall_rate`, 가중 근거 `weighting`(population 또는 equal), 제안 집단 `suggested`, 구간 겹침 `overlap`이 담긴다. 선택률과 구간은 백분율이다. 유효 응답이 없는 집단은 응답한 사람 수와 구별한다.
- 실행 기록의 `requested`는 목표 인원, `total`은 배정 인원이다. `target_basis`는 타깃을 선택한 근거다. 탐색·타깃·개선안 실행의 `usage: {elapsed_s, calls, input_tokens, output_tokens, est_cost_krw, est_cost_usd, priced_as}`에는 경과 초와 실제 호출 수를 남긴다. 비용을 추정할 근거가 없으면 비용 칸을 생략해 표시한다. 이전 기록에서는 새 필드가 없을 수 있다.

## W2 추가 (v1.16)

- `GET /api/trends`와 `POST /api/trends/refresh`는 `{items, collected_at}`을 돌려준다. 수집 시각은 ISO 8601 또는 null이다. 수동 새로 고침은 수집 결과를 갱신하며 이미 발행한 호는 유지한다.
- 항목의 공통 값은 `{keyword, title, source, publisher, url, date, verdict}`다. 뉴스는 `source: "web", verdict: null`이고 글의 `id, summary, detail, question, sources, image, alt, photoCredit`을 더 담을 수 있다. 출처 하나는 `{source, date, text, url}`이다. 선별한 글의 보도 사진은 `GET /api/trends/photos/{id}`로 읽는다. 새 기사는 공식 원문이 제공한 설명과 대표 사진을 쓰며, 검증된 뉴스룸 호스트의 HTTPS 사진 주소를 직접 제공할 수 있다. 제목만 확인한 소식은 원문 목록에서 읽는다.
- `GET /api/trends/tracking`은 `{edition: {day, collectedAt, channels: {google, naver}, issue}, nextAt}`을 돌려준다. 각 채널의 `{ok, rows}`는 수집 성공과 빈 결과를 구별한다. 일별 수집과 발행 기준은 서울 시각 오전 8시 30분이며 서버를 다시 켜면 해당 회차를 확인한다. 새 호가 없으면 최근 호의 원래 발행일을 유지한다. 한 번도 발행한 호가 없으면 `issue`는 null이다.
- 호의 값은 `{id, date, topic, title, observation, menu, question, period, ranks, searchUrl, menuUrl, sources, image, alt, photoCredit}`이다. 검색 동향과 관련 상품을 함께 전하는 호에는 각각을 뒷받침하는 원문이 붙는다.
- `GET /api/trends/{keyword}`는 `{keyword, stage, reasons, series, ad_share_peak, product_search_share, related, source}`를 돌려준다. `stage`는 함께 해당하는 판정들의 배열, `series`는 달 순서의 `{month, search_index, sns_mentions, sns_organic, ad_share}` 배열, `related`는 `{related, share}` 배열이다. 비중은 0~1, 알 수 없는 값은 null이다. 내부 항목의 `verdict`도 같은 형식이다.
- 사이드바의 `트렌드 피드`는 `/trends`로 연결한다. 뉴스레터에서 기획을 시작하면 읽은 글과 원문 주소를 첫 메시지에 담는다. 1부 대화의 `activity`는 내부 자료, 웹 소식, 정리 순으로 진행을 알린다. 작업대의 `trend` 카드는 `idea` 단계의 `{items}`를 받고, 내부 근거는 `origin: "internal"`로 표시한다.

## W3 추가 (v1.17)

- `/ideas`는 보드를 기본 탭으로 열고 대시보드는 옆 탭에 둔다. `GET /api/ideas`의 `items`에는 아이디어, 출처, 상태, 검증 단계, 최근 테스트와 첨부 파일 수가 있다. `GET /api/ideas/dashboard`는 상태와 검증 단계별 건수, 조사 비용 어림의 기준과 집계, 최근 테스트를 돌려준다.
- `POST /api/ideas`는 `{key, name}`으로 직접 작성한 아이디어를 만들고 그 줄을 돌려준다. `key`는 재전송에 쓰는 UUID다. `PATCH /api/ideas/{id}`는 이름·담당자·판단 사유·상태·검증 단계의 변경분을 받는다.
- `GET /api/ideas/{id}/logs`는 최근 진행 기록부터 `{items: [{id, at, text, filename}]}`을 돌려준다. 같은 주소의 POST는 `{key, text, filename?, content_base64?}`를 받고 기록과 파일을 함께 저장한다. 파일은 `GET /api/ideas/{id}/logs/{key}/file`에서 내려받는다.
- `GET /api/ideas/import/prompt`, `POST /api/ideas/import/preview`, `POST /api/ideas/import/commit`은 정리 문구, 미리보기, 확인한 줄 저장에 쓴다. `GET /api/ideas/similar`는 겹친 근거와 점수가 있는 유사 이력을 반환한다.

### 팀 출시 실적과 기획 사례

- `/ideas?view=dashboard`는 월별 출시 실적을, `/ideas?idea=<id>`는 기획 상세와 진행 기록을 연다. 아이디어 행에는 기획 설명 `concept`, 실제 출시일 `launched_on`, 최근 작업 `last_work`, 작업 시각 `work_date`가 추가된다. 모르는 값은 null이다. 이름이나 첨부를 고친 날짜로 출시일을 추정하지 않는다.
- 연결된 대화에서 대상과 발언 시각이 확인되는 착수·중단 결정은 진행 기록에서 원문으로 볼 수 있다. 진행 기록과 지원 형식의 첨부에서도 명시적인 결정과 사유를 읽는다. 같은 결정을 사람이 나중에 정정하면 더 최근에 한 정정이 적용된다.
- `GET /api/ideas/dashboard`의 `launches`는 제품마다 최초로 확인한 실제 출시를 `{name, row_id, launched_on}`으로 준다. 출시일은 YYYY-MM-DD다. 같은 브랜드와 제품명의 용량 차이는 합치고, 출시 후 단종돼도 원래 출시일에 집계한다. 출시일을 모르는 제품 수는 `undated_launches`로 따로 준다.
- `GET /api/ideas/cases?q=검색어`는 출시·개발 중단·단종 이력을 `{items: IdeaRow[]}`로 준다. 기획 설명, 결정 사유, 진행 기록, 첨부 파일명에서 찾는다. 빈 검색어는 전체 과거 사례를 돌려준다.
- 기획 대화의 `history` 카드는 idea 단계에서 관련 사례를 최대 세 개 전한다. 각 항목에는 `id, name, status, reason, has_original`과 선택적인 `concept_excerpt, conditions`가 있다. 근거 링크는 해당 아이디어의 상세로 연결한다.
- 확정한 기획의 대화에서 사용자가 담당자를 명시하면 보드 행의 `owner`와 진행 기록에 반영한다. 컨셉이 여러 개면 해당 컨셉명을 적어야 한다. 같은 기획의 담당자를 다시 지정하면 최신 지정이 적용되고, `담당자: 미지정`은 배정을 해제한다.

## 결과 화면과 보고서 (지시서 32)

### 테스트 결과의 요약 구역

- `GET /api/runs/{id}`에 없어도 되는 칸 `brief: {headline, range, points, actions}`가 더해진다. 타깃 테스트(탐색·개선안이 아닌 것)에 결과가 있을 때만 온다. 글은 모두 서버(`agent/result_brief.py`, 글틀은 `agent/phrases.py`)가 만든다.
- `points[]`: `{key: "how"|"from"|"why", value, text, bar?: [{label, n, self}], of?, stacked?}`. 고른 사람이 없으면 `from`이 빠진다.
- `actions[]`(많아야 셋, 결과 보고서가 늘 마지막): `{id, reason|null, label, do}`. `do`는 `{say, to, ids}`(대화에서 그 버튼을 누른 것과 같은 말과 metadata.reply) 또는 `{stage: "concept"}`(작업대의 단계 이동). 대화에 같은 id의 버튼이 있으면 그 묶음 id와 말을 쓰고, 없으면 `to: "result-brief"`다. 인터뷰는 `to: "visitor", ids: [run_id, 방문]`.
- 규칙과 문턱값은 `agent/result_brief.py`의 상수다. 다른 묶음은 `RULES`에 `(Ctx) -> Action | None` 함수를 한 줄 더해 행동을 더한다(규칙에서 많아야 둘 + 결과 보고서).

### 결과 보고서

- 제안서(`GET /api/chats/{id}/proposal`)의 `pages[].test`가 새 모양이다: `kind: "result-report"`, `chat_id`, 첫 장 `head{title, product, spec}`, `recommend{verdict: research|retest|hold, text, reasons[]}`, `decisions[]`(많아야 셋), `key[{key, label, value, note}]`(네 칸), `limits[]`, `opinion`, `disclaimer` → 근거 `evidence{who{lines, cells}, from{rows, note}, barriers, variants, voices, compare}` → 다음 실제 조사 `next{target, questions, conditions, unknowns}` → 부록 `appendix{method, records, rules}`. 실행 시간과 호출 수는 `appendix.records`에만 있다. 제품 개요는 종이의 `overview`·`sketch`·`compare`를 부록에 그린다.
- 종이의 차례: 첫 장(결재용, A4 한 장) → 근거와 다음 실제 조사의 조건 → 부록. 화면의 종이, PDF 인쇄, "LLM용 복사"가 같은 차례와 글을 낸다. 옛 v1.13 모양(`review`, `plans`)은 서버가 더 내지 않는다.
- `evidence.variants`는 돌린 개선안이 있을 때만 차고, 비어 있으면 그리지 않는다.
- 이름 붙은 자리 둘: `evidence.voices[{factor, quote, who}]`(W7이 FGI·FGD 기록을 더한다), `evidence.compare[{title, lines[]}]`(W6이 실제 자료와의 대조와 가상 매출을 더한다. 비어 있으면 그리지 않는다). 더하는 법: 자기 새 파일에 `def add(note, concept, test) -> None`을 만들어 `test["evidence"][...]`에 덧붙이고, `agent/proposal.py`의 `REPORT_EXTRAS`에 한 줄 더한다.
- 기획자 의견: `PUT /api/chats/{id}/proposal/opinion` 본문 `{concept_id, text}`(2,000자까지), 답 `{concept_id, text}`. 대화 파일의 `report_opinion{컨셉 id: 글}`에 두고 `updated_at`은 바꾸지 않는다. 없는 대화나 컨셉이면 404.

## W7 추가 (v1.19)

### 밀키스 화채 조사실 데모

`AX_LLM=fake`에서 대화 ID가 `w7-demo-`로 시작하면 일반 `POST /api/chat`으로 데모를 진행한다. 서버에 빈 데모를 처음 만들 때 아래 본문을 한 번 보내고, 화면에서 `/test/w7-demo-milkis`를 연다. 저장된 차례는 기존 `GET /api/chats/{id}`로 다시 연다.

```json
{"id":"w7-demo-milkis","messages":[{"id":"opening","role":"user","parts":[{"type":"text","text":"밀키스 화채 조사실을 보여줘."}]}]}
```

- `result` 단계의 `group` 카드는 `demo: true`, 컨셉 이름, 참석자의 매대 선택, FGI·FGD 대본, 컨셉 진단 집계와 데모용 개선안 비교 집계를 담는다. 화면 형식은 `chat/contract-group.ts`와 `chat/contract-diagnose.ts`에 있다.
- 발언에는 `id`, `person`, `round`, `text`, `topic`이 있다. 토론에서 다른 사람의 말을 인용하면 `replyTo`에 앞 발언의 ID가 들어간다. 결론의 `turnIds`는 근거 발언 ID 목록이다. 대본은 서버에서 받아 재생한다.
- 발언을 골라 개선안을 열면 `metadata.reply = {to: "w7-demo-quote", ids: ["w7-quote/<발언 ID>"]}`를 보낸다. 서버가 대본에서 확인한 `quoteId`와 조사 방식, 비교 조건을 같은 카드에 저장한다.
- 진단 수치는 정제표와 결합 매대의 집계다. 개선안 비교는 같은 데모용 가상 소비자에게 제형, 맛 또는 가격 변경을 적용해 계산한다. 각 조건의 선택률과 인원, 두 조건에서 선택을 바꾼 인원, 가격 세 점의 선택률을 전달한다.

### 원래 안과 개선안의 매대 조건

- 새 실행은 제품 설명 방식의 판을 `concept_prompt_version: 1`로 기록한다. 실행 메타의 `concept`에 보드의 맛(`flavor`), 제형(`form`), 소구점(`appeal`)을 보존한다. 원래 안과 개선안의 상품 번호 뒤에 같은 형식으로 보드의 제품 정보를 붙인다. 특징과 니즈의 연결은 컨셉을 올린 매대에서 다시 계산한다.
- 개선 실행의 `base_run_id`는 배정표를 가져온 원래 실행 ID다. 컨셉 쪽 실행을 재사용하는 열쇠에 원래 실행 ID, 설명 방식의 판, 제품 특징, 응답기(`shopper_adapter`)를 넣는다. 컨셉이 없는 매대의 질문과 저장 열쇠(매대 판, 응답 모델, 소비자, 상황)는 유지한다.
- 매대 판이나 응답기가 바뀌면 원래 안부터 다시 묻는다. 설명 방식의 판이 없는 옛 실행은 저장한 결과를 그대로 열 수 있다. 옛 원안과 가격·이름·규격·행사를 비교할 때는 당시의 질문을 사용한다. 보드에 적힌 맛·제형·소구점을 추가로 보여 주어야 하는 비교는 새 원안 실행이 필요하다.

### 컨셉 보드에서 테스트 전 진단 열기

- 컨셉 확정 뒤 `diagnosis` 카드가 `concept_id, concept_name, sections, fixes`를 보낸다. 트렌드, 과거 이력, 가격, 유통마다 한 줄 요약과 펼쳐 볼 근거가 있다. 수치에는 단위와 비교 기준을 붙인다. 자료에 맞는 대안이나 단종 사유가 없으면 그 상태를 표시한다.
- (11-25) 트렌드 칸에 `keyword`(검색어, 없을 수 있음)를 더했다. 요약 문장은 판정 이름(피크아웃 등) 대신 쉬운 말로 쓰고, 과거 이력은 가운뎃점으로 잇지 않은 문장이다. 판정 이름은 `stages`에만 있고 화면이 쉬운 말로 바꿔 보인다.
- 승인 동작은 `metadata.reply.to = "w7-diagnose"`다. `ids`는 원래 안만 테스트할 때 `[concept_id, "original"]`, 고친 안만 또는 둘 다 테스트할 때 `[concept_id, "fix"|"both", fix_id]`다. 컨셉이 달라지면 다시 진단한다. 둘 다 고르면 탐색과 타깃 결정 뒤 같은 매대 방문으로 원래 안과 고친 안을 테스트한다.
- `GET /api/w7/diagnosis`는 밀키스 화채의 첫 규격을 진단한다. 시안은 화면에 표시한 규격을 `pack`으로 보낸다. 일반 대화에서는 컨셉 보드의 대표 규격을 읽는다. 정량조사에 제시한 규격이 다르면 해당 가격의 지불의향을 비워 둔다.

### 개선안 테스트와 채택

- `improve.items[]`에 바꿀 조건 `kind, before, after`, 가설 `hypothesis`, 출처 목록 `evidence[{origin, text, session_id?, quote_id?}]`를 더한다. 조건은 가격·용량·이름·행사·맛·제형·용기·소구점이다. 화면에서 여러 안을 골라도 각 실행에서 바뀌는 조건은 하나다.
- 완료된 비교의 `paired`에는 공통 방문 수 `n`, 두 안 모두 선택 `both`, 개선안에서만 선택 `gained`, 원래 안에서만 선택 `lost`, 두 안 모두 미선택 `neither`가 있다. 소비자·방문·음료를 마시는 상황이 모두 같은 응답을 짝짓는다. `delta_pp, low_pp, high_pp`의 단위는 %p다. 두 전환 비율의 Clopper–Pearson 구간을 Bonferroni 방식으로 보정해 차이의 95% 구간을 계산한다. 구간이 0을 포함하면 `verdict: "unclear"`다.
- `price_curve[]`는 가격을 낮춘 안, 원래 안, 가격을 올린 안의 `price, n, picked, rate, run_id?`다. 세 실행이 끝나면 세 가격에 공통으로 답한 방문을 집계한다. W6의 `calibrate.sales.estimate(concept, result)`가 추정치를 주면 해당 가격의 `sales`에 기간·금액 범위·가정을 담는다. 세 가격의 추정 기간이 같을 때 중앙 추정값을 비교한다.
- `reply.to = "improve"`로 여러 안을 실행한다. 채택은 `reply.to = "w7-adopt", ids = [base_run, item_id]`다. 테스트를 마친 안을 채택하면 보드의 조건과 채택 근거가 함께 저장된다. 같은 안을 다시 눌러도 한 번만 반영한다.
- `POST /api/runs`의 `change`는 같은 타깃·규모로 테스트한 원래 안의 저장 조건 하나를 바꾼다. 맛·제형·소구점은 각각 `flavor, form, appeal`이다. 견줄 실행이 없거나 제품 설명 방식·매대·응답기가 달라진 경우 422와 사유를 돌려준다.

### 결과에서 소비자에게 다시 묻기

- 결과의 ‘더 물어볼 곳’은 비구매 요인, 타깃 안에서의 선택 차이 등 해당 실행의 기록으로 질문을 제시한다. `group` 카드의 일반 조사 형식은 `demo: false, view: "setup"|"room"|"conclusion", run_id, concept, questions, candidates, suggested, selected_question_id?, session?`이다. `suggested`는 실제 방문 ID이며 참석자는 화면에서 바꿀 수 있다.
- `metadata.reply.to = "w7-group"`이다. `ids`는 조사 준비 `["open", run_id, 질문의 단서?]`, 1:1 인터뷰 `["one", run_id, question_id, visit_id]`, 집단 조사 `["start", run_id, question_id, "fgi"|"fgd", ...visit_ids]`, 저장한 조사 다시 열기 `["reopen", run_id, session_id]`다.
- FGI는 5~6명이 같은 질문에 한 사람씩 답한다. FGD는 1차에 독립적으로 답하고 2차에는 다른 참석자의 1차 발언을 보고 답한다. 한 사람의 한 차례마다 응답기를 한 번 부르고 재질문도 `session.calls`에 센다. 발언이 끝날 때마다 `turns`가 갱신된다. 화면은 재생·일시정지·다음 발언과 차례별·발언자별 전체 기록을 제공한다.
- FGI는 직접 밝힌 다음 선택 의향을 인원과 근거 발언으로 묶는다. FGD의 `findings.agreed, split, changed`에는 발언 원문으로 확인된 결론만 싣는다. 각 결론은 `{text, count, turn_ids}`다. `turns[].reply_to`는 인용한 발언의 ID다. 저장된 조사를 다시 열면 같은 실행의 기록을 이어서 읽는다.
- 발언의 ‘이 말로 개선안 만들기’는 `["quote", run_id, session_id, turn_id]`를 보낸다. 바꿀 조건이 여럿이면 하나를 고른다. 원문과 화자를 저장 기록에서 확인한 뒤 개선안에 붙인다. 결과 보고서의 `evidence.voices`에 조사 결론과 원문을, `evidence.variants[].pair`에 동일 방문의 선택 비교를 담는다. 채택한 줄에는 `adopted: true`와 채택 근거가 있다. 첫 장과 부록에서 같은 판정 기준을 사용한다. 화면·인쇄·복사에서 같은 내용을 읽을 수 있다.

## 제품 사양 (지시서 33)

- 아이디어 카드의 `items[]`(IdeaItem)와 컨셉 카드의 `items[]`(ConceptItem)에 없어도 되는 칸이 더해진다. 값이 있는 것만 온다. 옛 대화에는 없다.
  - `variants[]`: `{label, volume_ml?, price?, factory_price?, shelf_life_months?, shelf_life_days?, kcal?}`. `label`은 "슬림캔 250ml". `price`는 **권장 소비자가**, `factory_price`는 **출고가**(원).
  - `shelf_variant`: 매대에 올릴 규격의 차례(기본 0). 매대 테스트로 넘어가는 용기·용량과 가격(그 규격의 권장 소비자가)은 지금처럼 컨셉의 `_container`, `_volume`, `price`다.
  - `launch`("2027-05"), `season`("5~9월 한정"), `channels[]`, `storage`("상온"|"냉장"|"냉동").
- 채우는 차례(서버 `agent/idea_spec.py`): (가) 기획자의 아이디어 이름이 과제의 컨셉(`onsite/concepts.py`의 `CONCEPTS`) 이름과 같거나(공백·대소문자 무시) 그 이름을 담으면 그 사양 → (나) 모델이 기획자의 말에서 뽑은 칸이 말한 칸만 덮는다. 모델이 뽑은 숫자는 기획자의 말에 그 숫자가 있을 때만 쓴다. 칠성이가 스스로 낸 아이디어에는 사양이 없다.
- 규격이 하나이고 숫자가 용량뿐이면 `variants`를 보내지 않는다(화면은 지금처럼 "용기와 용량" 한 줄).
- 컨셉의 `spec[]`: `variants`가 있으면 `pack` 줄을 보내지 않고, `price` 줄은 매대에 올릴 규격의 권장 소비자가와 같으면 보내지 않으며, `channels`가 있으면 `channel` 줄을 보내지 않는다. 화면은 규격의 표(모든 줄이 비어 있는 열은 그리지 않는다), 출시, 판매 시기, 채널을 그린다.

## W0 추가 (v1.14 후보)

| 서버 환경 변수 | 용도 |
|---|---|
| `AX_LLM` | `cli`(기본, 기존 Claude CLI), `fake`(자동 테스트), `codex`(개발·검증용 Codex 워크스페이스), `openai`(최종 시연용 대회 API) |
| `AX_MODEL_<ROLE>` | 역할별 모델 ID. `<ROLE>`은 가상 소비자 선택 `SHOPPER`, 인터뷰 `INTERVIEW`, 요청 읽기 `READ`, 기획 판단 `PLAN`, 칠성이의 말 `VOICE` |
| `AX_EFFORT_<ROLE>` | 해당 역할의 GPT 추론 강도. 설정한 모델이 지원하는 값을 쓴다. |
| `AX_SHOPPER_MODEL`, `AX_VOICE_MODEL` | 기존 실행 설정과의 호환용. 역할별 모델 설정이 우선한다. |
| `AX_NOVELTY` | 11차 가상 소비자의 새로움 욕구(N08) 보정. `off`(그대로), `survey`(조사 신제품 시도 성향 분포에 맞춤), `strict`(더 낮은 안). 기본값은 `calibrate/novelty.py`의 `DEFAULT`(`strict`, `docs/reliability.md`의 측정으로 정함). `off`가 아니면 `shelf_v`가 바뀌어 저장된 답을 따로 쓴다. |
| `AX_CONCEPT_NOVELTY` | 11차에서 신제품 컨셉이 새로움 욕구(N08)를 채우는 관계. `well`(잘 채움), `partly`(조금 채움), `none`(관계에서 뺌, 기본값). `well`이 아니면 `shelf_v`가 바뀐다. |
| `AX_USD_KRW` | 추정 비용 환산에 쓸 달러당 원화. 기본 가정은 1,400원이다. |
| `OPENAI_BASE_URL`, `OPENAI_API_KEY` | `AX_LLM=openai`에서 사용하는 대회 게이트웨이 주소와 키. 환경에 없는 값은 서버의 `.env.local`에 있는 `KEY=VALUE` 줄에서 읽는다. |

`with llm.usage.collect() as u` 안에서 발생한 호출은 그 안에서 생성한 비동기 작업까지 함께 센다. `u.summary()`는 호출 수 `calls`, 실패 수 `failed_calls`, 입력·출력 토큰 `input_tokens`와 `output_tokens`, 개별 호출 시간의 합(초) `call_seconds`, 모델별 집계 `by_model`를 반환한다. 토큰 수를 글자 수로 추정한 호출이 있으면 `estimated`가 참이다.

`est_cost_usd`와 `est_cost_krw`는 사용한 토큰에 공개 API 단가를 적용한 추정 금액이다. 단가를 모르면 두 값은 null이다. 단가를 확인한 모델 한 종류로 집계했을 때 `priced_as`에 그 모델 ID가 들어간다. `GET /api/runs/{id}`의 기존 `usage`는 전체 경과 시간 `elapsed_s`, 호출 수, 토큰과 추정 금액을 제공한다. 동시에 실행한 호출의 시간은 겹칠 수 있다.

Codex의 `input_tokens`는 실행기가 덧붙인 지침을 포함한 원래 수치다. `cost_basis="direct_api_uncached_estimate"`이면 직접 보낼 지침·질문·응답 형식의 UTF-8 크기로 `cost_input_tokens`를 어림하고 실제 출력 토큰을 더해 비용을 계산한다. 화면·보고서에 쓸 문구는 “앱이 보낼 입력 크기와 실제 출력량으로 어림한 금액이에요. 첫 호출 기준으로 캐시 할인은 적용하지 않았어요.”다. 이 경우 `estimated`는 참이고, 실측 출력량이나 단가가 없으면 비용은 null이다. 응답기의 토큰을 그대로 써서 계산하는 경우는 `adapter_usage`, 두 방식이 섞이면 `mixed`다. 이 표시는 수집기의 `summary()`와 `by_model`에 있다.

## 대화의 한 차례 (지시서 34)

- `POST /api/chat`은 대화마다 한 차례를 실행하고 기존 UI 메시지 스트림을 돌려준다. 응답 연결이 끊겨도 서버가 차례를 끝내고 메시지와 기획 노트를 함께 저장한다. 같은 대화의 차례가 실행 중이면 새 요청은 409다. 다른 대화는 동시에 진행할 수 있다.
- `GET /api/chats/{id}`에 선택 항목 `working: boolean`을 더한다. 참이면 마지막 메시지는 그때까지 모인 칠성이의 응답이다. 메시지 ID와 파트 형식은 저장된 응답과 같다. 다시 연 화면은 2초마다 조회해 메시지와 작업대를 갱신하고, 거짓이면 완료된 응답을 표시한다.
- `POST /api/chats/{id}/stop`은 진행 중인 차례를 멈추고, 그때까지의 응답에 `metadata.stopped: true`를 붙여 저장하고 기획 노트를 차례 앞으로 되돌린다. 저장을 마쳤거나 진행 중인 차례가 없으면 200과 `{"ok": true}`를 돌려준다.
- 서버를 다시 시작하면 마지막으로 저장한 차례부터 이어간다. 실행 중인 차례의 중간 결과는 메모리에 둔다.

## 신뢰도 점수표 (지시서 35)

`app/server/store/reliability/<판>.json`은 한 판의 측정 결과다. `version`, `measured_at`(마지막 호출 시각, UTC), `llm`, `models.shopper`(예: `gpt-6.2-sol/low`), `metrics`, `caveats`를 담는다. 일부 지표만 끝난 판에는 끝난 지표만 들어간다. W6은 배열의 `id`로 지표를 찾고, 없는 지표는 “아직 측정하지 않았어요”로 표시한다.

| `metrics[].id` | 주요 필드와 단위 |
|---|---|
| `retest` | `value`, `low`, `high`는 같은 선택의 비율과 윌슨 95% 구간(0~1), `n`은 유효한 짝 수, `threshold`는 0.70. `detail.same_product`와 `both_no_purchase`로 실제 상품 일치와 비구매 일치를 나눈다. |
| `direction` | `detail.price[]`에 원 단위 가격과 선택 인원·분모. `price_endpoints`와 `promo`에 짝별 증가·감소 인원, 양측 맥니마 `p`, 선택률 차이와 구간(0~1 척도). `promo.on/off`는 행사 유무별 선택 인원이다. `survey_wtp[]`는 가격별 지불의향 비율을 담는다. |
| `sales_rank` | `value`는 순위 상관, `gap`은 어긋난 정도(%p), `n_products`는 매대와 편의점 판매에서 맞춘 제품 수. `detail.calibrated`는 보정 뒤 결과, `detail.floor`는 실제 판매의 앞·뒤 12개월 비교다. |
| `survey_match` | `detail.concepts[]`에 컨셉별 `name`, 순위 상관 `rho`, 95% 구간 `low/high`, 비교한 칸 수 `cells`, 모집단 가중 선택률 `rate`(0~1). `detail.order.survey/virtual`은 높은 순서의 이름 배열, `same`은 엄격한 순서 일치 여부다. |

각 지표는 `name`, `passed`, `detail.usage`를 갖는다. 상관을 정의할 수 없거나 비용을 산정할 수 없으면 해당 값은 null이다. `usage.calls`는 전송 시도 수, `elapsed_s`는 동시에 진행한 구간을 한 번만 센 실행 초, `est_cost_usd`는 모든 호출의 비용용 토큰을 확인한 경우의 추정 달러다. 일부 호출의 출력이 빠지면 `known_cost_usd`에 확인한 금액, `completed_est_cost_usd`에 확인한 단가로 유효 응답의 누락분을 보충한 추정액을 적는다. `unpriced_calls`로 비용을 확인하지 못한 호출 수를 확인한다.

선택이 드물 때 따로 실행한 확인은 최상위 `checks[]`에 둔다. 각 조건의 `n`, `picked`, `non_picks`는 응답·선택·비선택 인원이고 `barriers`는 걸린 점별 응답 인원이다(복수 응답). `barrier_responses`는 사유 항목을 보관한 비선택 응답 수다. 확인 결과는 공식 네 지표의 통과 판정에 사용하지 않는다.

중립 컨셉을 따로 측정한 판은 최상위 `neutral_direction`에 제품명·규격과 세 조건에 모두 응답한 인원 `n`을 기록한다. `price.on/off`는 낮은 가격과 높은 가격에서의 선택 인원, `promo.on/off`는 같은 가격에서의 행사·무행사 선택 인원이다. 각각 짝별 증가·감소 수, 선택률 차이·구간과 맥니마 p값을 포함한다.

방문 달을 적용한 실행은 `GET /api/runs/{id}`에 선택 필드 `visit_months`를 돌려준다. `eligible`은 판매 기간에 해당하는 달의 배열(예: `[5,6,7,8,9]`), `used`는 실제 배정한 달의 배열이다. 화면 문구는 “판매 시기(5~9월)의 방문으로 물었어요”다. ③의 `detail.category_fit.seasonality`에는 매칭 제품 중 월별 탄산 선택·판매 비중, 여름과 겨울의 차이, 비교한 달 수와 월별 순위 상관을 담는다.


구매 여정을 묻는 10차에서 컨셉 응답이 있으면 매대 결과에 선택 필드 `journey`가 생긴다. `source=simulated`, `visits`, `noticed`, `considered`, `purchased`는 유효 방문 수와 그중 해당 신제품을 발견·비교·구매한 수다. `purchased_per_visit`, `purchased_per_noticed`, `purchased_per_considered`는 각 분모의 구매 비율(0~1, 분모 0이면 null)이다. `feedback_missing`은 비교한 사람의 후속 소감 수집 실패 수다. 10차 신뢰도 점수표의 컨셉 지표는 조건별로 같은 집계를 `detail.journeys`에 담는다.

## W6 추가 (v1.22): 후속 개선과 가상 매출

참가자가 정했다(11-24 밤): 실제 조사는 타깃만 한다. 결과 보고서 다음 단계 `followup`("후속 개선")에서 같은 대화에 조사 엑셀을 올려 지금의 컨셉을 고친다. 흐름은 조사 확인 → 가상 소비자 맞추기 → 다시 테스트 → 개선안 → 컨셉 수정. 견본은 `/proto/w6`.

### 단계와 카드

- `StageId`의 맨 끝에 `followup`, `PART_STAGES.test`의 맨 끝에도 `followup`. `CardKind`에 `followup`(단계 `followup`, 카드 id `followup`).
- 후속 개선의 버튼 묶음은 `actions`의 id가 `followup`이고 버튼의 id가 `"apply:<upload_id>"` 꼴이다(버튼은 id 하나만 보내므로). 서버는 `["apply", upload_id]`와 `["apply:<upload_id>"]`를 모두 받는다. 개선안 뒤의 버튼은 지금의 `improve-all`, `report`다.
- 결과 보고서의 말 뒤 버튼에 `upload-survey`("조사 결과 올리기")가 더해진다. 화면은 이 버튼을 누르면 파일 고르기를 열고, 대화창에 파일을 끌어다 놓아도 같은 일을 한다.

### 올리기

`POST /api/followup/upload` 본문 `{chat_id, filename, content_base64}`(8MB까지, .xlsx). 답 `{upload_id}`. 형식이 다르거나 테스트한 컨셉의 조사가 아니면 422와 `detail`(해요체 한 문장). 화면은 성공하면 기획자의 말 "조사 결과 올리기"를 `metadata.reply = {to: "followup", ids: ["upload", upload_id]}`로 보낸다. 올린 파일과 정제본은 `store/followup/<upload_id>/`에만 둔다(커밋되지 않는다).

### 칠성이에게 보내는 답

`metadata.reply.to = "followup"`. `ids`: `["upload", id]` 조사 확인, `["apply", id]` 맞추기, `["retest", id]` 다시 테스트, `["retest-result", id]` 다시 테스트의 결과, `["ideas", id]` 개선안. 개선안의 테스트와 채택은 지금의 `improve`, `w7-adopt` 길이다.

### 카드 `followup`의 payload

```ts
type FollowupPayload = {
  upload_id: string
  step: "diff" | "applied" | "retest" | "ideas"
  concept: { id: string; name: string; price: number }
  target: string                      // "20대"
  n: { raw: number; clean: number; target: number }
  removed: { label: string; count: number }[]
  diffs: { id: "price" | "worry" | "hope"; text: string; actual: number; actual_n: number   // 백분율, 응답 수
           virtual: number | null; virtual_n: number | null }[]   // 가상 소비자에게서 센 값. 없으면 null
  note: string                        // 두 값을 어디서 셌는지 한 줄
  curve: { price: number; share: number; money: number }[]        // 낼 수 있는 비율(%), 100명 기준 금액(원)
  best_price: number | null
  opinions: { good: Opinion[]; bad: Opinion[] }                   // Opinion = { text: string; n: number; intent: number }  (intent: 구매 의향 %)
  track: { total: number; original: number | null; retest: number | null; improved: number | null }
  base_run: string                    // 처음 테스트
  retest_run: string | null
  can_retest: boolean                 // 가상 소비자의 글에 조사 답을 끼우는 길이 이어졌는지
}
```

`GET /api/followup/{upload_id}/people` → `{status, total, asked, before: {n, picked}, after: {n, picked}, people: [{id, who, lines: string[], before: boolean, after: boolean | null, said: string}]}`. `lines`는 그 가상 소비자에게 더한 조사 답, `said`는 마지막으로 한 말. `after`는 아직 답하지 않았으면 null. 이름과 소비자 고유번호(uuid)는 내보내지 않는다. 없는 id면 404.

`status`는 다시 테스트의 상태(`running`, `done`, `stopped`, `failed`)이고, 그 전에는 올린 뒤 `ready`, 맞춘 뒤 `applied`다.

`GET /api/followup/{upload_id}` → 카드 payload의 지금 값(다시 테스트나 개선안이 끝난 뒤의 `track`). 없는 id면 404. 카드의 payload는 그 차례에 박힌 값이다. `track.improved`는 이 조사에서 나온 안 가운데 채택한 안, 없으면 끝난 안의 가장 많은 선택이다.

카드 `improve`에 없어도 되는 칸 `focus_id`: 카드를 열면 먼저 보일 안. 마지막으로 올린 조사에서 나온 첫 안이고, 그 조사의 안을 채택했으면 없다. 안의 차례와 이름은 바뀌지 않는다.

조사를 더한 결과는 조사와 독립이 아니다. 화면과 보고서에서 "조사를 반영해 다시 물은 결과"라 부르고 처음 결과와 나란히 둔다. 더하는 칸: 낼 수 있는 가격(`wtp`), 의견의 갈래(`comment`에서). 더하지 않고 확인에만 쓰는 칸: 구매의향(`intent`). 평소 습관(월 구매 횟수)은 W0의 `calibrate/habits.py`가 다룬다.

### 조사 답을 가상 소비자에게 더하기

`calibrate/overlay.py`: `build(upload_id, people) -> None`(타깃 안에서 성별을 맞추고 조사 가중치의 비율대로 나눠 준다. 씨앗 고정), `lines(upload_id, uuid) -> list[str]`(더할 사실의 줄. 컨셉을 올린 매대의 글에만 끼운다). 글에 끼우는 곳은 총지휘가 잇는다: `runner.Spec.overlay`, `meta["overlay"]`.

### 가상 매출

`calibrate.sales.estimate(concept, result) -> dict | None`. 모양은 지시서 28과 `chat/contract-improve.ts`의 `ImproveSales`. 보고서의 `evidence.compare`는 `agent/proposal_compare.py`의 `add(note, concept, test)`가 채운다.

## 칠성이의 아이디어 사양 (11-25)

- 칠성이가 스스로 낸 아이디어(`by: "chilseong"`)도 지시서 33의 칸을 싣는다: `variants`(한 개: 용량, `price` 권장 소비자가, `shelf_life_months`, `kcal`), `shelf_variant: 0`, `launch`, `season`, `channels`. 출고가(`factory_price`)는 내지 않는다. 형식은 지시서 33과 같아 화면은 바뀌지 않는다.
- 모델이 제안한 값은 서버가 다듬는다(`agent/idea_spec.proposed_spec`): 용량은 매대에 있는 같은 용기의 가장 가까운 용량(자료가 없는 용기는 190, 250, 355, 500), 가격은 100원 단위로 같은 용기(없으면 매대 전체)의 가격 범위 안, 유통기한 1~24개월, 열량 0~용량의 0.8배, `launch`는 오늘보다 뒤의 `YYYY-MM`, `season`은 달의 숫자가 있을 때만, `channels`는 편의점·대형마트·SSM·온라인 가운데(편의점은 늘). 벗어난 칸은 비운다.
- 이 아이디어로 만든 컨셉은 사양을 물려받고, 매대 테스트로 넘어가는 가격은 아이디어의 권장 소비자가다. 옛 아이디어(칸이 없는 것)는 지금처럼 보인다.

## 컨셉의 예시 이미지 (11-25)

- 기획자가 누를 때만 만든다(자동으로 만들지 않는다). 그림은 예시이고 화면에 "예시 이미지예요. 실제 패키지와 달라요."를 붙인다.
- `POST /api/chats/{chat_id}/concepts/{concept_id}/image` 본문 `{"again": bool}`(없으면 false): 만들어 저장하고 `{status: "ready", url, version}`. 이미 있으면 `again`이 아닐 때 있는 것을 준다. 같은 컨셉에 도는 요청이 있으면 그것을 기다린다. 시간 제한 150초. 뒷단이 꺼졌거나 지원하지 않으면 409, 실패(시간 초과, 뒷단 오류)는 502. 둘 다 `detail`에 사람이 읽을 까닭.
- `GET …/image`: 저장된 PNG(없으면 404). `GET …/image/status`: `{status: "none"|"working"|"ready"|"unavailable", url?, version?}`. `url`에는 `?v={version}`이 붙어 다시 만들면 바뀐다.
- id는 `[A-Za-z0-9_-]{1,64}`만 받는다. 저장은 `server/store/images/{chat_id}/{concept_id}.png`와 옆의 `.json`(만든 시각, 시킨 글, 뒷단, 걸린 초, 판).
- 뒷단은 `AX_IMAGE`(fake|codex|openai|off), 없으면 `AX_LLM`을 따른다(codex→codex, openai→openai, fake→fake, cli→off). openai는 `{OPENAI_BASE_URL}/images/generations`, 모델은 `AX_MODEL_IMAGE`(기본 `gpt-image-1`).
- 시키는 글은 코드가 정해진 영어 낱말로만 만든다(`server/imagegen/prompt.py`): 제품 종류, 매대에 올릴 규격의 용기와 용량, 맛의 재료, 좋은 점의 시각 단서, 그리고 "no text, no logo, no trademark". 컨셉의 글과 브랜드 이름은 넣지 않는다.
- 화면: `components/concept/ConceptImage.tsx`의 `ConceptImage({ chatId, conceptId, placeholder })`. `placeholder`는 지금의 그림 자리(빈 면)다. 상태만 그리는 `ConceptImageView`는 `/design`에 있다.

## 도는 테스트의 view (11-25)

`GET /api/runs/{id}`의 status가 `running`이면 `waiting` 칸이 더 온다. 끝난 테스트와 옛 서버에는 없다(화면은 없으면 `asked`/`total`로 그린다). 숫자는 모두 서버가 쌓인 답에서 센다(`server/shelftest/waiting.py`). 화면의 형식은 `web/src/chat/contract-shelf.ts`의 `RunWaiting`.

| 칸 | 뜻 |
|---|---|
| `mode` | `target` / `explore` / `improve`. 남은 시간을 모를 때의 어림을 고른다 |
| `steps_done`, `steps_total` | 남은 일. 한 손님에게 두 매대(컨셉이 있는 매대, 없는 매대)를 물으므로 `steps_total = 2 × total`. 답 하나가 한 걸음이고 저장해 둔 답을 다시 쓴 것도 든다. 빠진 손님은 두 걸음으로 센다. 진행 막대는 이것을 따른다 |
| `visited` | 컨셉이 있는 매대의 답이 온 손님 수("N명이 다녀갔어요") |
| `complete` | 두 매대의 답이 모두 온 손님 수 |
| `eta_s` | 남은 초. 최근 90초(모자라면 최근 40개)의 새 답(다시 쓴 답 제외)의 속도로 계산한다. 새 답이 6개 미만이면 `null` |
| `lead` | 지금까지의 한 줄. 탐색은 `{kind:"group", age:"50대", sex:"여자", picked, n}`(모든 칸이 10명 이상이고 1위가 하나일 때만), 타깃은 `{kind:"target", picked, n, name}`(30명 이상일 때만). 아니면 `null` |
| `recent` | 방금 다녀간 손님(최근 6명, 최근 것부터). 컨셉이 있는 매대의 답에서만: `{visit, age:"20대", sex, occasion, chose, said, ours}`. `said`는 그 답의 `sentence`(고른 까닭) 그대로 120자까지, 이름이 든 말은 빈 글. 손님의 uuid와 이름은 내보내지 않는다 |

## 컨셉 보드 분석 (11-25)

- 화면의 이름 "테스트 전 진단"을 "컨셉 보드 분석"으로 바꾼다. 카드는 그대로 `kind: "diagnosis"`, `stage: "concept"`이고 제목만 `"컨셉 보드 분석"`이다.
- 화면에서만 1부의 세 번째 단계 `analysis`가 있다(`아이디어 회의 → 컨셉 보드 → 컨셉 보드 분석`). 서버는 `analysis`를 보내지도 받지도 않는다: 화면이 `diagnosis` 카드를 `analysis`에 두고, 서버의 단계가 `concept`인데 이 카드가 와 있으면 지금 단계를 `analysis`로 읽는다.
- payload의 구역에 없어도 되는 칸을 더한다(옛 payload는 없이 그려진다): 트렌드 `series: [{month, search_index}]`(트렌드 조사 카드와 같은 달별 값), 가격 `points: [{name, price}]`(같은 용기·용량 타사 1개입, 값 순), 비슷한 과거 사례 `rows: [{name, year, status, reasons}]`(`reasons`는 사유의 묶음 이름, 사유가 비었으면 null, 단종·개발 중단이 아니면 null), 유통 `storage`(상온|냉장|냉동).
