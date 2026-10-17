import { expect, mock, test } from 'claude-code/testing'

// A session registers its id with the bridge once and gets a key (its capability); every run it starts
// carries that key. When $.session.id() gives nothing, the id the classic hook envelope carried is used;
// with neither, nothing is registered and the run is refused rather than left ownerless. A restarted
// bridge forgets keys: the mod registers again and retries once.

type Seen = { posted: any[]; idWorks: boolean; registered?: string[]; forgetOnce?: boolean }

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
    const reply = (status: number, body: any) => ({ value: { status, ok: status < 300, headers: {}, text: JSON.stringify(body) } })
    if (path === '/sessions') {
      const session = JSON.parse(e.init.body).session
      seen.registered = [...(seen.registered ?? []), session]
      return reply(200, { key: `key-${session}-${seen.registered.length}`, peer: 'claude-x' })
    }
    const key = String(e.init?.headers?.['X-ModStage-Session'] ?? '')
    if (path === '/runs' && e.init?.method === 'POST' && seen.forgetOnce) {
      seen.forgetOnce = false  // the bridge restarted and forgot every key
      return reply(401, { error: 'unknown session', code: 'session' })
    }
    if (e.init?.method === 'POST' && path === '/runs') seen.posted.push({ ...JSON.parse(e.init.body), key })
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
  await start($)
  expect(seen.registered).toEqual(['sess-A'])  // registered once, then the key is reused
  expect(seen.posted.map(p => p.key)).toEqual(['key-sess-A-1', 'key-sess-A-1'])
  expect(seen.posted.every(p => p.session === undefined)).toBe(true)  // the id is never the proof
})

test('a bridge that forgot the key is joined again and the start goes through once', async ($, on) => {
  const seen: Seen = { posted: [], idWorks: true }
  fakeBridge(on, seen)
  await start($)
  seen.forgetOnce = true
  await start($)
  expect(seen.registered).toEqual(['sess-A', 'sess-A'])
  expect(seen.posted.map(p => p.key)).toEqual(['key-sess-A-1', 'key-sess-A-2'])
})

test("without $.session.id(), the classic hook envelope's session_id is used", async ($, on) => {
  const seen: Seen = { posted: [], idWorks: false }
  fakeBridge(on, seen)
  await ($ as any).classic.UserPromptSubmit({ prompt: 'hi', session_id: 'sess-H' })
  await start($)
  expect(seen.registered).toEqual(['sess-H'])
  expect(seen.posted).toHaveLength(1)
})

test('with no id at all, the run is refused and nothing reaches the bridge', async ($, on) => {
  const seen: Seen = { posted: [], idWorks: false }
  fakeBridge(on, seen)
  const res = await start($)
  expect(seen.posted).toEqual([])
  expect(seen.registered ?? []).toEqual([])
  expect(out(res)).toContain("could not read this Claude Code session's id")
  expect(out(res)).toContain('no session owns')
})

test('/clear keeps the session key, so runs stay with this session and nothing registers again', async ($, on) => {
  const seen: Seen = { posted: [], idWorks: true }
  fakeBridge(on, seen)
  on('session.end', async (_$: any, e: any) => ({ sessionId: e.sessionId }))  // the engine beneath
  await start($)
  await ($ as any).session.end({ reason: 'clear', sessionId: 'sess-A', resume: { id: 'sess-A' } })
  await start($)
  expect(seen.registered).toEqual(['sess-A'])
  expect(seen.posted.map(p => p.key)).toEqual(['key-sess-A-1', 'key-sess-A-1'])
})
