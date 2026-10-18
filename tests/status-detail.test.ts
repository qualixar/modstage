import { expect, test } from 'claude-code/testing'
import { fakeBridge } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'
import { stepLine } from '../hooks/register.tsx'

// Claude reads a run through stage_status / stage_wait. It saw only each step's first 200 characters; it now sees
// what came of the step, and with detail:true the agent's whole detail (fenced, as the agent's own words).

const out = (r: any) => (r?.text ?? r?.content?.[0]?.text ?? JSON.stringify(r))
const DIFF = '--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n-old\n+new\n+newer'

test('a step shows what came of it, and detail:true adds the full detail', () => {
  expect(stepLine({ seq: 1, ts: 0, kind: 'edit', text: 'edited a.py', detail: DIFF })).toContain('(+2 -1)')
  expect(stepLine({ seq: 2, ts: 0, kind: 'result', text: 'exit 1', detail: 'FAIL one\nTypeError: bad' })).toContain('TypeError: bad')
  expect(stepLine({ seq: 1, ts: 0, kind: 'edit', text: 'edited a.py', detail: DIFF })).not.toContain('@@')
  expect(stepLine({ seq: 1, ts: 0, kind: 'edit', text: 'edited a.py', detail: DIFF }, true)).toContain('  │ +newer')
  expect(stepLine({ seq: 3, ts: 0, kind: 'message', text: 'hello' })).toBe('  [message] hello')
})

test('stage_status passes the detail flag through to what Claude reads', async ($, on) => {
  const run = { id: 'r1', engine: 'codex', status: 'idle', activity: 'idle', owner: 'sess-A', pending: [], elapsed_s: 3, autonomy: 'ask',
    usage: { input: 0, cached: 0, output: 0, reasoning: 0, context_used: 0, context_window: null, cost_usd: null },
    events_log: [{ seq: 1, ts: 0, kind: 'edit', text: 'edited a.py', detail: DIFF }] }
  const b: Bridge = { runs: { r1: run }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  const plain = out(await $.tool.call({ tool: 'mcp__modstage__stage_status', run_id: 'r1' } as any))
  expect(plain).toContain('(+2 -1)')
  expect(plain).not.toContain('+newer')
  const full = out(await $.tool.call({ tool: 'mcp__modstage__stage_status', run_id: 'r1', detail: true } as any))
  expect(full).toContain('+newer')
})
