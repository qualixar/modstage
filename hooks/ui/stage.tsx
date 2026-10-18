import { drawTranscript, FIRST_PAGE } from './transcript.tsx'

// ModStage view: one drawing function used two ways.
//  - As a Client surface module (default export): it owns a frame clock and animates locally.
//  - From the hooks module's own ui.render (drawStage): animated by a hooks-side tick, for surfaces without Client.
// Look follows Claude Code's transcript: ⏺ for actions, ⎿ for results, ✻ spinner, rounded boxes.

export type Usage = {
  input: number; cached: number; output: number; reasoning: number
  context_used: number; context_window: number | null; cost_usd: number | null
}
/** One mark per run state, used by the panel tabs and the band above the prompt so they always agree.
 *  ✓ the turn finished and the run waits for Claude · ○ the run has ended · ✗ failed · ◼ interrupted.
 *  Running shows the caller's spinner frame (the band has no clock, so it passes a fixed ✻). */
export function statusGlyph(status: string, spin = '✻'): string {
  if (status === 'running' || status === 'starting') return spin
  return status === 'idle' ? '✓' : status === 'error' ? '✗' : status === 'interrupted' ? '◼' : '○'
}

// The band has room for a few runs: the ones that need attention first, newest first within each group.
const BAND_RANK: Record<string, number> = { running: 0, starting: 0, idle: 1, error: 2, interrupted: 3 }
export function bandRuns<T extends { status: string }>(runs: T[], max = 5): { shown: T[]; hidden: number } {
  const ranked = runs.map((r, i) => ({ r, i })).sort((a, b) =>
    (BAND_RANK[a.r.status] ?? 4) - (BAND_RANK[b.r.status] ?? 4) || b.i - a.i)
  return { shown: ranked.slice(0, max).map(x => x.r), hidden: Math.max(0, runs.length - max) }
}

/** The header's live dots: one per agent that has runs now, in first-run order, never a fixed list.
 *  ● pulsing = one of its runs is working · ● = waiting for Claude · ○ = all of its runs have ended. */
export type EngineDot = { engine: string; colour: string; count: number; working: boolean; open: boolean }
export function engineDots(runs: Array<{ engine: string; status: string; color?: string | null }>): EngineDot[] {
  const dots = new Map<string, EngineDot>()
  for (const r of runs) {
    const d = dots.get(r.engine) ?? { engine: r.engine, colour: r.color ?? ENGINE[r.engine] ?? '#CDD6F4', count: 0, working: false, open: false }
    d.count += 1
    d.working ||= r.status === 'running' || r.status === 'starting'
    d.open ||= statusGlyph(r.status) !== '○'
    dots.set(r.engine, d)
  }
  return [...dots.values()]
}

export type RunView = {
  id: string; engine: string; model: string | null; label: string; cwd: string
  status: string; activity: string; elapsed_s: number; usage: Usage; error: string | null
  name?: string; color?: string | null; steer?: string; autonomy?: string; quiet_s?: number; stuck?: boolean
  approval_note?: string; pending?: unknown[]; blocked?: string
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
  /** Rows the stage may fill, decided outside it (see nativeRows). */
  rows?: number
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

const ACCENT = '#D97757' // Claude's coral
// Fallback colours (the bridge sends each run's own colour from the registry; these match it)
const ENGINE: Record<string, string> = {
  codex: '#7AA2F7', muse: '#C792EA', grok: '#E0AF68', antigravity: '#8AB4F8', kimi: '#F5C2E7',
  qwen: '#9ECE6A', opencode: '#FAB387', claude: '#D97757',
}
const STATUS: Record<string, string> = {
  running: ACCENT, starting: ACCENT, idle: '#9ECE6A', done: '#7F849C', error: '#F7768E', interrupted: '#E0AF68',
}
const SPIN = ['·', '✢', '✳', '✶', '✻', '✽', '✻', '✶', '✳', '✢']
const SHIMMER = ['#7F849C', '#A6ADC8', '#CDD6F4', '#F5E0DC', '#CDD6F4', '#A6ADC8']
const GRADIENT = ['#D97757', '#E08A5F', '#E0AF68', '#C9A0DC', '#C792EA', '#A9B1F5', '#7AA2F7', '#A9B1F5', '#C792EA', '#C9A0DC', '#E0AF68', '#E08A5F']

const kTok = (n: number | null | undefined) =>
  n == null ? '–' : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(Math.round(n))

const pct = (r: RunView) =>
  r.usage.context_window ? Math.min(100, Math.round((100 * r.usage.context_used) / r.usage.context_window)) : null

const bar = (percent: number | null, cells = 10) => {
  if (percent == null) return '▱'.repeat(cells)
  const full = Math.round((percent / 100) * cells)
  return '▰'.repeat(full) + '▱'.repeat(cells - full)
}

const shortPath = (path: string, home: string) => {
  const p = home && path.startsWith(home) ? '~' + path.slice(home.length) : path
  return p.length > 56 ? p.slice(0, 20) + '…' + p.slice(-34) : p
}

/** A small robot, Claude Code-mascot style, 3 rows x 9 columns in monospace.
 *  Working: arms swing, eyes glance, antenna blinks. Idle: dozes (zZ). Error: x eyes. */
function robot(Text: any, colour: string, status: string, tick: number) {
  const working = status === 'running' || status === 'starting'
  const failed = status === 'error'
  const swing = Math.floor(tick / 4) % 2 === 0
  const blink = tick % 40 < 2
  const look = Math.floor(tick / 16) % 4
  const eyes = failed ? 'x x' : !working ? '- -' : blink ? '- -' : look === 1 ? '◐ ◐' : look === 3 ? '◑ ◑' : '● ●'
  const armL = working ? (swing ? '╲' : '╱') : ' '
  const armR = working ? (swing ? '╱' : '╲') : ' '
  const feet = working ? (swing ? '╰┘ └╯' : '╰┘╶└╯') : '╰┘ └╯'
  const zz = !working && !failed ? ['  ', ' z', 'zZ', 'Z '][Math.floor(tick / 10) % 4] : '  '
  const tip = working ? (Math.floor(tick / 3) % 2 === 0 ? '#F5E0DC' : ACCENT) : failed ? '#F7768E' : '#585B70'
  return [
    <Text key="r0" wrap="truncate"><Text color={colour}>  ╭─</Text><Text color={tip}>●</Text><Text color={colour}>─╮</Text><Text dimColor>{zz}</Text></Text>,
    <Text key="r1" wrap="truncate" color={colour}>{armL} │{eyes}│ {armR}</Text>,
    <Text key="r2" wrap="truncate" color={colour}>  {feet}  </Text>,
  ]
}

const elapsed = (s: number) => (s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`)

export type Fit = { maxLines: number; composer: boolean }

/** Rows the animated head (title bar, then the robot card) is drawn into: a fixed number, so what the
 *  Client draws can never change the size of its own region. */
export const HEAD_ROWS = 16
export const HEAD_ROWS_NO_RUN = 4

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

/** Tabs: one per run, the engine's colour, a spinner while it works. The selected tab is filled. */
export function drawTabs(el: any, p: StageProps, tick: number, act: (a: Action) => void) {
  const { Box, Text, Button } = el
  const spin = SPIN[tick % SPIN.length]
  return (
    <Box key="tabs" flexDirection="row" flexWrap="wrap" columnGap={1} paddingX={1}>
      {p.runs.length === 0
        ? <Text dimColor>No runs yet. Start one with "Start an agent", or ask Claude to hand a task to any installed agent.</Text>
        : p.runs.map(r => {
            const on = r.id === p.selected
            const glyph = statusGlyph(r.status, spin)
            const c = r.color ?? ENGINE[r.engine] ?? '#CDD6F4'
            return (
              <Box key={`tab:${r.id}`} flexDirection="row" backgroundColor={on ? '#313244' : undefined} paddingRight={1}>
                <Text backgroundColor={c} color="#1E1E2E" bold> {glyph} </Text>
                <Text> </Text>
                <Button key={`tabbtn:${r.id}`} label={` ${r.engine} `} plain={on ? undefined : true} variant={on ? 'primary' : undefined}
                  hover={{ color: c, bold: true } as any} onPress={() => act({ type: 'select', id: r.id })} />
                <Text color={on ? '#F5E0DC' : '#7F849C'}> {r.label.slice(0, 22)}{r.label.length > 22 ? '…' : ''}</Text>
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
  const colour = run.color ?? ENGINE[run.engine] ?? '#CDD6F4'
  const running = run.status === 'running' || run.status === 'starting'
  const c = pct(run)
  return (
    <Box key="detail" borderStyle="round" borderColor={colour} paddingX={1} flexDirection="row" columnGap={2}>
      <Box flexDirection="column" width={11} minWidth={11} flexShrink={0}>{robot(Text, colour, run.status, tick)}</Box>
      <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0}>
        <Box flexDirection="row" justifyContent="space-between">
          <Text>
            <Text color={colour} bold>{run.engine}</Text>
            <Text dimColor> {run.model ?? ''} · {run.id}</Text>
          </Text>
          <Text color={STATUS[run.status] ?? '#A6ADC8'}>{running ? spin : '●'} {run.status} · {elapsed(run.elapsed_s)}</Text>
        </Box>
        <Text bold wrap="truncate-end">{run.label}</Text>
        <Text wrap="truncate-end">
          <Text backgroundColor="#313244" color={colour}> {run.steer === 'native' ? '⇄ steerable' : run.steer === 'watch' ? '◉ watch only' : '⇢ queued msgs'} </Text>
          <Text> </Text>
          <Text backgroundColor="#313244" color={run.autonomy === 'auto' ? '#F7768E' : '#9ECE6A'}> {run.autonomy === 'auto' ? '⚡ autonomous' : run.steer === 'watch' ? '✻ claude' : run.engine === 'antigravity' ? '◆ read-only' : '◆ asks first'} </Text>
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
          in {kTok(run.usage.input)} ({kTok(run.usage.cached)} cached) · out {kTok(run.usage.output)}
          {run.usage.cost_usd != null ? `  ·  ≈$${run.usage.cost_usd.toFixed(2)} at API price` : ''}
        </Text>
      </Box>
    </Box>
  )
}

/** The animated head: title bar, a bridge problem line, and the selected run's card. Fixed in size by
 *  the caller (HEAD_ROWS), so drawing it in a Client or in the pane body gives the same picture. */
export function drawHead(el: any, p: StageProps, tick: number) {
  const { Box, Text } = el
  const run = p.runs.find(r => r.id === p.selected)
  return (
    <Box key="head" flexDirection="column">
      {drawHeader(el, p, tick)}
      {p.problem ? <Text color="#F7768E">  bridge: {p.problem}</Text> : null}
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
        colour: run.color ?? ENGINE[run.engine] ?? '#CDD6F4', spin: SPIN[tick % SPIN.length]!,
      }, () => {}) : null}
    </Box>
  )
}

/** The Client surface module: a 100 ms frame clock animates the head; its size comes from its props and
 *  never from its own measured region (a region that sizes its content while its content sizes the region
 *  is unmounted by the engine). The transcript is not drawn here: the pane body draws it so it scrolls. */
const started = new WeakSet<object>()

export default function StageClient(props: any, surface: any) {
  const p = props as StageProps
  if (!started.has(surface)) {
    started.add(surface)
    let n = 0
    surface.every(100, () => surface.setState({ tick: ++n }))
  }
  const tick: number = (surface.state as { tick?: number } | undefined)?.tick ?? 0
  const rows = Math.max(HEAD_ROWS_NO_RUN, Math.round(p.rows ?? HEAD_ROWS))
  const { Box } = surface.elements
  return (
    <Box key="head-fixed" flexDirection="column" height={rows} overflow="hidden">
      {drawHead(surface.elements, p, tick)}
    </Box>
  )
}
