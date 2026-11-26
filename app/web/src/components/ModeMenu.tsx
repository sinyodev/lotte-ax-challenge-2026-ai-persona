import { AdjustmentsHorizontalIcon } from "@heroicons/react/24/outline"
import { Icon } from "@astryxdesign/core/Icon"
import {
  DropdownMenu,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "@astryxdesign/core/DropdownMenu"
import { copy, type ModeValue } from "../copy"

type Props = {
  value: ModeValue
  onChange: (value: ModeValue) => void
  /** 견본 페이지에서 펼친 모습을 보이려고 쓴다. */
  isMenuOpen?: boolean
  onOpenChange?: (isOpen: boolean) => void
  /** 입력창 안에서는 위로 펼친다. */
  placement?: "above" | "below"
}

/** 진행 방식 버튼. 지금 고른 방식의 이름을 보여 주고, 누르면 세 가지가 이름과 설명으로 펼쳐진다. */
export function ModeMenu({ value, onChange, isMenuOpen, onOpenChange, placement = "above" }: Props) {
  const current = copy.mode.options.find((o) => o.value === value) ?? copy.mode.options[1]
  return (
    <DropdownMenu
      button={{
        label: current.label,
        variant: "secondary",
        size: "lg",
        icon: <Icon icon={AdjustmentsHorizontalIcon} />,
        tooltip: copy.mode.label,
      }}
      placement={placement}
      menuWidth={320}
      isMenuOpen={isMenuOpen}
      onOpenChange={onOpenChange}
    >
      <DropdownMenuRadioGroup
        label={copy.mode.label}
        value={value}
        onChange={(v) => onChange(v as ModeValue)}
      >
        {copy.mode.options.map((o) => (
          <DropdownMenuRadioItem key={o.value} value={o.value} label={o.label} description={o.description} />
        ))}
      </DropdownMenuRadioGroup>
    </DropdownMenu>
  )
}
