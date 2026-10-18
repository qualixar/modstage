// Small formatters shared by the text and the vector drawings of the panel.
import type { RunView } from './stage.tsx'

export const kTok = (n: number | null | undefined): string =>
  n == null ? '–' : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(Math.round(n))

export const elapsed = (s: number): string => (s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`)

/** Percent of the context window a run uses, or null when its window is unknown. */
export const pct = (r: RunView): number | null =>
  r.usage.context_window ? Math.min(100, Math.round((100 * r.usage.context_used) / r.usage.context_window)) : null

export const shortPath = (path: string, home: string): string => {
  const p = home && path.startsWith(home) ? '~' + path.slice(home.length) : path
  return p.length > 56 ? p.slice(0, 20) + '…' + p.slice(-34) : p
}

/** How a run is steered, in the words the panel uses. */
export const steerLabel = (r: RunView): string => (r.steer === 'native' ? 'steerable' : r.steer === 'watch' ? 'watch only' : 'queued messages')

/** What the agent may do without asking, as a label and whether it deserves a warning colour. */
export function autonomyLabel(r: RunView): { text: string; warn: boolean } {
  if (r.autonomy === 'auto') return { text: 'autonomous', warn: true }
  if (r.steer === 'watch') return { text: 'Claude subagent', warn: false }
  return { text: r.engine === 'antigravity' ? 'read-only' : 'asks first', warn: false }
}

/** The totals the stat tiles show. */
export function totals(runs: RunView[]) {
  let working = 0, waiting = 0, finished = 0, usd = 0, priced = false
  for (const r of runs) {
    if (r.status === 'running' || r.status === 'starting') working++
    else if (r.status === 'idle' || r.status === 'done') finished++
    waiting += r.pending?.length ?? 0
    if (r.usage.cost_usd != null) { usd += r.usage.cost_usd; priced = true }
  }
  return { working, waiting, finished, usd, priced }
}
