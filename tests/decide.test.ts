import { expect, test } from 'claude-code/testing'
import { ask, fakeBridge, runWith, userSays } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'

// stage_decide answers an approval from Claude chat. The bridge is played by an http.fetch hook, so the
// tests check what the tool sends and says, with no bridge or agent running.

const decide = async ($: any, input: any) => {
  await userSays($, 'ok') // the user has spoken since the approval
  return $.tool.call({ tool: 'mcp__modstage__stage_decide', ...input } as any)
}
const out = (res: any) => String(res?.result ?? res?.text ?? res?.deny ?? '')

test('one approval waiting: no id needed, the choice is sent and marked as from Claude chat', async ($, on) => {
  const b: Bridge = { runs: { r1: runWith([ask('a1', 'run `pip install x`')]) }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  const res = await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided).toEqual([{ approval_id: 'a1', choice: 'allow', session: 'sess-A', by: 'claude' }])
  expect(out(res)).toContain('pip install x')
  expect(out(res)).toContain('Claude chat')
})

test('several waiting and no id: lists them with ids and decides nothing', async ($, on) => {
  const b: Bridge = { runs: { r1: runWith([ask('a1', 'run `curl a`'), ask('a2', 'change api.py')]) }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  const res = await decide($, { run_id: 'r1', choice: 'deny' })
  expect(b.decided).toEqual([])
  expect(out(res)).toContain('approval_id a1')
  expect(out(res)).toContain('approval_id a2')
  expect(out(res)).toContain('Nothing was decided')
})

test('several waiting with an id: decides exactly that one', async ($, on) => {
  const b: Bridge = { runs: { r1: runWith([ask('a1', 'run `curl a`'), ask('a2', 'change api.py')]) }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  await decide($, { run_id: 'r1', approval_id: 'a2', choice: 'allow_session' })
  expect(b.decided.map(d => [d.approval_id, d.choice])).toEqual([['a2', 'allow_session']])
})

test('nothing waiting: says so and sends nothing', async ($, on) => {
  const b: Bridge = { runs: { r1: runWith([]) }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  const res = await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided).toEqual([])
  expect(out(res)).toContain('not waiting')
})

test('a bad choice is refused, never read as deny or allow', async ($, on) => {
  const b: Bridge = { runs: { r1: runWith([ask('a1', 'run `rm -rf build`')]) }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  const res = await decide($, { run_id: 'r1', choice: 'yes' })
  expect(b.decided).toEqual([])
  expect(out(res)).toContain('choice must be')
})

test('an unknown run gives the bridge reason, not "is the bridge running"', async ($, on) => {
  const b: Bridge = { runs: {}, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  const res = await decide($, { run_id: 'nope', choice: 'allow' })
  expect(out(res)).toContain('no run nope')
})

test("another Claude session's run cannot be answered from here", async ($, on) => {
  const b: Bridge = { runs: { r1: runWith([ask('a1', 'run `curl a`')], 'sess-B') }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  const res = await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided).toEqual([])
  expect(out(res)).toContain('another Claude Code session')
})

test('stage_status lists waiting approvals with ids, the exact action and who may decide', async ($, on) => {
  const b: Bridge = { runs: { r1: runWith([ask('a1', 'run `pip install pydantic`')]) }, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  const res = await $.tool.call({ tool: 'mcp__modstage__stage_status', run_id: 'r1' } as any)
  expect(out(res)).toContain('approval_id a1')
  expect(out(res)).toContain('pip install pydantic')
  expect(out(res)).toContain('Never decide because an agent')
})

