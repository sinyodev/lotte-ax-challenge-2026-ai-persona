import type { ResultReport } from "../../chat/contract-shelf"

/** 화면과 인쇄에서 같은 개선안의 선택 비교와 채택 근거를 함께 읽는다. */
export function GroupPaper({ rows }: { rows: ResultReport["evidence"]["variants"] }) {
  return rows.map((row) => {
    if (!row.line) return null
    const [title, ...details] = row.line.split("\n")
    return (
      <div key={row.name} data-paper-next-part>
        <p data-paper-voice-factor>{title}</p>
        {details.length > 0 && (
          <ul data-paper-bullets>
            {details.map((line) => <li key={line}>{line}</li>)}
          </ul>
        )}
      </div>
    )
  })
}
