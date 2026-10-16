import { expect, test } from 'claude-code/testing'
import { ask, fakeBridge, runWith } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'
import { drawComposer } from '../hooks/ui/native.tsx'

const out = (res: any) => String(res?.result ?? res?.text ?? res?.deny ?? '')

test('stage_send passes images and "now" to the bridge', async ($, on) => {
  const b: Bridge = { runs: { r1: runWith([]) }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  await $.tool.call({ tool: 'mcp__modstage__stage_send', run_id: 'r1', text: 'look', now: true, images: ['/tmp/a.png'] } as any)
  expect(b.sent).toEqual([{ text: 'look', now: true, images: ['/tmp/a.png'], session: 'sess-A' }])
})

test('stage_wait can wait through approvals, and says waiting_on_user when it returns for one', async ($, on) => {
  const b: Bridge = { runs: { r1: runWith([ask('a1', 'run `pip install x`')]) }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  const first = await $.tool.call({ tool: 'mcp__modstage__stage_wait', run_id: 'r1' } as any)
  expect(out(first)).toContain('waiting_on_user: yes')
  expect(out(first)).toContain('approval_id a1')
  await $.tool.call({ tool: 'mcp__modstage__stage_wait', run_id: 'r1', until: 'turn_end' } as any)
  expect(b.waits?.[0]).not.toContain('until=turn_end')
  expect(b.waits?.[1]).toContain('until=turn_end')
})

const base = {
  id: 'q1', engine: 'grok', name: 'Grok', color: '#E0AF68', steer: 'queue', model: null, label: 'x', cwd: '/home/test',
  status: 'running', activity: 'thinking', elapsed_s: 5, events: 1, error: null, pending: [],
  usage: { input: 0, cached: 0, output: 0, reasoning: 0, context_used: 0, context_window: null, cost_usd: null },
}

for (const surface of ['desktop', 'terminal'] as const) {
  test(`a queued message shows "1 queued" and an "Interrupt and send now" button that jumps (${surface})`, async ($, on) => {
    const acts: any[] = []
    on('ui.render', { component: 'Pane', requestId: 'queued' } as any, async ($$: any, e: any) => {
      const el = $$.ui.resolve(e)
      return <el.Box flexDirection="column">{drawComposer(el, { ...base, queued: 1 } as any, true, a => acts.push(a))}</el.Box>
    })
    on('ui.render', { component: 'Pane', requestId: 'not-queued' } as any, async ($$: any, e: any) => {
      const el = $$.ui.resolve(e)
      return <el.Box flexDirection="column">{drawComposer(el, { ...base, queued: 0 } as any, true, () => {})}</el.Box>
    })
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'queued',
      props: {} as any, viewport: { columns: 120, rows: 20 } })
    expect(await ui.find({ text: /1 queued · runs when the turn ends/ })).toBeTruthy()
    // this tree is drawn by the test's own render hook, so the press names the test as its plugin
    await ui.press({ key: 'jump', plugin: 'test' })
    expect(acts).toEqual([{ type: 'jump', id: 'q1' }])
    await ui.unmount()
    const ui2: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'not-queued',
      props: {} as any, viewport: { columns: 120, rows: 20 } })
    expect(await ui2.find({ key: 'jump' })).toBeUndefined()
    await ui2.unmount()
  })
}
