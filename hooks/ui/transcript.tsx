// The run's transcript, drawn in the pane body (not in a Client) so the engine scrolls it with the wheel,
// the arrow keys and Page Up/Down, like a terminal. Every row carries what the agent reported: messages
// wrap in full, tool calls and results expand to their whole input or output, edits to their diff.
import type { EventView, RunView } from './stage.tsx'

export type TranscriptAction =
  | { type: 'toggle'; key: string }
  | { type: 'earlier' }

const ACCENT = '#D97757'
const DIM_LINE = 90 // most characters of one detail line shown
const MAX_DETAIL_LINES = 80
export const FIRST_PAGE = 120 // newest events drawn at first; "earlier" adds a page
export const PAGE = 120

/** The key a row's expanded state is stored under: unique across runs. */
export const rowKey = (runId: string, seq: number) => `${runId}:${seq}`

/** Follow-latest rule: the window follows new output only while the person has not scrolled up.
 *  `offset` is the first row the window will show, `bodyRows` how many it shows, `contentRows` how many exist. */
export function followsLatest(offset: number, bodyRows: number, contentRows: number): boolean {
  return contentRows <= bodyRows || offset + bodyRows >= contentRows - 1
}

const lines = (s: string | undefined) => (s ?? '').split('\n').map(l => l.replace(/\s+$/, '')).filter((l, i, a) => l || (i > 0 && i < a.length - 1))

export type TranscriptView = {
  run: RunView
  feed: EventView[]
  partial: string
  open: ReadonlySet<string>
  shown: number
  colour: string
  spin: string
}

const elapsed = (s: number) => (s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`)

/** One expandable detail block: collapsed it is a single dim line, expanded it is every line, diffs coloured. */
function detailBlock(el: any, ev: EventView, expanded: boolean, rk: string, act: (a: TranscriptAction) => void, diff: boolean) {
  const { Box, Text, Button } = el
  const all = lines(ev.detail)
  if (!all.length) return null
  const more = all.length > 1 || (all[0]?.length ?? 0) > DIM_LINE
  if (!expanded) {
    return (
      <Box key={`d${ev.seq}`} flexDirection="row" columnGap={1}>
        <Text dimColor wrap="truncate-end">  ⎿  {all[0]}</Text>
        {more ? <Button key={`x:${rk}`} label={`▸ ${all.length > 1 ? `${all.length} lines` : 'more'}`} plain onPress={() => act({ type: 'toggle', key: rk })} /> : null}
      </Box>
    )
  }
  return (
    <Box key={`d${ev.seq}`} flexDirection="column">
      <Box flexDirection="row" columnGap={1}>
        <Text dimColor>  ⎿</Text>
        <Button key={`x:${rk}`} label="▾ collapse" plain onPress={() => act({ type: 'toggle', key: rk })} />
      </Box>
      {all.slice(0, MAX_DETAIL_LINES).map((l, i) => {
        const colour = diff ? (l.startsWith('+') ? '#9ECE6A' : l.startsWith('-') ? '#F7768E' : undefined) : undefined
        return <Text key={`l${ev.seq}-${i}`} wrap="wrap" dimColor={!colour} color={colour}>    {l}</Text>
      })}
      {all.length > MAX_DETAIL_LINES ? <Text dimColor>    … {all.length - MAX_DETAIL_LINES} more lines</Text> : null}
    </Box>
  )
}

function row(el: any, ev: EventView, t: TranscriptView, act: (a: TranscriptAction) => void) {
  const { Box, Text } = el
  const rk = rowKey(t.run.id, ev.seq)
  const expanded = t.open.has(rk)
  const key = `e${ev.seq}`
  switch (ev.kind) {
    case 'you':
      return <Text key={key} wrap="wrap"><Text color={ACCENT} bold>&gt; </Text><Text color="#F5E0DC">{ev.text}</Text></Text>
    case 'message':
      return <Text key={key} wrap="wrap"><Text color="#CDD6F4">⏺ </Text><Text color="#CDD6F4">{ev.text}</Text></Text>
    case 'thinking':
      return <Text key={key} wrap="wrap" dimColor italic>  ✻ {ev.text}</Text>
    case 'tool':
      return (
        <Box key={key} flexDirection="column">
          <Text wrap="wrap"><Text color={t.colour}>⏺ </Text><Text bold>{ev.text}</Text></Text>
          {detailBlock(el, ev, expanded, rk, act, false)}
        </Box>
      )
    case 'result':
      return (
        <Box key={key} flexDirection="column">
          <Text wrap="wrap" dimColor>  ⎿  {ev.text}</Text>
          {detailBlock(el, ev, expanded, rk, act, false)}
        </Box>
      )
    case 'edit':
      return (
        <Box key={key} flexDirection="column">
          <Text wrap="wrap"><Text color="#9ECE6A">⏺ </Text><Text color="#9ECE6A">{ev.text}</Text></Text>
          {detailBlock(el, ev, expanded, rk, act, true)}
        </Box>
      )
    case 'plan':
      return <Text key={key} wrap="wrap"><Text color="#E0AF68">☰ </Text><Text dimColor>{ev.text.replace(/\n/g, '  ')}</Text></Text>
    case 'error':
      return <Text key={key} wrap="wrap" color="#F7768E">✗ {ev.text}</Text>
    case 'warning':
      return <Text key={key} wrap="wrap" color="#E0AF68">! {ev.text}</Text>
    case 'approval':
    case 'needs-you':
      return (
        <Box key={key} flexDirection="column">
          <Text wrap="wrap" color="#E0AF68">⚑ {ev.text}</Text>
          {detailBlock(el, ev, expanded, rk, act, false)}
        </Box>
      )
    default:
      return (
        <Box key={key} flexDirection="column">
          <Text wrap="wrap" dimColor>· {ev.text}</Text>
          {detailBlock(el, ev, expanded, rk, act, false)}
        </Box>
      )
  }
}

/** The transcript: older rows on top, the live line last. Pure, so it can be drawn by the pane or a test. */
export function drawTranscript(el: any, t: TranscriptView, act: (a: TranscriptAction) => void) {
  const { Box, Text, Button } = el
  const total = t.feed.length
  const from = Math.max(0, total - Math.max(1, t.shown))
  const rows = t.feed.slice(from)
  const running = t.run.status === 'running' || t.run.status === 'starting'
  const word = `${t.run.activity.charAt(0).toUpperCase()}${t.run.activity.slice(1)}…`.slice(0, 80)
  const live = t.partial.trim()
  return (
    <Box key="transcript" flexDirection="column" paddingX={1}>
      {from > 0 ? (
        <Box key="earlier" flexDirection="row">
          <Button key="earlier-btn" label={`↑ ${from} earlier event${from === 1 ? '' : 's'}`} plain onPress={() => act({ type: 'earlier' })} />
        </Box>
      ) : null}
      {rows.map(ev => row(el, ev, t, act))}
      {running && live ? <Text key="live" wrap="wrap"><Text color={ACCENT}>{t.spin} </Text><Text color="#CDD6F4">{live}</Text></Text> : null}
      {running && !live ? (
        <Text key="working"><Text color={ACCENT}>{t.spin} </Text><Text dimColor>{word}  {elapsed(t.run.elapsed_s)}</Text></Text>
      ) : null}
    </Box>
  )
}
