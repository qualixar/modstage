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
  return what ? `${tool}(${String(what).slice(0, 600)})` : tool
}

const LIMIT = 3900
export const clip = (s: string, n = LIMIT) => (s.length <= n ? s : `${s.slice(0, n)}\n… (cut)`)

/** A replacement as -/+ lines under a file header: the old text, then the new text. */
function replacement(path: string, oldText: string, newText: string): string {
  const lines = (t: string, mark: string) => (t === '' ? [] : t.replace(/\n$/, '').split('\n').map(l => `${mark}${l}`))
  return [`--- a/${path}`, `+++ b/${path}`, ...lines(oldText, '-'), ...lines(newText, '+')].join('\n')
}

/** The change an Edit, MultiEdit or Write made, from its input; '' for any other tool. */
export function claudeEditDetail(tool: string, input: any): string {
  if (!input || typeof input !== 'object') return ''
  const path = String(input.file_path ?? input.path ?? 'file')
  if (tool === 'Edit' && typeof input.old_string === 'string') return clip(replacement(path, input.old_string, String(input.new_string ?? '')))
  if (tool === 'MultiEdit' && Array.isArray(input.edits)) {
    return clip(input.edits.map((x: any) => replacement(path, String(x?.old_string ?? ''), String(x?.new_string ?? ''))).join('\n'))
  }
  if (tool === 'Write' && typeof input.content === 'string') return clip(replacement(path, '', input.content))
  return ''
}

/** A tool call's whole input as readable lines (a command in full, every argument), '' when the summary says it all. */
export function claudeToolDetail(tool: string, input: any): string {
  if (!input || typeof input !== 'object') return ''
  if (claudeEditDetail(tool, input)) return ''   // an edit shows its diff on the edit row
  const rows = Object.entries(input).map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
  const text = rows.join('\n')
  const summary = describe(tool, input)
  return rows.length === 1 && summary.includes(text.split(': ').slice(1).join(': ').slice(0, 100)) ? '' : clip(text)
}

/** Claude runs with a fresh elapsed time, for drawing. */
export function liveClaude(list: RunSummary[]): RunSummary[] {
  const now = Date.now()
  return list.map(r => (r.status === 'running' ? { ...r, elapsed_s: Math.round((now - ((r as any).startedAt ?? now)) / 1000) } : r))
}
