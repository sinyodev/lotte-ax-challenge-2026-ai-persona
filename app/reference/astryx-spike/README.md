# Astryx 시험 앱 (참고용)

2026-11-19에 임시 폴더에서 돌려 본 시험 앱의 핵심 파일이다. 그대로 실행되는 앱이 아니라 구현 세션이 읽는 참고 자료다(node_modules, 받아 온 부품 소스, 만들어진 테마 CSS는 넣지 않았다).

- `src/App.tsx`: 단계 표시줄, Astryx 대화 부품으로 그린 대화와 질문 카드, 작업대 숫자 카드. `useChat`의 메시지를 Astryx 부품에 잇는 코드가 여기 있다.
- `src/index.css`: 레이어 순서 한 줄과 Astryx CSS를 불러오는 순서. shadcn과 Agent Elements를 불러오는 줄은 시험의 흔적이니 새 앱에는 넣지 않는다.
- `lotte.settings.ts`, `lotte.theme.ts`, `palette.config.json`: 테마 편집기(`astryx experimental theme editor`)가 만든 롯데 레드 테마의 설정.
- `server/main.py`: AI SDK의 UI 메시지 스트림으로 말과 질문을 내보내는 FastAPI 시험 서버.
- `pnpm-workspace.yaml`: pnpm 11에서 Astryx의 설치 뒤 스크립트를 막지 않게 하는 설정.
