import { expect, mock, test } from 'claude-code/testing'

const AGENTS = [
  { id: 'codex', name: 'Codex', installed: true, version: '1', steer: 'native', color: '#7AA2F7', command: 'codex', note: '',
    takes_model: true, default_model: 'gpt-6.1-sol', models: [{ id: 'gpt-6.1-sol', label: 'GPT-6.1-Sol' }, { id: 'gpt-6-luna', label: 'GPT-6-Luna' }] },
  { id: 'grok', name: 'Grok', installed: true, version: '1', steer: 'queue', color: '#E0AF68', command: 'grok', note: '' },
  { id: 'kimi', name: 'Kimi', installed: false, version: '', steer: 'queue', color: '#9CA3AF', command: 'kimi', note: '' },
]

// Stand in for the bridge: the test's hooks sit beneath the plugin, so they answer its fetches.
function fakeBridge(on: any, posted: any[], spawned: any[] = [], sent: any[] = []) {
  on('agent.spawn', async (_$: any, e: any) => { spawned.push(e); return { agentId: 'cl001', model: e.model ?? 'inherit' } })
  on('session.send', async (_$: any, e: any) => { sent.push(e); return { value: { isSent: true } } })
  on('fs.read', async () => ({ value: 'test-token' }))
  on('session.cwd', async () => ({ value: '/home/test/project' }))
  on('ui.toast', async (_$: any, e: any) => { (globalThis as any).toasts = [...((globalThis as any).toasts ?? []), e.text]; return { value: undefined } })
  on('http.fetch', async (_$: any, e: any) => {
    const path = new URL(e.url).pathname
    const body = e.init?.body ? JSON.parse(e.init.body) : null
    if (e.init?.method === 'POST' && path === '/runs') posted.push(body)
    const answer = path === '/agents' ? { agents: AGENTS }
      : path === '/runs' && e.init?.method === 'POST' ? { id: 'run00001', autonomy: 'ask' }
      : path === '/runs' ? { runs: [] }
      : path === '/inbox' ? { pending: [] }
      : { events: [], next_seq: 0 }
    return { value: { status: 200, ok: true, headers: {}, text: JSON.stringify(answer) } }
  })
}

// Every installed agent is a button from the first draw. One click opens its task box; Start
// launches it in ask mode; clicking the agent again closes the box.
for (const surface of ['desktop', 'terminal'] as const) {
  test(`one-click start from the panel on ${surface}`, async ($, on) => {
    mock.env(on, { HOME: '/home/test' })
    const posted: any[] = []
    fakeBridge(on, posted)
    await $.tool.call({ tool: 'mcp__modstage__stage_agents' } as any)
    const ui: any = await $.ui.mount({
      plugin: 'modstage', surface, component: 'Pane', requestId: 'modstage',
      props: {} as any, viewport: { columns: 110, rows: 40 },
    })
    expect(await ui.find({ key: 'pick:codex' })).toBeDefined()
    expect(await ui.find({ key: 'pick:grok' })).toBeDefined()
    expect(await ui.find({ key: 'pick:kimi' })).toBeUndefined()
    expect(await ui.find({ key: 'launch-task:codex' })).toBeUndefined()

    await ui.press({ key: 'pick:codex' })
    expect(await ui.find({ key: 'launch-task:codex' })).toBeDefined()
    await ui.press({ key: 'model:gpt-6-luna' })

    await ui.input({ key: 'launch-task:codex', text: 'write tests' })
    expect(posted).toHaveLength(1)
    expect(posted[0].engine).toBe('codex')
    expect(posted[0].autonomy).toBe('ask')
    expect(posted[0].cwd).toBe('/home/test/project')
    expect(posted[0].model).toBe('gpt-6-luna')
    expect(await ui.find({ key: 'launch-task:codex' })).toBeUndefined()

    await ui.press({ key: 'pick:grok' })
    expect(await ui.find({ key: 'launch-task:grok' })).toBeDefined()
    await ui.press({ key: 'pick:grok' })
    expect(await ui.find({ key: 'launch-task:grok' })).toBeUndefined()
    await ui.unmount()
  })

  // Claude is a button too: it spawns a Claude Code subagent through the mod API, on the model
  // picked, and its tab takes messages (SendMessage's route).
  test(`Claude subagent from the panel on ${surface}`, async ($, on) => {
    mock.env(on, { HOME: '/home/test' })
    const posted: any[] = [], spawned: any[] = [], sent: any[] = []
    ;(globalThis as any).toasts = []
    fakeBridge(on, posted, spawned, sent)
    await $.tool.call({ tool: 'mcp__modstage__stage_agents' } as any)
    const ui: any = await $.ui.mount({
      plugin: 'modstage', surface, component: 'Pane', requestId: 'modstage',
      props: {} as any, viewport: { columns: 110, rows: 40 },
    })
    await ui.press({ key: 'pick:claude' })
    await ui.press({ key: 'model:haiku' })
    await ui.input({ key: 'launch-task:claude', text: 'list the TODOs in this repo' })
    expect(posted).toHaveLength(0)
    expect(spawned).toHaveLength(1)
    expect(spawned[0].model).toBe('haiku')
    expect(spawned[0].cwd).toBe('/home/test/project')
    // agentId is set by the engine alone, so a faked spawn starts none: the panel must say so
    // rather than open a tab it cannot message. The live check covers a real spawn's tab.
    expect(((globalThis as any).toasts ?? []).some((t: string) => /did not start a subagent/.test(t))).toBe(true)
    expect(await ui.find({ key: 'say:claude:undefined' })).toBeUndefined()
    await ui.unmount()
  })
}
