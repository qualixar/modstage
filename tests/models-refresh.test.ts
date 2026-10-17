import { expect, mock, test } from 'claude-code/testing'

// The bridge outlives Claude Code sessions, so each session start asks it to fetch every agent's
// model list again, and stage_agents shows Muse's contributor ids folded into their model.

const AGENTS = [
  { id: 'muse', name: 'Muse', installed: true, version: '1', steer: 'native', color: null, command: 'muse', note: '',
    takes_model: true, default_model: 'muse-wonder-1.0',
    models: [{ id: 'muse-wonder-1.0', label: 'muse-wonder-1.0', variant: 'muse-wonder-1.0-contributor' }, { id: 'muse-spark-1.3', label: 'muse-spark-1.3' }] },
]

function fakeBridge(on: any, calls: string[]) {
  mock.env(on, { HOME: '/home/test' })
  on('fs.read', async () => ({ value: 'tok' }))
  on('process.run', async () => ({ value: { exitCode: 0, stdout: '', stderr: '' } }))
  // what the engine beneath answers when the mod starts: tool and command registrations, and the start itself
  on('tool.register', async () => ({ value: undefined }))
  on('command.register', async () => ({ value: undefined }))
  on('session.start', async (_$: any, e: any) => ({ cwd: e.cwd }))
  on('http.fetch', async (_$: any, e: any) => {
    const path = new URL(e.url).pathname
    calls.push(`${e.init?.method ?? 'GET'} ${path}`)
    const answer = path === '/agents' ? { agents: AGENTS } : path === '/runs' ? { runs: [] } : path === '/inbox' ? { pending: [] } : { ok: 'x' }
    return { value: { status: 200, ok: true, headers: {}, text: JSON.stringify(answer) } }
  })
}

test('session start asks the bridge to refresh every model list before reading them', async ($, on) => {
  const calls: string[] = []
  fakeBridge(on, calls)
  await $.session.start({ cwd: '/home/test/demo', surface: null, isInteractive: false })
  const refresh = calls.indexOf('POST /agents/refresh')
  expect(refresh).toBeGreaterThan(-1)
  expect(calls.indexOf('GET /agents', refresh)).toBeGreaterThan(refresh)
})

test('stage_agents shows the contributor id as a variant of its model', async ($, on) => {
  fakeBridge(on, [])
  const res: any = await $.tool.call({ tool: 'mcp__modstage__stage_agents' } as any)
  const out = String(res?.result ?? res?.text ?? '')
  expect(out).toContain('default muse-wonder-1.0')
  expect(out).toContain('muse-wonder-1.0 (or muse-wonder-1.0-contributor: same model')
  expect(out).toContain('muse-spark-1.3')
})
