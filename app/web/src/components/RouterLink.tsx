import type { ComponentProps, Ref } from "react"
import { Link } from "react-router"

/** Astryx의 링크(LinkProvider)가 react-router로 주소를 바꾸게 잇는 부품. */
type Props = Omit<ComponentProps<"a">, "href"> & { href?: string; to?: string; ref?: Ref<HTMLAnchorElement> }

export function RouterLink({ href, to, ref, ...rest }: Props) {
  return <Link ref={ref} to={to ?? href ?? "/"} {...rest} />
}
