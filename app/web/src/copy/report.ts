/**
 * 지시서 32의 B: 결과 보고서 종이의 칸 이름. 칸 안의 문장은 서버가 보고서체로 보낸 그대로 쓴다.
 * 종이 안은 보고서체(명사형). "전환", "유입", "신규 수요", "점유", "구매"를 쓰지 않는다.
 */
const count = new Intl.NumberFormat("ko-KR")
const decimal = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 })

export const reportCopy = {
  recommend: "권고",
  decisions: "결정 요청",
  key: "핵심 수치",
  limits: "한계",
  opinion: "기획자 의견",
  opinionPlaceholder: "검토 의견을 적어 주세요. 적은 내용은 인쇄와 복사에 함께 실려요.", // 임시
  opinionEmpty: "(기재 없음)", // 임시: 복사한 마크다운에서 의견이 비었을 때
  opinionSaved: "저장했어요", // 임시
  opinionFailed: "저장하지 못했어요", // 임시
  circled: (n: number) => "①②③④⑤⑥⑦⑧⑨"[n - 1] ?? `${n}.`,
  evidence: "근거",
  sections: {
    who: "선택한 소비자",
    from: "평소 선택하던 제품",
    barriers: "비선택 사유",
    variants: "개선안 비교",
    voices: "소비자 반응",
  },
  whoHead: { label: "집단", n: "응답", picked: "선택", rate: "선택률" },
  fromHead: { label: "구분", n: "인원", top: "많이 선택하던 제품" },
  barrierHead: { label: "사유", n: "인원" },
  next: "다음 실제 조사의 조건",
  nextParts: { target: "권하는 타깃과 인원", questions: "물을 문항", conditions: "지킬 조건", unknowns: "이 테스트로 알 수 없는 것" },
  appendix: "부록",
  appendixParts: { method: "방법", records: "실행 기록", overview: "제품 개요(컨셉 보드)", rules: "권고의 규칙" },
  people: (n: number) => `${count.format(n)}명`,
  rate: (r: number | null) => (r == null ? "-" : `${decimal.format(r)}%`),
  topItem: (name: string, n: number) => `${name}(${count.format(n)}명)`,
  quote: (said: string, who: string | null) => (who ? `"${said}" (${who})` : `"${said}"`),
  numbered: (n: number, title: string) => `${n}. ${title}`,
}
