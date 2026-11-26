# lotte 테마

Astryx 테마 편집기(`astryx experimental theme editor`, CLI 0.7.16)로 만든 롯데 레드 테마다. neutral 위에 얹었다.

## 파일

| 파일 | 누가 쓰나 | 내용 |
|---|---|---|
| `lotte.settings.json` | 편집기 | 확인을 거친 설정 목록. **테마의 기준.** |
| `lotte.settings.ts`, `tokens/` | 편집기(매번 새로 만듦) | 설정에서 만든 소스 |
| `lotte.theme.ts` | 처음 한 번만 편집기, 그 뒤는 사람 | 설정 위에 손으로 덧붙이는 곳(지금은 비어 있음) |
| `lotte.css`, `lotte.js` | 편집기(매번 새로 만듦) | 빌드한 테마 |
| `overrides.css` | 사람 | 편집기로 안 되는 덮어쓰기. 색은 토큰으로만 쓴다 |
| `palette.config.json`, `lotte.history.json` | 편집기 | 색 계열 설정, 바꾼 기록 |
| `../../src/themes/lotte/` | 편집기(매번 새로 만듦) | 앱이 불러 쓰는 사본. 손으로 고치지 않는다 |
| `../../src/astryx-themes.ts` | `astryx theme add` | 앱이 테마를 불러오는 모듈 |

## 지금 들어 있는 설정

- 강조색 `#DA291C`. 선택 테두리(`--shadow-inset-selected`)와 강조 아이콘(`--color-icon-accent`)도 이 색
- 밝은 모드만(`light-only`), 앱도 `<Theme mode="light">`
- 글꼴 Pretendard Variable (글꼴 파일은 앱이 `pretendard` 패키지에서 직접 싣는다. `src/index.css`), 기본 글씨 15px(`text-size large`, 보조 글씨 13px)
- 면: 본문과 페이지 바탕은 흰색, 옅은 면(`--color-background-muted`) `#F7F7F8`, 보조 버튼 면(`--color-neutral`) `#F2F2F3`, 선 `#EBEBEB`
- 글씨: 거의 검정 `#111111`, 보조 글씨와 보조 아이콘 `#8E8E93`
- 모서리: 전체 `round`, 버튼과 칩(`token`)은 `pill`, 입력창 20px, 칠성이 자리(`card` red) 22px, 메뉴 판 16px, 최근 테스트 줄 12px, 메뉴 항목 10px
- 인사(`display-2`): 36px, 굵기 600, 줄 간격 1.15, 자간 -0.02em
- 왼쪽 메뉴: 화면 가장자리에서 8px 떨어진 옅은 회색 둥근 판. 안에서는 `--color-neutral`이 흰색이라 고른 항목과 새 테스트 버튼이 흰 면이 된다. 항목 글씨는 회색, 고른 항목만 거의 검정
- 추천 칩(`token` lg): 높이 44px, 흰 바탕에 1px 선, 좌우 18px, 올려놓으면 옅은 면
- 입력창(`chat-composer`): 넓고 옅은 그림자와 1px 선, 안쪽 여백 14px, 글 쓰는 자리 두 줄 높이, 보내기 버튼 36px
- `card`의 `red` 변형은 칠성이 자리 전용이다(롯데 레드 면에 흰 글씨)

편집기로 할 수 없는 것은 `overrides.css`에 둔다(지금은 메뉴 안 보조 버튼의 테두리와 높이 40px 하나). 앱이 `src/index.css`에서 불러온다.

## 처음부터 다시 만드는 명령

`app/web`에서 차례로 돌린다.

```bash
E() { pnpm exec astryx experimental theme editor "$@"; }
E new lotte --like neutral
E set lotte accent '#DA291C'
E set lotte mode light-only
E set lotte corners round
E set lotte corners pill --on button
E set lotte corners pill --on token
E set lotte --shadow-inset-selected 'inset 0px 0px 0px 2px #DA291C'
E set lotte font '"Pretendard Variable", Pretendard, sans-serif'
# 02: 글씨
E set lotte text-size large
E set lotte --text-display-2-size 2.25rem
E set lotte --text-display-2-leading 1.15
E set lotte --text-display-2-weight 'var(--font-weight-semibold)'
E set lotte letter-spacing -0.02em --on heading --when type:display-2
# 02: 색
E set lotte --color-border '#EBEBEB'
E set lotte --color-text-secondary '#8E8E93'
E set lotte --color-text-primary '#111111'
E set lotte --color-background-muted '#F7F7F8'
E set lotte --color-background-body '#FFFFFF'
E set lotte --color-neutral '#F2F2F3'
E set lotte --color-icon-secondary '#8E8E93'
E set lotte --color-icon-accent 'var(--color-accent)'
# 02: 왼쪽 메뉴
E set lotte padding 8px --on app-shell-sidenav
E set lotte background 'var(--color-background-muted)' --on side-nav
E set lotte border-radius 16px --on side-nav
E set lotte padding-inline 4px --on side-nav
E set lotte --color-neutral '#FFFFFF' --on side-nav
E set lotte border-radius 10px --on side-nav-item
E set lotte height 36px --on side-nav-item
E set lotte color 'var(--color-text-secondary)' --on side-nav-item
E set lotte color 'var(--color-text-primary)' --on side-nav-item --state selected
E set lotte border-radius 12px --on item
E set lotte background-color 'var(--color-background-surface)' --on item --state selected
E set lotte background-color 'var(--color-background-gray)' --on avatar-fallback
# 02: 추천 칩
E set lotte height 44px --on token --when size:lg
E set lotte padding-inline 18px --on token --when size:lg
E set lotte font-size 'var(--text-label-size)' --on token --when size:lg
E set lotte background-color 'var(--color-background-surface)' --on token
E set lotte box-shadow 'inset 0 0 0 1px var(--color-border)' --on token
E set lotte background-color 'var(--color-background-muted)' --on token --state hover
# 02: 입력창
E set lotte --shadow-low '0 10px 20px -12px rgb(0 0 0 / 10%), 0 1px 2px rgb(0 0 0 / 4%), inset 0 0 0 1px var(--color-border)' --on chat-composer
E set lotte --shadow-med '0 12px 24px -12px rgb(0 0 0 / 14%), 0 1px 2px rgb(0 0 0 / 5%), inset 0 0 0 1px var(--color-border)' --on chat-composer
E set lotte --radius-chat 20px --on chat-composer
E set lotte --spacing-3 14px --on chat-composer
E set lotte min-height 44px --on chat-composer-input
E set lotte --size-element-md 36px --on chat-send-button
# 02: 칠성이 자리
E set lotte background-color 'var(--color-accent)' --on card --when variant:red
E set lotte color 'var(--color-on-accent)' --on card --when variant:red
E set lotte border-radius 22px --on card --when variant:red
E set lotte box-shadow none --on card --when variant:red
pnpm exec astryx theme add lotte
```

`--color-text-secondary '#8E8E93'`는 흰 바탕에서 대비가 3.3:1이라 편집기가 4.5:1 미달로 알린다. 레퍼런스에 맞춘 지시서의 값이라 그대로 두었다.

## 바꾸는 법

- 하나를 바꿀 때: `pnpm exec astryx experimental theme editor set lotte <무엇> <값>`. 앱 사본까지 다시 만든다.
- 어떻게 바꾸는지 모를 때: `pnpm exec astryx experimental theme editor how "<하고 싶은 것>"` (영어로 묻는다)
- 되돌릴 때: `pnpm exec astryx experimental theme editor undo lotte`
- `lotte.theme.ts`를 손으로 고쳤으면: `pnpm exec astryx experimental theme compile themes/lotte/lotte.theme.ts`
- 눈으로 볼 때: `pnpm exec astryx experimental theme editor show lotte --png` 또는 앱의 `/design`
