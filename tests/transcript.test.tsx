import { expect, test } from 'claude-code/testing'
import { fakeBridge } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'
import { followsLatest, rowKey } from '../hooks/ui/transcript.tsx'

// The transcript lives in the pane body (not in a Client) so the engine scrolls it. It must show what the
// agent reported in full, expand a tool's whole output, page back through older events, and follow new
// output only while the person has not scrolled up.

const usage = { input: 1, cached: 0, output: 1, reasoning: 0, context_used: 1, context_window: 100, cost_usd: null }
const LONG = 'The quick brown fox jumps over the lazy dog. '.repeat(40) // 1800 characters, far past the old 400-character cut
const OUTPUT = Array.from({ length: 30 }, (_, i) => `output line ${i}`).join('\n')

const events = [
  { seq: 1, kind: 'you', text: 'Repair the failing pipeline' },
  ...Array.from({ length: 150 }, (_, i) => ({ seq: 2 + i, kind: 'thinking', text: `thought ${i}` })),
  { seq: 152, kind: 'tool', text: '$ npm test', detail: OUTPUT },
  { seq: 153, kind: 'edit', text: 'edited app.py', detail: '--- a/app.py\n+++ b/app.py\n-old line\n+new line' },
  { seq: 154, kind: 'message', text: LONG },
]
const run = { id: 'r1', engine: 'codex', model: null, label: 'Fix the build', cwd: '/home/test', status: 'idle', activity: 'idle', elapsed_s: 5,
  usage, error: null, owner: 'sess-A', steer: 'native', pending: [], events_log: events }

for (const surface of ['desktop', 'terminal'] as const) {
  test(`the transcript shows full messages, expands tool output and pages back (${surface})`, async ($, on) => {
    const b: Bridge = { runs: { r1: run }, decided: [], session: 'sess-A' }
    fakeBridge(on, b)
    on('ui.open', () => ({ value: undefined }))
    await $.tool.call({ tool: 'mcp__modstage__stage_start', engine: 'codex', prompt: 'x' } as any) // its poll fills the panel
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'modstage',
      props: {} as any, viewport: { columns: 120, rows: 30 } })
    // the head: a vector picture on the desktop, an animated Client in the terminal (its module must load and draw)
    if (surface === 'desktop') expect(await ui.find({ type: 'Svg' })).toBeTruthy()
    else expect(await ui.drawn({ in: 'stage' })).toBeTruthy()
    // a message longer than the old 400-character cut is shown whole
    expect(await ui.find({ text: new RegExp(LONG.trim().slice(-60)) })).toBeTruthy()
    // the newest page holds 120 events: the oldest are behind "earlier"
    expect(await ui.find({ key: 'earlier-btn' })).toBeTruthy()
    expect(await ui.find({ text: /thought 149/ })).toBeTruthy()
    expect(await ui.find({ text: /Repair the failing pipeline/ })).toBeUndefined()
    await ui.press({ key: 'earlier-btn' })
    expect(await ui.find({ text: /Repair the failing pipeline/ })).toBeTruthy()
    // a tool's output is one dim line until expanded, then every line
    expect(await ui.find({ text: /output line 29/ })).toBeUndefined()
    await ui.press({ key: `x:${rowKey('r1', 152)}` })
    expect(await ui.find({ text: /output line 29/ })).toBeTruthy()
    await ui.press({ key: `x:${rowKey('r1', 152)}` })
    expect(await ui.find({ text: /output line 29/ })).toBeUndefined()
    await ui.unmount()
  })
}

test('the pane follows new output only while the window sits at its end', () => {
  expect(followsLatest(0, 40, 30)).toBe(true)     // everything fits
  expect(followsLatest(60, 40, 100)).toBe(true)   // at the end
  expect(followsLatest(59, 40, 100)).toBe(true)   // one row short still counts as the end
  expect(followsLatest(20, 40, 100)).toBe(false)  // scrolled up
})
