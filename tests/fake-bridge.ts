import { mock } from 'claude-code/testing'

// A ModStage bridge played by test hooks (http.fetch, fs.read, session.id), for mod-level tests.

export type Bridge = { runs: Record<string, any>; decided: any[]; session: string; toasts?: string[]; sent?: any[]; waits?: string[]
  claude?: any[]; held?: any[]; mail?: any[]; down?: boolean }

export function fakeBridge(on: any, b: Bridge) {
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: b.session }))
  on('session.cwd', () => ({ value: '/home/test/demo' }))
  on('fs.read', () => ({ value: 'tok' }))
  on('ui.toast', (_$: any, e: any) => {
    b.toasts = [...(b.toasts ?? []), String(e.text)]
    return { value: undefined }
  })
  on('http.fetch', ($: any, e: any) => {
    const url = new URL(e.url)
    const parts = url.pathname.split('/').filter(Boolean)
    const reply = (status: number, body: any) => ({ value: { status, ok: status < 300, headers: {}, text: JSON.stringify(body) } })
    if (parts[0] === 'runs' && parts.length === 1) return reply(200, { runs: Object.values(b.runs), others: 0 })
    if (parts[0] === 'inbox') return reply(200, { pending: Object.values(b.runs).flatMap((r: any) => r.pending) })
    if (parts[0] === 'claude') {
      if (b.down) throw new Error('fetch failed: ECONNREFUSED')
      const body = JSON.parse(e.init?.body ?? '{}')
      b.claude = [...(b.claude ?? []), { op: parts[1], ...body }]
      if (parts[1] === 'edit_check') return reply(200, { held: (b.held ?? []).filter((h: any) => body.path.endsWith(h.path)) })
      if (parts[1] === 'inbox') return reply(200, { messages: b.mail ?? [] })
      if (parts[1] === 'board_read') return reply(200, { workspace: body.cwd, agents: [{ engine: 'codex', run_id: 'r1', state: 'working', doing: 'api.py' }], claims: b.held ?? [], log: [] })
      if (parts[1] === 'send') return reply(200, { message_id: 'm1' })
      return reply(200, {})
    }
    const run = b.runs[parts[1] ?? '']
    if (!run) return reply(404, { error: `no run ${parts[1]}` })
    if (parts[2] === 'send') {
      b.sent = [...(b.sent ?? []), JSON.parse(e.init.body)]
      return reply(200, { ok: 'queued' })
    }
    if (parts[2] === 'wait') {
      b.waits = [...(b.waits ?? []), url.search]
      return reply(200, { ...run, new_events: [], partial: '', timed_out: false })
    }
    if (parts[2] === 'decide') {
      const body = JSON.parse(e.init.body)
      b.decided.push(body)
      run.pending = run.pending.filter((p: any) => p.id !== body.approval_id)
      return reply(200, { ok: true })
    }
    return reply(200, { ...run, new_events: [], partial: '' })
  })
}

export const ask = (id: string, title: string) => ({ id, run_id: 'r1', engine: 'codex', kind: 'command', title, detail: 'network', warning: '', asked_at: 1 })
export const runWith = (pending: any[], owner = 'sess-A') => ({
  id: 'r1', engine: 'codex', status: 'running', activity: 'waiting', owner, pending,
  usage: { input: 0, cached: 0, output: 0, reasoning: 0, context_used: 0, context_window: null, cost_usd: null },
})
