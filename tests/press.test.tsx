import { expect, test } from 'claude-code/testing'
import { ANSWER_MS, clearDrafts, draftOf, drawComposer, drawInbox, pressKey, setDraft } from '../hooks/ui/native.tsx'
import { fakeBridge } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'

// 18 Oct 2026: "when someone clicks a button it should feel clicked; the text boxes should be strong". A pressed button
// says what it is doing, then what it did; an answered approval leaves a confirming line. None of that may ever claim
// success for an action the bridge refused, and a message that was not sent stays in its box (found by independent review).

const usage = { input: 1, cached: 0, output: 1, reasoning: 0, context_used: 1, context_window: 100, cost_usd: null }
const ask = { id: 'a00', run_id: 'r0', engine: 'codex', kind: 'command', title: 'curl example.com', detail: 'curl -I https://example.com', warning: '', asked_at: Date.now() / 1000 }

test('each button has a slot of its own; the buttons of one run are scoped to that run', () => {
  expect(pressKey({ type: 'decide', runId: 'r', approvalId: 'a1', choice: 'allow' })).toBe('allow:a1')
  expect(pressKey({ type: 'decide', runId: 'r', approvalId: 'a1', choice: 'allow_session' })).toBe('session:a1')
  expect(pressKey({ type: 'decide', runId: 'r', approvalId: 'a1', choice: 'deny' })).toBe('deny:a1')
  expect(pressKey({ type: 'launch', engine: 'codex' })).toBe('launch-start|codex')
  expect(pressKey({ type: 'send', id: 'r1', via: 'Status?' })).toBe('q:Status?|r1')
  expect(pressKey({ type: 'send', id: 'r1' })).toBe('send-btn|r1')
  for (const t of ['interrupt', 'close', 'jump']) expect(pressKey({ type: t, id: 'r1' })).toBe(`${t}|r1`)
  expect(pressKey({ type: 'close', id: 'r1' })).not.toBe(pressKey({ type: 'close', id: 'r2' }))
  expect(pressKey({ type: 'pickAgent', engine: 'x' })).toBe('')
})

test('drafts are kept per box and an emptied box forgets its draft', () => {
  clearDrafts()
  setDraft('say:r1', 'half a message')
  setDraft('say:r2', 'another')
  expect(draftOf('say:r1')).toBe('half a message')
  expect(draftOf('say:r3')).toBe('')
  setDraft('say:r1', '')
  expect(draftOf('say:r1')).toBe('')
  expect(draftOf('say:r2')).toBe('another')
  clearDrafts()
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`a button says what it is doing, then what it did; the others stay as they were (${surface})`, async ($, on) => {
    let state: 'busy' | 'done' = 'busy'
    on('ui.render', { component: 'Pane', requestId: 'press' } as any, async ($$: any, e: any) => {
      const el = $$.ui.resolve(e)
      return <el.Box flexDirection="column">
        {drawInbox(el, [ask] as any, { codex: '#4C9BFF' }, () => {}, { 'allow:a00': state })}
      </el.Box>
    })
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'press', props: {} as any, viewport: { columns: 120, rows: 30 } })
    expect(await ui.find({ text: /Allowing…/ })).toBeTruthy()
    expect(await ui.find({ text: /✓ Allowed/ })).toBeUndefined()   // not claimed before the bridge has answered
    expect(await ui.find({ text: 'Deny' })).toBeTruthy()
    state = 'done'
    await ui.redraw()
    expect(await ui.find({ text: /✓ Allowed/ })).toBeTruthy()
    expect(await ui.find({ text: /✓ Denied/ })).toBeUndefined()
    await ui.unmount()
  })

  test(`the message box is tall, restores a draft and has a Send button (${surface})`, async ($, on) => {
    clearDrafts()
    setDraft('say:r1', 'half a message')
    const acts: any[] = []
    const run = { id: 'r1', engine: 'codex', status: 'idle', steer: 'native', color: '#4C9BFF', pending: [] } as any
    on('ui.render', { component: 'Pane', requestId: 'msg' } as any, async ($$: any, e: any) => {
      const el = $$.ui.resolve(e)
      return <el.Box flexDirection="column">{drawComposer(el, run, true, a => acts.push(a), {})}</el.Box>
    })
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'msg', props: {} as any, viewport: { columns: 120, rows: 30 } })
    const box: any = await ui.find({ key: 'say:r1' })
    expect(box).toBeTruthy()
    expect(box.props?.rows).toBe(3)
    expect(box.props?.value).toBe('half a message')
    await ui.press({ key: 'send-btn', plugin: 'test' })
    expect(acts[0]).toMatchObject({ type: 'send', id: 'r1', text: 'half a message' })
    expect(draftOf('say:r1')).toBe('half a message')   // emptied by the panel only once the bridge took it
    setDraft('say:r1', '')
    await ui.press({ key: 'send-btn', plugin: 'test' })
    expect(acts.length).toBe(1)                          // an empty box sends nothing
    await ui.unmount()
    clearDrafts()
  })
}

// ---- through the real panel and a fake bridge ------------------------------------------------------------------------
async function panel($: any, on: any, b: Bridge) {
  fakeBridge(on, b)
  on('ui.open', () => ({ value: undefined }))
  await $.tool.call({ tool: 'mcp__modstage__stage_start', engine: 'codex', prompt: 'x' } as any)
  return $.ui.mount({ plugin: 'modstage', surface: 'desktop', component: 'Pane', requestId: 'modstage', props: {} as any, viewport: { columns: 120, rows: 40 } })
}
const bridgeWith = (pending: any[]): Bridge => ({
  runs: { r0: { id: 'r0', engine: 'codex', model: null, label: 'x', cwd: '/home/test', status: 'running', activity: 'thinking', elapsed_s: 4, usage, error: null, owner: 'sess-A', steer: 'native', pending } },
  decided: [], session: 'sess-A',
})

test('answering an approval confirms it for a moment, then the line clears', async ($, on) => {
  const b = bridgeWith([ask, { ...ask, id: 'a01', title: 'second' }])
  const ui: any = await panel($, on, b)
  await ui.press({ key: 'allow:a01' })
  expect(b.decided.length).toBe(1)
  expect(await ui.find({ text: /✓ Allowed/ })).toBeTruthy()
  await b.clock.advance(ANSWER_MS + 50)
  expect(await ui.find({ text: /✓ Allowed/ })).toBeUndefined()
  await ui.unmount()
})

test('an approval the bridge refused is never shown as allowed, and its button comes back', async ($, on) => {
  const b = bridgeWith([ask, { ...ask, id: 'a01', title: 'second' }])
  b.decideFault = 'refused'
  const ui: any = await panel($, on, b)
  await ui.press({ key: 'allow:a01' })
  expect(b.decided.length).toBe(0)
  expect(await ui.find({ text: /✓ Allowed/ })).toBeUndefined()
  expect(await ui.find({ text: /Allowing…/ })).toBeUndefined()
  expect(await ui.find({ key: 'allow:a01' })).toBeTruthy()
  await ui.unmount()
})

test('a message the bridge took empties its box; one it refused stays in the box', async ($, on) => {
  const b = bridgeWith([])
  const ui: any = await panel($, on, b)
  const valueOf = async () => { await ui.redraw(); return ((await ui.find({ key: 'say:r0' })) as any)?.props?.value }
  await ui.input({ key: 'say:r0', text: 'hello there', kind: 'change' })   // typing: the draft is kept
  expect(await valueOf()).toBe('hello there')
  await ui.input({ key: 'say:r0', text: 'hello there' })                   // Enter: the bridge takes it
  await b.clock.advance(2000)
  expect(b.sent?.[0]).toMatchObject({ text: 'hello there' })
  expect(await valueOf()).toBeUndefined()                                   // sent: the box is empty again
  b.failSend = true                                                         // the bridge refuses the next send
  await ui.input({ key: 'say:r0', text: 'try again', kind: 'change' })
  await ui.input({ key: 'say:r0', text: 'try again' })
  await b.clock.advance(2000)
  expect(await valueOf()).toBe('try again')                                 // not sent, not lost
  await ui.unmount()
})
