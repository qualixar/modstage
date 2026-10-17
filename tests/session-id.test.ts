import { expect, mock, test } from 'claude-code/testing'

// A run is started under this Claude Code session's id. When $.session.id() gives nothing, the id the
// classic hook envelope carried is used; with neither, the run is refused rather than left ownerless
// (an ownerless run used to be shown to, and steerable from, every session that could not read its id).

type Seen = { posted: any[]; idWorks: boolean }

function fakeBridge(on: any, seen: Seen) {
  mock.env(on, { HOME: '/home/test' })
  on('fs.read', async () => ({ value: 'tok' }))
  on('session.cwd', async () => ({ value: '/home/test/demo' }))
  on('ui.toast', async () => ({ value: undefined }))
  on('classic.UserPromptSubmit', async () => ({}))  // the engine beneath: no settings hook decides
  on('session.id', async () => {
    if (!seen.idWorks) throw new Error('no session id here')
    return { value: 'sess-A' }
  })
  on('http.fetch', async (_$: any, e: any) => {
    const path = new URL(e.url).pathname
    if (e.init?.method === 'POST' && path === '/runs') seen.posted.push(JSON.parse(e.init.body))
    const answer = path === '/runs' && e.init?.method === 'POST' ? { id: 'run00001', autonomy: 'ask' }
      : path === '/runs' ? { runs: [] } : path === '/inbox' ? { pending: [] } : path === '/agents' ? { agents: [] } : {}
    return { value: { status: 200, ok: true, headers: {}, text: JSON.stringify(answer) } }
  })
}

const start = ($: any) => $.tool.call({ tool: 'mcp__modstage__stage_start', engine: 'codex', prompt: 'say ok' } as any)
const out = (res: any) => String(res?.result ?? res?.text ?? res?.deny ?? '')

test("a run is started under the session's own id", async ($, on) => {
  const seen: Seen = { posted: [], idWorks: true }
  fakeBridge(on, seen)
  await start($)
  expect(seen.posted.map(p => p.session)).toEqual(['sess-A'])
})

test("without $.session.id(), the classic hook envelope's session_id is used", async ($, on) => {
  const seen: Seen = { posted: [], idWorks: false }
  fakeBridge(on, seen)
  await ($ as any).classic.UserPromptSubmit({ prompt: 'hi', session_id: 'sess-H' })
  await start($)
  expect(seen.posted.map(p => p.session)).toEqual(['sess-H'])
})

test('with no id at all, the run is refused and nothing reaches the bridge', async ($, on) => {
  const seen: Seen = { posted: [], idWorks: false }
  fakeBridge(on, seen)
  const res = await start($)
  expect(seen.posted).toEqual([])
  expect(out(res)).toContain("could not read this Claude Code session's id")
  expect(out(res)).toContain('no session owns')
})
