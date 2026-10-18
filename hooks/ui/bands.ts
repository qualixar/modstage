// The band above the prompt is shared: every mod that draws there asks the mods beneath it for their band first,
// then adds its own. Returning without `next(e)` hides every band beneath (0.0.14 did, so context-bar and
// token-weather drew nothing while ModStage was installed).
//
// The community convention (karanb192/awesome-claude-code-mods, "band mods"): a band is a Box keyed `band:<name>`,
// and a mod returns one column keyed `bands` that the next band mod unpacks, adds its own to, and returns again.
import type { RenderElement, RenderNode } from 'claude-code'

const COLUMN = 'bands'
const PREFIX = 'band:'

const isColumn = (el: RenderElement) => el.type === 'Box' && el.props?.key === COLUMN

/** Our band added below (nearest the prompt) whatever `rest` (what `next(e)` returned) already holds. */
export function stackBand(rest: RenderElement | null | undefined, name: string, mine: RenderNode): RenderElement {
  const own: RenderElement = { type: 'Box', props: { key: PREFIX + name, flexDirection: 'column' }, children: [mine] }
  const owner = rest?.part?.plugin
  // The engine stamps a returned column with its author: that stamp goes back on the author's own band.
  const stamp = (k: RenderNode): RenderNode =>
    owner && typeof k !== 'string' && k.props?.key === PREFIX + owner && !k.part ? { ...k, part: rest!.part } : k
  const others: RenderNode[] = !rest ? [] : isColumn(rest) ? (rest.children ?? []).map(stamp) : [rest]
  return { type: 'Box', props: { key: COLUMN, flexDirection: 'column' }, children: [...others, own] }
}
