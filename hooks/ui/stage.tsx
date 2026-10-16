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
}
export type Action =
  | { type: 'select'; id: string }
  | { type: 'send'; id: string; text: string }
  | { type: 'interrupt'; id: string }
  | { type: 'close'; id: string }

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

/** Draws the whole stage. `tick` advances ~12 times a second; `seenAt` maps event seq → tick first drawn. */
export type Fit = { maxLines: number; composer: boolean }

export function drawStage(el: any, p: StageProps, tick: number, seenAt: Record<number, number>, act: (a: Action) => void, fit: Fit = { maxLines: 30, composer: true }) {
  const { Box, Text, Button } = el
  const Input = el.Input
  const anyRunning = p.runs.some(r => r.status === 'running' || r.status === 'starting')
  const spin = SPIN[tick % SPIN.length]
  const run = p.runs.find(r => r.id === p.selected)
  const pulse = tick % 12 < 6
  const live = p.age >= 0 && p.age <= 3

  const header = (
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

  // Tabs: one per run, the engine's colour, a spinner while it works. The selected tab is filled.
  const tabs = (
    <Box key="tabs" flexDirection="row" flexWrap="wrap" columnGap={1} paddingX={1}>
      {p.runs.length === 0
        ? <Text dimColor>No runs yet. Start one with "Start an agent", or ask Claude to hand a task to any installed agent.</Text>
        : p.runs.map(r => {
            const on = r.id === p.selected
            const running = r.status === 'running' || r.status === 'starting'
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

  if (!run) return <Box flexDirection="column" gap={1}>{header}{p.problem ? <Text color="#F7768E">  bridge: {p.problem}</Text> : null}{tabs}</Box>

  const colour = run.color ?? ENGINE[run.engine] ?? '#CDD6F4'
  const running = run.status === 'running' || run.status === 'starting'
  const newest = p.feed.length ? p.feed[p.feed.length - 1]!.seq : 0
  // one row per event and a fixed budget, so the view never outgrows the pane and never jumps
  const lines = p.feed.slice(-Math.max(3, fit.maxLines)).map(ev => {
    const age = tick - (seenAt[ev.seq] ?? tick)
    const fresh = age < 10
    const first = (ev.text.split('\n')[0] ?? '')
    // typewriter: the newest message reveals over a few frames
    const shown = ev.seq === newest && ev.kind === 'message' && age < 40 ? first.slice(0, Math.max(1, age * 8)) : first
    const out = ev.detail ? (ev.detail.split('\n').filter(Boolean).slice(-1)[0] ?? '') : ''
    switch (ev.kind) {
      case 'you':
        return <Text key={`e${ev.seq}`} wrap="truncate-end"><Text color={ACCENT} bold>&gt; </Text><Text color="#F5E0DC">{first}</Text></Text>
      case 'tool':
        return <Text key={`e${ev.seq}`} wrap="truncate-end"><Text color={fresh ? ACCENT : colour}>⏺ </Text><Text bold={fresh}>{first}</Text></Text>
      case 'result':
        return <Text key={`e${ev.seq}`} wrap="truncate-end" dimColor>  ⎿  {first}{out ? ` · ${out.slice(0, 120)}` : ''}</Text>
      case 'edit':
        return <Text key={`e${ev.seq}`} wrap="truncate-end"><Text color="#9ECE6A">⏺ </Text><Text color="#9ECE6A">{first}</Text></Text>
      case 'message':
        return <Text key={`e${ev.seq}`} wrap="truncate-end"><Text color="#CDD6F4">⏺ </Text><Text color="#CDD6F4">{shown}</Text></Text>
      case 'thinking':
        return <Text key={`e${ev.seq}`} wrap="truncate-end" dimColor italic>  ✻ {first}</Text>
      case 'plan':
        return <Text key={`e${ev.seq}`} wrap="truncate-end"><Text color="#E0AF68">☰ </Text><Text dimColor>{ev.text.replace(/\n/g, '  ').slice(0, 300)}</Text></Text>
      case 'error':
        return <Text key={`e${ev.seq}`} wrap="truncate-end" color="#F7768E">✗ {first}</Text>
      case 'warning':
        return <Text key={`e${ev.seq}`} wrap="truncate-end" color="#E0AF68">! {first}</Text>
      default:
        return <Text key={`e${ev.seq}`} wrap="truncate-end" dimColor>· {first}</Text>
    }
  })

  // "Thinking…" shimmer while the agent works and has nothing streaming yet
  const word = `${run.activity.charAt(0).toUpperCase()}${run.activity.slice(1)}…`.slice(0, 60)
  const shimmer = running && !p.partial ? (
    <Text key="shim">
      <Text color={ACCENT}>{spin} </Text>
      {word.split('').map((ch, i) => <Text key={`s${i}`} color={SHIMMER[(i - tick + 600) % SHIMMER.length]}>{ch}</Text>)}
      <Text dimColor>  {elapsed(run.elapsed_s)}</Text>
    </Text>
  ) : null
  const streaming = running && p.partial
    ? <Text key="stream" wrap="truncate-end"><Text color={ACCENT}>{spin} </Text><Text color="#CDD6F4">{p.partial.split('\n').filter(Boolean).slice(-1)[0] ?? ''}</Text><Text color={pulse ? ACCENT : '#2A2D3A'}>▍</Text></Text>
    : null

  const c = pct(run)
  const detail = (
    <Box key="detail" borderStyle="round" borderColor={colour} paddingX={1} flexDirection="column">
      <Box flexDirection="row" columnGap={2}>
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
      <Box flexDirection="column" marginTop={1}>
        {lines}
        {shimmer}
        {streaming}
      </Box>
    </Box>
  )

  return (
    <Box flexDirection="column" rowGap={1}>
      {header}
      {p.problem ? <Text color="#F7768E">  bridge: {p.problem}</Text> : null}
      {tabs}
      {detail}
    </Box>
  )
}

// Per-instance bookkeeping lives outside `surface.state`: drawing must never call setState
// (three draws in a row that set state count as a render loop and the engine unmounts the instance).
const started = new WeakSet<object>()
const seenBy = new WeakMap<object, Record<number, number>>()

/** The Client surface module: a 100 ms frame clock drives the animation; actions go to the hooks module by post. */
export default function StageClient(props: any, surface: any) {
  const p = props as StageProps
  if (!started.has(surface)) {
    started.add(surface)
    let n = 0
    surface.every(100, () => surface.setState({ tick: ++n }))
  }
  const tick: number = (surface.state as { tick?: number } | undefined)?.tick ?? 0
  let seenAt = seenBy.get(surface)
  if (!seenAt) seenBy.set(surface, (seenAt = {}))
  for (const ev of p.feed ?? []) if (seenAt[ev.seq] === undefined) seenAt[ev.seq] = tick
  // header 3 + tabs 1 + card chrome 10 + spacing 3 + live line 1 = 18 rows that are not transcript
  const maxLines = Math.max(4, (surface.rows || 36) - 18)
  return drawStage(surface.elements, p, tick, seenAt, a => surface.post(a), { maxLines, composer: false })
}
