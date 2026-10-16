import { expect, test } from 'claude-code/testing'
import { fakeBridge } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'
import { drawComposer } from '../hooks/ui/native.tsx'
import { drawStage } from '../hooks/ui/stage.tsx'
import { startDescription } from '../hooks/register.tsx'

// Antigravity ask runs are read-only; a refusal ends the turn blocked and must say what and why (run 120c4f36).

const out = (res: any) => String(res?.result ?? res?.text ?? res?.deny ?? '')
const usage = { input: 0, cached: 0, output: 0, reasoning: 0, context_used: 0, context_window: null, cost_usd: null }
const BLOCKED = 'refused a shell command: run_command echo hi. agy cannot ask for permission. To let it proceed, ' +
  'start a new run with autonomy "auto", ideally in an isolated folder (auto allows everything)'
const agyRun = () => ({
  id: 'g1', engine: 'antigravity', name: 'Antigravity', color: '#8AB4F8', steer: 'queue', model: null, label: 'research',
  cwd: '/home/test/demo', status: 'idle', activity: 'blocked: ' + BLOCKED, elapsed_s: 30, events: 4, error: null,
  autonomy: 'ask', owner: 'sess-A', pending: [], blocked: BLOCKED, usage,
  approval_note: 'headless agy cannot ask for permission. Ask mode is read-only',
})

for (const tool of ['stage_wait', 'stage_status'] as const) {
  test(`${tool} says plainly what agy refused and how to let it proceed`, async ($, on) => {
    const b: Bridge = { runs: { g1: agyRun() }, decided: [], session: 'sess-A' }
    fakeBridge(on, b)
    const text = out(await $.tool.call({ tool: `mcp__modstage__${tool}`, run_id: 'g1' } as any))
    expect(text).toContain('BLOCKED (turn ended): refused a shell command: run_command echo hi')
    expect(text).toContain('autonomy "auto", ideally in an isolated folder')
    expect(text).toContain('read-only (cannot ask)')
  })
}

test('stage_start tells Claude that antigravity ask runs are read-only and when to use auto', () => {
  const d = startDescription(['codex', 'antigravity'])
  expect(d).toContain('Antigravity (headless agy) cannot ask')
  expect(d).toContain('read-only (web pages, web search, files in its cwd)')
  expect(d).toContain('autonomy "auto", ideally in an isolated folder')
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`the composer shows a blocked turn and its way out (${surface})`, async ($, on) => {
    on('ui.render', { component: 'Pane', requestId: 'blocked' } as any, async ($$: any, e: any) => {
      const el = $$.ui.resolve(e)
      return <el.Box flexDirection="column">{drawComposer(el, agyRun() as any, true, () => {})}</el.Box>
    })
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'blocked',
      props: {} as any, viewport: { columns: 200, rows: 20 } })
    expect(await ui.find({ text: /Turn ended blocked: refused a shell command/ })).toBeTruthy()
    expect(await ui.find({ text: /autonomy "auto", ideally in an isolated folder/ })).toBeTruthy()
    await ui.unmount()
  })

  test(`the run card marks a blocked agy run (${surface})`, async ($, on) => {
    const props = { runs: [agyRun() as any], selected: 'g1', feed: [], partial: '', age: 1, problem: '',
      home: '/home/test', canType: true }
    on('ui.render', { component: 'Pane', requestId: 'card' } as any, async ($$: any, e: any) =>
      drawStage($$.ui.resolve(e), props as any, 0, {}, () => {}))
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'card',
      props: {} as any, viewport: { columns: 200, rows: 44 } })
    expect(await ui.find({ text: /blocked: refused a shell command/ })).toBeTruthy()
    expect(await ui.find({ text: /read-only/ })).toBeTruthy()
    await ui.unmount()
  })
}
