import type { SVGProps } from "react"
import type { Container } from "../fixtures/confirmedConcepts"

/** 용기 아이콘. 선은 글씨 색(currentColor)을 따른다. Icon의 icon 자리에 SVG 부품으로 넘긴다. */
function CanIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" {...props}>
      <path d="M8 3.5h8l1 2v13l-1 2H8l-1-2v-13z" />
      <path d="M7 6.5h10M7 17.5h10" />
    </svg>
  )
}
function PetIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" {...props}>
      <path d="M10 2.5h4v2.5l2.5 3.5v12a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1v-12L10 5z" />
      <path d="M7.5 12h9M7.5 16h9" />
    </svg>
  )
}
function BottleIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" {...props}>
      <path d="M10.5 2.5h3v4l2 3v11a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-11l2-3z" />
    </svg>
  )
}

export const CONTAINER_ICONS: Record<Container, (p: SVGProps<SVGSVGElement>) => React.JSX.Element> = {
  can: CanIcon,
  pet: PetIcon,
  bottle: BottleIcon,
}
