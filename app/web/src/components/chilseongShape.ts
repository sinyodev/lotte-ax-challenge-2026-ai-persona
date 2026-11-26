import type { AvatarDefinition } from "open-bot-avatar"

/**
 * 칠성이의 모양: 통통한 캔. open-bot-avatar(MIT)의 정의 형식(윤곽선 하나와 눈의 위치)이다.
 * 색은 여기에 없다. 테마의 --color-chilseong을 쓴다.
 */
export const chilseongShape: AvatarDefinition = {
  version: 1,
  id: "chilseong",
  name: "Chilseong",
  body: {
    path: "M34 14H66Q70 14 71 18Q80 21 80 31V73Q80 82 71 85Q70 89 66 89H34Q30 89 29 85Q20 82 20 73V31Q20 21 29 18Q30 14 34 14Z",
  },
  eyes: { x: 50, y: 46, spacing: 18, scale: 1.2 },
}
