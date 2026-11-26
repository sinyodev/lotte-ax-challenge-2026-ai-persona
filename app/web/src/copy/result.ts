/**
 * 지시서 32의 A: 테스트 결과 카드의 요약 구역과 "자세히"의 글. 요약 구역의 문장(알게 된 것, 근거, 까닭, 버튼의 말)은 서버가 보낸다.
 * 이 카드 안에서 사람 수의 주어는 "가상 소비자"다("손님"과 섞지 않는다).
 */
const count = new Intl.NumberFormat("ko-KR")

export const resultCopy = {
  next: "다음 행동", // 임시
  details: "자세히 보기", // 임시
  more: (n: number) => `${count.format(n)}개 더 보기`, // 임시
  less: "접기", // 임시
  records: "테스트 기록",
  barLabel: (label: string, n: number) => `${label} ${count.format(n)}명`, // 임시: 막대의 이름(화면 읽기용)
  asked: (who: string, n: number) => `${who} ${count.format(n)}명에게 물었어요`,
  skipped: (n: number) => `답이 맞지 않아 ${count.format(n)}명은 뺐어요.`, // 임시
}
