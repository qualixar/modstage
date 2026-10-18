import { drawTranscript, FIRST_PAGE } from './transcript.tsx'
import { ACCENT, ENGINE, STATUS, colourOf } from './palette.ts'
import { autonomyLabel, elapsed, kTok, pct, shortPath, steerLabel, totals } from './format.ts'
import { headParts, widthFor } from './head.ts'
import type { HeadPart } from './head.ts'
import { engineDots, statusGlyph } from './runs.ts'

// ModStage view: one drawing function used two ways.
//  - As a Client surface module (default export): it owns a frame clock and animates locally.
//  - From the hooks module's own ui.render (drawStage): animated by a hooks-side tick, for surfaces without Client.
// Look follows Claude Code's transcript: ⏺ for actions, ⎿ for results, ✻ spinner, rounded boxes.

export type Usage = {
  input: number; cached: number; output: number; reasoning: number
  context_used: number; context_window: number | null; cost_usd: number | null
}
export { statusGlyph, bandRuns, engineDots } from './runs.ts'
export type { EngineDot } from './runs.ts'

export type RunView = {
  id: string; engine: string; model: string | null; label: string; cwd: string
  status: string; activity: string; elapsed_s: number; usage: Usage; error: string | null
  name?: string; color?: string | null; steer?: string; autonomy?: string; quiet_s?: number; stuck?: boolean
  approval_note?: string; pending?: unknown[]; blocked?: string; effort?: string
}
export type EventView = { seq: number; kind: string; text: string; detail?: string }
export type StageProps = {
  runs: RunView[]
  selected: string
  feed: EventView[]
  partial: string
  age: number
  problem: string
  home: string
  canType: boolean
}
export type Action =
  | { type: 'select'; id: string }
  | { type: 'send'; id: string; text: string }
  | { type: 'interrupt'; id: string }
  | { type: 'close'; id: string }

/** Client props are plain JSON of at most 100000 characters; past that the engine unmounts the stage.
 *  Pass only what the stage draws (a run's approvals as bare titles, no details, claims or file lists),
 *  and if it is still too big, drop the oldest transcript rows. */
export const CLIENT_PROP_LIMIT = 90000
const clip = (v: unknown, n: number) => (typeof v === 'string' ? v.slice(0, n) : v)
export function forClient(p: StageProps): StageProps {
  const runs = p.runs.slice(0, 40).map((r: any) => ({
    id: r.id, engine: r.engine, model: clip(r.model, 80) ?? null, label: clip(r.label, 120), cwd: clip(r.cwd, 300),
    status: r.status, activity: clip(r.activity, 160), elapsed_s: r.elapsed_s, usage: r.usage, error: clip(r.error, 300) ?? null,
    name: r.name, color: r.color, steer: r.steer, autonomy: r.autonomy, quiet_s: r.quiet_s, stuck: r.stuck,
    approval_note: clip(r.approval_note, 200), blocked: clip(r.blocked, 200),
    pending: (r.pending ?? []).slice(0, 10).map((x: any) => ({ title: clip(x?.title, 120) })),
  }))
  let out: StageProps = JSON.parse(JSON.stringify({ ...p, runs }))
  while (JSON.stringify(out).length > CLIENT_PROP_LIMIT && out.feed.length > 4) {
    out = { ...out, feed: out.feed.slice(Math.ceil(out.feed.length / 4)) }
  }
  return out
}

const SPIN = ['·', '✢', '✳', '✶', '✻', '✽', '✻', '✶', '✳', '✢']
const SHIMMER = ['#7F849C', '#A6ADC8', '#CDD6F4', '#F5E0DC', '#CDD6F4', '#A6ADC8']
const GRADIENT = ['#D97757', '#E08A5F', '#E0AF68', '#C9A0DC', '#C792EA', '#A9B1F5', '#7AA2F7', '#A9B1F5', '#C792EA', '#C9A0DC', '#E0AF68', '#E08A5F']

const bar = (percent: number | null, cells = 10) => {
  if (percent == null) return '▱'.repeat(cells)
  const full = Math.round((percent / 100) * cells)
  return '▰'.repeat(full) + '▱'.repeat(cells - full)
}

/** The agent's mark in the terminal: a squared head with a visor, 3 rows x 9 columns. Working: a light sweeps the visor.
 *  Waiting on you: both eyes lit amber. Idle: eyes that blink. Ended: eyes closed. Failed: crossed eyes. */
function robot(Text: any, colour: string, status: string, tick: number, waiting = false) {
  const working = status === 'running' || status === 'starting'
  const failed = status === 'error'
  const idle = status === 'idle'
  const lit = failed ? '#F7768E' : waiting ? '#F5B93A' : colour
  const blink = idle && tick % 48 < 2
  let visor: string
  if (working && !waiting) {
    const span = 3 // the 2-cell light travels across cells 0..3 of the 5-cell visor and back
    const step = Math.floor(tick / 3) % (span * 2)
    const at = step <= span ? step : span * 2 - step
    visor = ' '.repeat(at) + '▬▬' + ' '.repeat(span - at)
  } else if (failed) visor = ' × × '
  else if (working || idle) visor = blink ? ' ─ ─ ' : ' ● ● '
  else visor = ' ─ ─ '
  const tip = working ? (Math.floor(tick / 6) % 2 === 0 ? lit : '#585B70') : failed ? '#F7768E' : '#585B70'
  return [
    <Text key="r0" wrap="truncate"><Text color={colour}> ╭──</Text><Text color={tip}>●</Text><Text color={colour}>──╮ </Text></Text>,
    <Text key="r1" wrap="truncate"><Text color={colour}>▐│</Text><Text color={lit}>{visor}</Text><Text color={colour}>│▌</Text></Text>,
    <Text key="r2" wrap="truncate" color={colour}> ╰─────╯ </Text>,
  ]
}

export type Fit = { maxLines: number; composer: boolean }

function drawHeader(el: any, p: StageProps, tick: number) {
  const { Box, Text } = el
  const anyRunning = p.runs.some(r => r.status === 'running' || r.status === 'starting')
  const spin = SPIN[tick % SPIN.length]
  const pulse = tick % 12 < 6
  const live = p.age >= 0 && p.age <= 3
  return (
    <Box key="hdr" borderStyle="round" borderColor={ACCENT} paddingX={1} flexDirection="row" justifyContent="space-between">
      <Text>
        <Text color={ACCENT} bold>{anyRunning ? spin : '✻'} </Text>
        {'ModStage'.split('').map((ch, i) => <Text key={`t${i}`} bold color={GRADIENT[(i + Math.floor(tick / 2)) % GRADIENT.length]}>{ch}</Text>)}
      </Text>
      <Box key="dots" flexDirection="row" columnGap={2} flexShrink={1} overflow="hidden">
        {engineDots(p.runs).map(d => (
          <Text key={`dot:${d.engine}`} wrap="truncate-end">
            <Text color={d.working && !pulse ? '#45475A' : d.colour} bold={d.working}>{d.open ? '●' : '○'}</Text>
            <Text color={d.open ? d.colour : '#7F849C'}> {d.engine}{d.count > 1 ? ` ${d.count}` : ''}</Text>
          </Text>
        ))}
      </Box>
      <Text>
        <Text color={live ? (pulse ? '#9ECE6A' : '#5F7F45') : '#F7768E'}>●</Text>
        <Text dimColor> {live ? 'live' : p.age < 0 ? 'connecting' : `stalled ${p.age}s`} · {p.runs.length} run{p.runs.length === 1 ? '' : 's'}</Text>
      </Text>
    </Box>
  )
}

/** Tabs: one per run. Each shows the agent's own colour in its mark (a spinner while it works, ✓ waiting for Claude, ✗ failed,
 *  ○ ended), the agent's name as a button (filled when selected) and the task in dim text, all on one baseline. */
export function drawTabs(el: any, p: StageProps, tick: number, act: (a: Action) => void) {
  const { Box, Text, Button } = el
  const spin = SPIN[tick % SPIN.length]
  return (
    <Box key="tabs" flexDirection="row" flexWrap="wrap" columnGap={2} rowGap={1} paddingX={1} alignItems="center">
      {p.runs.length === 0
        ? <Text dimColor>No runs yet. Start one with "Start an agent", or ask Claude to hand a task to any installed agent.</Text>
        : p.runs.map(r => {
            const on = r.id === p.selected
            const c = colourOf(r)
            return (
              <Box key={`tab:${r.id}`} flexDirection="row" columnGap={1} alignItems="center">
                <Text color={c} bold>{statusGlyph(r.status, spin)}</Text>
                <Button key={`tabbtn:${r.id}`} label={r.name ?? r.engine} variant={on ? 'primary' : undefined}
                  hover={{ color: c, bold: true } as any} onPress={() => act({ type: 'select', id: r.id })} />
                <Text color={on ? '#F5E0DC' : '#7F849C'} wrap="truncate-end">{r.label.slice(0, 22)}{r.label.length > 22 ? '…' : ''}</Text>
              </Box>
            )
          })}
    </Box>
  )
}

/** The selected run's card: robot, status, badges, path, context and token use. No transcript. */
function drawCard(el: any, p: StageProps, run: RunView, tick: number) {
  const { Box, Text } = el
  const spin = SPIN[tick % SPIN.length]
  const colour = colourOf(run)
  const running = run.status === 'running' || run.status === 'starting'
  const c = pct(run)
  return (
    <Box key="detail" borderStyle="round" borderColor={colour} paddingX={1} flexDirection="row" columnGap={2}>
      <Box flexDirection="column" width={11} minWidth={11} flexShrink={0}>{robot(Text, colour, run.status, tick, (run.pending?.length ?? 0) > 0)}</Box>
      <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0}>
        <Box flexDirection="row" justifyContent="space-between">
          <Text>
            <Text color={colour} bold>{run.engine}</Text>
            <Text dimColor> {run.model ?? ''}{run.effort ? ` · ${run.effort}` : ''} · {run.id}</Text>
          </Text>
          <Text color={STATUS[run.status] ?? '#A6ADC8'}>{running ? spin : '●'} {run.status} · {elapsed(run.elapsed_s)}</Text>
        </Box>
        <Text bold wrap="truncate-end">{run.label}</Text>
        <Text wrap="truncate-end">
          <Text backgroundColor="#313244" color={colour}> {steerLabel(run)} </Text>
          <Text> </Text>
          <Text backgroundColor="#313244" color={autonomyLabel(run).warn ? '#F7768E' : '#5FD38D'}> {autonomyLabel(run).text} </Text>
          {run.pending && run.pending.length ? <Text color="#E0AF68" bold>  ⚑ {run.pending.length} waiting on you</Text> : null}
          {run.stuck ? <Text color="#F7768E" bold>  ⏸ quiet {Math.round((run.quiet_s ?? 0) / 60)}m</Text>
            : running && (run.quiet_s ?? 0) >= 45 ? <Text dimColor>  · no new output for {(run.quiet_s ?? 0) < 120 ? `${run.quiet_s}s` : `${Math.round((run.quiet_s ?? 0) / 60)}m`}, still running</Text> : null}
        </Text>
        {run.blocked ? <Text color="#F7768E" wrap="truncate-end">⛔ blocked: {run.blocked}</Text>
          : run.approval_note ? <Text color="#E0AF68" wrap="truncate-end">⚠ {run.approval_note}</Text> : null}
        <Text dimColor wrap="truncate-middle">{shortPath(run.cwd, p.home)}</Text>
        <Text wrap="truncate-end">
          <Text dimColor>context </Text><Text color={c != null && c > 80 ? '#F7768E' : colour}>{bar(c, 12)}</Text>
          <Text dimColor> {c == null ? '' : `${c}% · `}{kTok(run.usage.context_used)}/{kTok(run.usage.context_window)}</Text>
        </Text>
        <Text dimColor wrap="truncate-end">
          in {kTok(run.usage.input)} ({kTok(run.usage.cached)} cached) · out {kTok(run.usage.output)}{run.usage.reasoning ? ` (${kTok(run.usage.reasoning)} thinking)` : ''}
          {run.usage.cost_usd != null ? `  ·  ≈$${run.usage.cost_usd.toFixed(2)} at API price` : ''}
        </Text>
      </Box>
    </Box>
  )
}

/** Four stat tiles for the terminal: what is working, what needs you, what finished and what it cost. */
function drawTiles(el: any, p: StageProps) {
  const { Box, Text } = el
  const t = totals(p.runs)
  const cell = (key: string, label: string, value: string, colour: string, live: boolean) => (
    <Box key={key} flexDirection="column" borderStyle="round" borderColor={live ? colour : '#45475A'} paddingX={1} width="25%" flexShrink={1} minWidth={0}>
      <Text dimColor wrap="truncate-end">{label}</Text>
      <Text bold color={live ? colour : '#7F849C'} wrap="truncate-end">{value}</Text>
    </Box>
  )
  return (
    <Box key="tiles" flexDirection="row" columnGap={1}>
      {cell('t-work', 'WORKING', String(t.working), STATUS.running!, t.working > 0)}
      {cell('t-wait', 'NEEDS YOU', String(t.waiting), '#F5B93A', t.waiting > 0)}
      {cell('t-done', 'FINISHED', String(t.finished), '#5FD38D', t.finished > 0)}
      {cell('t-cost', 'SPEND', t.priced ? `$${t.usd < 100 ? t.usd.toFixed(2) : Math.round(t.usd)}` : '–', '#CDD6F4', t.priced)}
    </Box>
  )
}

/** The head: title bar, stat tiles and the selected run's card. On the desktop (`px` set and the surface draws vectors)
 *  it is one vector picture sized to the pane; in the terminal it is text, animated by `tick`. Nothing in it depends on
 *  the room it is given, so drawing it in a Client or in the pane body gives the same picture. */
export function drawHead(el: any, p: StageProps, tick: number, px?: number) {
  const { Box, Text, Svg } = el
  if (Svg && px) {
    // Separate pictures, drawn in a frame (isInteractive) so their CSS animation runs; the robot's picture is stable, so its
    // animation is not restarted when the numbers in the pictures beside it change.
    const pic = (hp: HeadPart) => (
      <Svg key={hp.key} source={hp.source} alt={hp.alt} width={hp.width} height={hp.height} {...(hp.animated ? { isInteractive: true } : {})} />
    )
    return (
      <Box key="head-svg" flexDirection="column" rowGap={1}>
        {headParts(p, px).map((item, i) => Array.isArray(item)
          ? <Box key={`head-row${i}`} flexDirection="row" columnGap={1}>{item.map(pic)}</Box>
          : pic(item))}
      </Box>
    )
  }
  const run = p.runs.find(r => r.id === p.selected)
  return (
    <Box key="head" flexDirection="column" rowGap={1}>
      {drawHeader(el, p, tick)}
      {p.problem ? <Text color="#F7768E">  bridge: {p.problem}</Text> : null}
      {drawTiles(el, p)}
      {run ? drawCard(el, p, run, tick) : null}
    </Box>
  )
}

/** The whole stage in one tree (head, tabs, transcript). The pane composes these pieces itself so the
 *  transcript can scroll; this is the same picture in one call, for tests and simple surfaces.
 *  `seenAt` is unused now (the typewriter reveal went with the in-Client transcript) and kept for callers. */
export function drawStage(el: any, p: StageProps, tick: number, _seenAt: Record<number, number>, act: (a: Action) => void,
                          fit: Fit = { maxLines: FIRST_PAGE, composer: true }) {
  const { Box } = el
  const run = p.runs.find(r => r.id === p.selected)
  return (
    <Box flexDirection="column" rowGap={1}>
      {drawHead(el, p, tick)}
      {drawTabs(el, p, tick, act)}
      {run ? drawTranscript(el, {
        run, feed: p.feed, partial: p.partial, open: new Set<string>(), shown: Math.max(3, fit.maxLines),
        colour: colourOf(run), spin: SPIN[tick % SPIN.length]!,
      }, () => {}) : null}
    </Box>
  )
}

/** The Client surface module: a 100 ms frame clock animates the head (title bar and robot card). Its content
 *  never depends on its own measured region (no surface.rows), so letting the region be as tall as what it draws
 *  cannot feed back on itself: that loop is what made the engine unmount the old stage. The transcript is not
 *  drawn here: the pane body draws it so it scrolls. */
const started = new WeakSet<object>()

export default function StageClient(props: any, surface: any) {
  const p = props as StageProps
  if (!started.has(surface)) {
    started.add(surface)
    let n = 0
    surface.every(100, () => surface.setState({ tick: ++n }))
  }
  const tick: number = (surface.state as { tick?: number } | undefined)?.tick ?? 0
  return drawHead(surface.elements, p, tick)
}
