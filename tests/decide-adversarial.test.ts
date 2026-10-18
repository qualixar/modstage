import { expect, test } from 'claude-code/testing'
import { ask, fakeBridge, runWith, userSays } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'
import { boundTo, decisionIn } from '../hooks/decision.ts'

// Found by an independent adversarial review of the approval gate (18 Oct 2026), after two upstream review rounds
// that each found a way for one message to approve two actions. Two classes: (H1) words the user did not say were
// read as a decision, (H2) a message was never tied to the approval it answers.

const decide = ($: any, input: any) => $.tool.call({ tool: 'mcp__modstage__stage_decide', ...input } as any)
const out = (res: any) => String(res?.result ?? res?.text ?? res?.deny ?? '')
const ago = () => Date.now() / 1000 - 5
const one = () => ({ runs: { r1: runWith([{ ...ask('a1', 'run `pip install x`'), asked_at: ago() }]) }, decided: [], session: 'sess-A' }) as Bridge
const two = () => {
  const b = one()
  b.runs.r2 = { ...runWith([{ ...ask('a2', 'run `rm -rf build`'), run_id: 'r2', asked_at: ago() }]), id: 'r2' }
  return b
}

// ---- H1: a message is a decision only when the whole message is one ----

test('H1 the ordinary ways of answering still work', () => {
  for (const said of ['allow it', 'Allow it.', 'yes allow it', 'ok, allow it', 'allow', 'approve it', 'accept it', 'please allow it',
    'allow it please', 'allow it once', 'allow it this time', 'allow the pip install', 'yes allow the pip install', 'allow pip install', 'allow codex'])
    expect(decisionIn(said), said).toBe('allow')
  for (const said of ['allow it for the rest of this run', 'always allow it', 'yes, allow it for this run', 'allow the curl every time',
    'allow it for this session', 'allow it for the whole run', 'allow it from now on'])
    expect(decisionIn(said), said).toBe('allow_session')
  for (const said of ['deny', 'deny it', 'no', 'No.', 'nope', "no, don't run that", "don't allow it", 'reject it', 'deny the curl', 'deny curl', 'block it', 'please deny it'])
    expect(decisionIn(said), said).toBe('deny')
})

// A bare yes can answer any question Claude asked, and an agent can steer Claude into asking one: it is not an approval.
test('H1 a bare "yes", "ok", "sure" or "go ahead" is not an approval', () => {
  for (const said of ['yes', 'Yes!', 'ok', 'okay', 'sure', 'yeah', 'go ahead', 'proceed', 'do it', 'run it', 'yes, go ahead', 'sounds good'])
    expect(decisionIn(said), said).toBe('')
})

test('H1 negations, questions, qualifications and extra words decide nothing', () => {
  for (const said of [
    'allow it just this once, not for the rest of this run', 'allow it once, not every time', 'never allow that', 'I would not approve this',
    'should I allow it? what does it do?', 'ok, what is it asking for?', "don't deny it", 'it keeps asking every time, ok allow it',
    'I read all of it, allow', 'yes and no', 'allow it but only the first one', 'what time is it', 'sure, after you explain it',
    'allow it, then delete everything', 'ok ' + 'x'.repeat(150), '', 'yes?', 'allow the not safe thing',
    // an object may not carry a second decision, a conjunction or a negation
    'allow the push then deny', 'allow the curl but stop', 'allow the deny', 'approve the edit cancel rest', 'deny the allow', 'allow nothing',
    'allow none of it', 'allow it without asking', 'allow the', 'allow it if safe',
  ]) expect(decisionIn(said), said).toBe('')
})

// every message below must pass nothing: the choice Claude would pass is not what was said
for (const [said, choice] of [
  ['allow it just this once, not for the rest of this run', 'allow_session'], ['never allow that', 'allow'],
  ['should I allow it? what does it do?', 'allow'], ["don't deny it", 'deny'], ['I read all of it, allow', 'allow_session'],
] as const) {
  test(`H1 "${said}" cannot pass ${choice}`, async ($, on) => {
    const b = one()
    fakeBridge(on, b)
    await userSays($, said)
    await decide($, { run_id: 'r1', choice })
    expect(b.decided).toEqual([])
  })
}

// ---- H2: a message answers only the approval it was sent for ----

test('H2 with one approval waiting, the message answers it', async ($, on) => {
  const b = one()
  fakeBridge(on, b)
  await userSays($, 'allow it')
  await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided.map(d => d.approval_id)).toEqual(['a1'])
})

test('H2 with two waiting, "yes allow it" names neither: refused, and Claude is told how to ask', async ($, on) => {
  const b = two()
  fakeBridge(on, b)
  await userSays($, 'yes allow it')
  const res = await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided).toEqual([])
  expect(out(res)).toContain('does not say which approval')
  expect(out(res)).toContain('Nothing was decided')
})

test('H2 "allow the pip install" cannot approve the rm in another run', async ($, on) => {
  const b = two()
  fakeBridge(on, b)
  await userSays($, 'allow the pip install')
  const res = await decide($, { run_id: 'r2', choice: 'allow' })
  expect(b.decided).toEqual([])
  expect(out(res)).toContain('Nothing was decided')
  await decide($, { run_id: 'r1', choice: 'allow' })                       // and it does answer the one it names
  expect(b.decided.map(d => d.approval_id)).toEqual(['a1'])
})

test('H2 a refused (already answered elsewhere) approval does not free the message for a different one', async ($, on) => {
  const b = two()
  fakeBridge(on, b)
  await userSays($, 'yes allow the pip install')
  b.decideFault = 'refused'
  await decide($, { run_id: 'r1', choice: 'allow' })                       // the panel got there first: the bridge says 404
  b.decideFault = undefined
  await decide($, { run_id: 'r2', choice: 'allow' })                       // the same message must not approve the rm
  expect(b.decided).toEqual([])
})

test('H2 a message arriving while a decision is in flight is neither spent nor freed by it', async ($, on) => {
  const b = two()
  fakeBridge(on, b)
  await userSays($, 'yes allow the pip install')
  b.decideFault = 'refused'
  const first = decide($, { run_id: 'r1', choice: 'allow' })
  await userSays($, 'deny the rm')
  await first
  b.decideFault = undefined
  await decide($, { run_id: 'r2', choice: 'deny' })                        // the new message is intact and answers r2
  expect(b.decided.map(d => [d.approval_id, d.choice])).toEqual([['a2', 'deny']])
})

test('H2 if the bridge cannot be asked when the user speaks, nothing is guessed', async ($, on) => {
  const b = one()
  fakeBridge(on, b)
  b.inboxDown = true
  await userSays($, 'allow it')                                            // bound to nothing
  b.inboxDown = false
  const res = await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided).toEqual([])
  expect(out(res)).toContain('does not say which approval')
})

test('H2 boundTo: the only waiting approval, or the one the message alone names', () => {
  const w = [{ id: 'a1', run_id: 'r1', engine: 'codex', title: 'run `pip install x`' }, { id: 'a2', run_id: 'r2', engine: 'grok', title: 'run `rm -rf build`' }]
  expect(boundTo('allow it', [w[0]!])).toBe('a1')
  expect(boundTo('allow it', w)).toBe('')
  expect(boundTo('allow the pip install', w)).toBe('a1')
  expect(boundTo('deny the rm', w)).toBe('a2')
  expect(boundTo("deny grok's one", w)).toBe('')                            // grok's, not grok: no loose matching
  expect(boundTo('allow the pip rm', w)).toBe('')                           // names both: ambiguous, so none
})


// ---- round 2 of the adversarial review: what the first patch still let through ----

const sole = (id: string, title: string, run = 'r1') => ({ runs: { [run]: { ...runWith([{ ...ask(id, title), run_id: run, asked_at: ago() }]), id: run } }, decided: [], session: 'sess-A' }) as Bridge
const pair = (t1: string, t2: string) => ({ runs: {
  r1: runWith([{ ...ask('a1', t1), asked_at: ago() }]),
  r2: { ...runWith([{ ...ask('a2', t2), run_id: 'r2', asked_at: ago() }]), id: 'r2' } }, decided: [], session: 'sess-A' }) as Bridge

test('R2-A with only the rm waiting, "allow the pip install" does not allow the rm', async ($, on) => {
  const b = sole('a2', 'run `rm -rf build`', 'r2')
  fakeBridge(on, b)
  await userSays($, 'allow the pip install')
  await decide($, { run_id: 'r2', choice: 'allow' })
  expect(b.decided).toEqual([])
  await userSays($, 'allow the rm')                                         // naming the right one works
  await decide($, { run_id: 'r2', choice: 'allow' })
  expect(b.decided.map(d => d.approval_id)).toEqual(['a2'])
})

test('R2-B words the grammar itself uses ("from now on") never name an approval', async ($, on) => {
  const b = pair('run `pip install x`', 'turn on telemetry upload')
  fakeBridge(on, b)
  await userSays($, 'allow it from now on')
  await decide($, { run_id: 'r2', choice: 'allow_session' })
  await decide($, { run_id: 'r1', choice: 'allow_session' })
  expect(b.decided).toEqual([])                                             // with two waiting it names neither
})

test('R2-C a slow inbox read for an earlier message cannot overwrite a newer one', async ($, on) => {
  const b = pair('run `pip install x`', 'run `rm -rf build`')
  fakeBridge(on, b)
  let open!: () => void
  b.inboxGate = new Promise<void>(r => { open = r })
  const first = userSays($, 'allow the pip install')
  while (!b.inboxCalls) await new Promise(r => setTimeout(r, 5))
  await userSays($, 'wait, stop, I changed my mind about everything')       // no decision: written at once
  open()
  await first
  await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided).toEqual([])
})

test('R2-D a bridge that never answers the inbox does not hold the prompt, and binds nothing', async ($, on) => {
  const b = pair('run `pip install x`', 'run `rm -rf build`')
  fakeBridge(on, b)
  b.inboxGate = new Promise(() => {})
  let sent = false
  const done = userSays($, 'allow the pip install').then(() => { sent = true })
  await b.clock.settle()
  expect(sent).toBe(false)                                                   // still waiting, within its bound
  await b.clock.advance(1500)
  await done
  expect(sent).toBe(true)                                                    // the prompt went on once the bound passed
  await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided).toEqual([])                                              // and nothing was guessed
})

test('R2-F a bare "sure" in answer to some other question approves nothing', async ($, on) => {
  const b = sole('a1', 'run `rm -rf build`')
  fakeBridge(on, b)
  await userSays($, 'sure')                                                  // e.g. to "want me to summarise the diff?"
  await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided).toEqual([])
})

test('control: an approval raised while the inbox is being read is refused by the time check', async ($, on) => {
  const b = { runs: { r1: runWith([]) }, decided: [], session: 'sess-A' } as Bridge
  fakeBridge(on, b)
  let open!: () => void
  b.inboxGate = new Promise<void>(r => { open = r })
  const p = userSays($, 'allow it')
  while (!b.inboxCalls) await new Promise(r => setTimeout(r, 5))
  await new Promise(r => setTimeout(r, 5))
  b.runs.r1.pending = [{ ...ask('a1', 'run `rm -rf build`'), asked_at: Date.now() / 1000 }]
  open()
  await p
  await decide($, { run_id: 'r1', choice: 'allow' })
  expect(b.decided).toEqual([])
})

test('control: non-user origins never read the inbox', async ($, on) => {
  const b = pair('run `pip install x`', 'run `rm -rf build`')
  fakeBridge(on, b)
  for (const kind of ['peer', 'plugin', 'task-notification']) await userSays($, 'allow the pip install', kind)
  expect(b.inboxCalls ?? 0).toBe(0)
})
