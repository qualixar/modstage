import { expect, mock, test } from 'claude-code/testing'

// Draw the panel and the above-prompt band through the engine on each surface that can show them.
// The engine validates every tree against the surface's element table, so a bad prop fails here.
for (const surface of ['desktop', 'terminal'] as const) {
  test(`ModStage panel draws on ${surface}`, async ($, on) => {
    mock.env(on, { HOME: '/home/test' })
    const ui: any = await $.ui.mount({
      plugin: 'modstage', surface, component: 'Pane', requestId: 'modstage',
      props: {} as any, viewport: { columns: 110, rows: 40 },
    })
    expect(ui).toBeTruthy()
    await ui.unmount()
  })

  test(`entry band draws above the prompt on ${surface}`, async ($, on) => {
    mock.env(on, { HOME: '/home/test' })
    const ui: any = await $.ui.mount({
      plugin: 'modstage', surface, component: 'AbovePrompt',
      props: { hasSurvey: false } as any, viewport: { columns: 110, rows: 3 },
    })
    expect(ui).toBeTruthy()
    await ui.unmount()
  })
}

// The full view with runs: tabs, robot, transcript, composer. Drawn by a test hook on its own pane id,
// so the engine validates exactly the tree drawStage returns.
import { drawStage } from '../hooks/ui/stage.tsx'
import type { StageProps } from '../hooks/ui/stage.tsx'

const usage = { input: 82000, cached: 48000, output: 300, reasoning: 0, context_used: 41000, context_window: 828000, cost_usd: null }
const PROPS: StageProps = {
  runs: [
    { id: 'aaaa1111', engine: 'codex', model: 'gpt-6-luna', label: 'Fizzbuzz in Python', cwd: '/home/test/demo', status: 'running', activity: 'running: python3 fizzbuzz.py', elapsed_s: 12, usage, error: null },
    { id: 'bbbb2222', engine: 'muse', model: 'muse-spark-1.3', label: 'Word counter', cwd: '/home/test/demo', status: 'idle', activity: 'idle', elapsed_s: 40, usage: { ...usage, cost_usd: 0.0067 }, error: null },
    { id: 'cccc3333', engine: 'grok', model: 'grok-4.7', label: 'Primes check', cwd: '/home/test/demo', status: 'error', activity: 'failed', elapsed_s: 9, usage: { ...usage, cost_usd: 0.73 }, error: 'boom' },
  ],
  selected: 'aaaa1111',
  feed: [
    { seq: 1, kind: 'you', text: 'Write fizzbuzz.py and run it.' },
    { seq: 2, kind: 'tool', text: '$ python3 fizzbuzz.py' },
    { seq: 3, kind: 'result', text: 'exit 0', detail: '28\nFizz' },
    { seq: 4, kind: 'thinking', text: 'Checking the output' },
    { seq: 5, kind: 'edit', text: 'edited fizzbuzz.py' },
    { seq: 6, kind: 'message', text: 'Done: FizzBuzz printed for 1 to 30.' },
  ],
  partial: '',
  age: 1,
  problem: '',
  home: '/home/test',
  canType: true,
}

for (const surface of ['desktop', 'terminal'] as const) {
  for (const tick of [0, 7, 33]) {
    test(`full view with runs draws on ${surface} (frame ${tick})`, async ($, on) => {
      on('ui.render', { component: 'Pane', requestId: 'view-test' } as any, async ($$: any, e: any) =>
        drawStage($$.ui.resolve(e), PROPS, tick, {}, () => {}))
      const ui: any = await $.ui.mount({
        plugin: 'modstage', surface, component: 'Pane', requestId: 'view-test',
        props: {} as any, viewport: { columns: 120, rows: 44 },
      })
      expect(ui).toBeTruthy()
      await ui.unmount()
    })
  }
}


// Native parts with data: inbox cards, open launcher, setup list, message box (steerable, queued, watch-only).
import { drawComposer, drawInbox, drawLauncher, drawSetup } from '../hooks/ui/native.tsx'

const AGENTS = [
  { id: 'codex', name: 'Codex', color: '#7AA2F7', protocol: 'codex-app-server', steer: 'native', installed: true, version: 'codex-cli 0.156.0', command: 'codex app-server', note: '' },
  { id: 'grok', name: 'Grok', color: '#E0AF68', protocol: 'acp', steer: 'queue', installed: true, version: 'grok 1.0.60', command: 'grok agent stdio', note: 'auto-approves every action', takes_model: true, default_model: 'grok-4.7', models: [{ id: 'grok-4.7', label: 'grok-4.7' }, { id: 'grok-4.6', label: 'grok-4.6' }] },
  { id: 'kimi', name: 'Kimi', color: '#F5C2E7', protocol: 'acp', steer: 'queue', installed: false, version: '', command: 'kimi acp', note: '' },
]
const PENDING = [
  { id: 'a1', run_id: 'aaaa1111', engine: 'codex', kind: 'command', title: 'run `curl -sI https://example.com`', detail: 'network access', warning: '', asked_at: Date.now() / 1000 - 30 },
  { id: 'a2', run_id: 'cccc3333', engine: 'grok', kind: 'edit', title: 'change src/app.py', detail: '', warning: 'src/app.py is claimed by codex run aaaa1111', asked_at: Date.now() / 1000 - 5 },
]

for (const surface of ['desktop', 'terminal'] as const) {
  test(`inbox, launcher, setup and composers draw on ${surface}`, async ($, on) => {
    on('ui.render', { component: 'Pane', requestId: 'native-test' } as any, async ($$: any, e: any) => {
      const el = $$.ui.resolve(e)
      const { Box } = el
      const steerable = { ...PROPS.runs[0]!, color: '#7AA2F7', steer: 'native' } as any
      const queued = { ...PROPS.runs[2]!, color: '#E0AF68', steer: 'queue', status: 'running' } as any
      const watch = { ...PROPS.runs[0]!, id: 'claude:x', engine: 'claude', steer: 'watch' } as any
      return (
        <Box flexDirection="column">
          {drawInbox(el, PENDING as any, { codex: '#7AA2F7', grok: '#E0AF68' }, () => {})}
          {drawLauncher(el, AGENTS as any, 'grok', 'grok-4.6', true, () => {})}
          {drawLauncher(el, AGENTS as any, '', '', true, () => {})}
          {drawSetup(el, AGENTS as any)}
          {drawComposer(el, steerable, true, () => {})}
          {drawComposer(el, queued, true, () => {})}
          {drawComposer(el, watch, true, () => {})}
        </Box>
      )
    })
    const ui: any = await $.ui.mount({
      plugin: 'modstage', surface, component: 'Pane', requestId: 'native-test',
      props: {} as any, viewport: { columns: 120, rows: 60 },
    })
    expect(ui).toBeTruthy()
    await ui.unmount()
  })
}


// ---- A: the Needs-you card is reachable wherever the panel is scrolled ----
import { ask, fakeBridge, runWith } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'
import { revealInbox } from '../hooks/register.tsx'

test('revealInbox scrolls the pane to the Needs-you card, and a closed pane is not an error', async () => {
  const asked: any[] = []
  await revealInbox({ ui: { scroll: async (a: any) => { asked.push(a); return {} } } })
  expect(asked).toEqual([{ to: { key: 'inbox' }, in: 'modstage', block: 'start' }])
  await revealInbox({ ui: { scroll: async () => { throw new Error('no pane') } } })
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`a new approval is announced and the band's "needs you" opens the pane at the card (${surface})`, async ($, on) => {
    const b: Bridge = { runs: { r1: runWith([ask('a1', 'run `curl a`'), ask('a2', 'run `pip install x`')]) }, decided: [], session: 'sess-A' }
    fakeBridge(on, b)
    let opened = 0
    on('ui.open', () => {
      opened += 1
      return { value: { isPlaced: true } }
    })
    // deciding one approval refreshes the panel; the other is new to it: revealInbox runs and it is announced
    await $.tool.call({ tool: 'mcp__modstage__stage_decide', run_id: 'r1', approval_id: 'a1', choice: 'deny' } as any)
    expect((b.toasts ?? []).some(t => t.includes('codex needs you') && t.includes('pip install x'))).toBe(true)

    const band: any = await $.ui.mount({
      plugin: 'modstage', surface, component: 'AbovePrompt',
      props: { hasSurvey: false } as any, viewport: { columns: 110, rows: 3 },
    })
    const needs = await band.find({ key: 'band-needs' })
    expect(needs).toBeTruthy()  // the old band drew this as plain text: nothing to press
    expect(String(needs.props.label)).toContain('1 needs you')
    await band.press({ key: 'band-needs' })
    expect(opened).toBeGreaterThan(0)
    await band.unmount()
  })

  // ---- C3: free text is never an approval ----
  test(`the message box refuses free text while an approval is pending (${surface})`, async ($, on) => {
    const waiting = { ...PROPS.runs[0]!, color: '#7AA2F7', steer: 'native', pending: [PENDING[0]] } as any
    const free = { ...PROPS.runs[0]!, color: '#7AA2F7', steer: 'native', pending: [] } as any
    on('ui.render', { component: 'Pane', requestId: 'composer-test' } as any, async ($$: any, e: any) => {
      const el = $$.ui.resolve(e)
      return <el.Box flexDirection="column">{drawComposer(el, waiting, true, () => {})}</el.Box>
    })
    on('ui.render', { component: 'Pane', requestId: 'composer-free' } as any, async ($$: any, e: any) => {
      const el = $$.ui.resolve(e)
      return <el.Box flexDirection="column">{drawComposer(el, free, true, () => {})}</el.Box>
    })
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'composer-test',
      props: {} as any, viewport: { columns: 120, rows: 20 } })
    expect(await ui.find({ key: `say:${waiting.id}` })).toBeUndefined()
    expect(await ui.find({ text: /Answer the approval above first/ })).toBeTruthy()
    await ui.unmount()
    const ui2: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'composer-free',
      props: {} as any, viewport: { columns: 120, rows: 20 } })
    expect(await ui2.find({ key: `say:${free.id}` })).toBeTruthy()
    await ui2.unmount()
  })
}
