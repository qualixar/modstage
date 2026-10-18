// Run marks and groupings shared by the band, the tabs and the head.
import { ENGINE, FALLBACK, safeColour } from './palette.ts'

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
    const d = dots.get(r.engine) ?? { engine: r.engine, colour: safeColour(r.color) ?? ENGINE[r.engine] ?? FALLBACK, count: 0, working: false, open: false }
    d.count += 1
    d.working ||= r.status === 'running' || r.status === 'starting'
    d.open ||= statusGlyph(r.status) !== '○'
    dots.set(r.engine, d)
  }
  return [...dots.values()]
}

