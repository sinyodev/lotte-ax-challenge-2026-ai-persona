import { ArrowDownIcon, ArrowUpIcon } from "@heroicons/react/20/solid"
import { DropdownMenu, DropdownMenuDivider, DropdownMenuRadioGroup, DropdownMenuRadioItem } from "@astryxdesign/core/DropdownMenu"
import { ideasCopy as c } from "../../copy/ideas"

export type OwnerOrder = "ownerAsc" | "ownerDesc"

export function IdeaOwnerMenu({ owners, filter, order, onFilter, onOrder }: {
  owners: string[]
  filter: string
  order?: OwnerOrder
  onFilter: (value: string) => void
  onOrder: (value: OwnerOrder) => void
}) {
  const current = filter === "unassigned" ? c.noOwner : filter.slice("owner:".length)
  const label = filter === "all" ? c.fields.owner : c.filteredOwner(current)
  const OrderIcon = order === "ownerAsc" ? ArrowUpIcon : ArrowDownIcon
  return <DropdownMenu button={{
    label,
    "aria-label": c.ownerMenu(label),
    icon: order ? <OrderIcon width={14} aria-hidden="true"/> : undefined,
    variant: "ghost",
    size: "sm",
  }}>
    <DropdownMenuRadioGroup label={c.ownerSort} value={order}
      onChange={value => onOrder(value === "ownerAsc" ? "ownerAsc" : "ownerDesc")}>
      <DropdownMenuRadioItem value="ownerAsc" label={c.ownerAsc}/>
      <DropdownMenuRadioItem value="ownerDesc" label={c.ownerDesc}/>
    </DropdownMenuRadioGroup>
    <DropdownMenuDivider/>
    <DropdownMenuRadioGroup label={c.ownerFilter} value={filter} onChange={onFilter}>
      <DropdownMenuRadioItem value="all" label={c.ownerAny}/>
      <DropdownMenuRadioItem value="unassigned" label={c.noOwner}/>
      {owners.map(name => <DropdownMenuRadioItem key={name} value={"owner:" + name} label={name}/>)}
    </DropdownMenuRadioGroup>
  </DropdownMenu>
}
