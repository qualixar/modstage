// Claude Code's own subagents, shown as ModStage tabs beside Codex, Muse and the rest.
// Pattern: agent.spawn opens a card (its result carries the agentId), tool.call with an agentId
// adds steps, turn.complete with an agentId closes it. Idea credit: claude-flightdeck and
// agent-radar (both MIT); this is our own implementation.
import type { RunSummary } from '../types'

export const MAX_RUNS = 30
export const MAX_EVENTS = 200
export const CLAUDE_COLOUR = '#D97757'

export const blankUsage = () => ({
  input: 0, cached: 0, output: 0, reasoning: 0, context_used: 0, context_window: null, cost_usd: null,
})

export function describe(tool: string, input: any): string {
  if (!input || typeof input !== 'object') return tool
  const what = input.command ?? input.file_path ?? input.path ?? input.pattern ?? input.url ?? input.query ?? input.description
  return what ? `${tool}(${String(what).slice(0, 140)})` : tool
}

/** Claude runs with a fresh elapsed time, for drawing. */
export function liveClaude(list: RunSummary[]): RunSummary[] {
  const now = Date.now()
  return list.map(r => (r.status === 'running' ? { ...r, elapsed_s: Math.round((now - ((r as any).startedAt ?? now)) / 1000) } : r))
}
