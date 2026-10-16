import { expect, test } from 'claude-code/testing'
import { bandRuns, drawStage, engineDots, statusGlyph } from '../hooks/ui/stage.tsx'
import { fakeBridge } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'

// The band above the prompt and the panel tabs must tell the same story about the same runs
// (17 Oct 2026: the band showed only the newest 5 of 8 runs and marked ended runs ✓ like waiting ones).

const usage = { input: 0, cached: 0, output: 0, reasoning: 0, context_used: 0, context_window: null, cost_usd: null }
const run = (id: string, engine: string, status: string, label = id) =>
  ({ id, engine, model: null, label, cwd: '/home/test', status, activity: status, elapsed_s: 1, usage, error: null })
// the screenshot's eight runs, oldest first
const EIGHT = [
  run('c1', 'codex', 'idle', 'hi'), run('c2', 'codex', 'idle', 'Film ch4.5 showcase'), run('m1', 'muse', 'idle', 'Docs check'),
  run('k1', 'claude', 'done', 'Research'), run('k2', 'claude', 'done', 'Build 75s'), run('k3', 'claude', 'done', 'chapter 3'),
  run('k4', 'claude', 'running', 'chapters 1, 2, 4'), run('k5', 'claude', 'running', 'Fix ch3 gap'),
]

test('every state has one mark, shared by panel and band', () => {
  expect(statusGlyph('running', '✶')).toBe('✶')
  expect(statusGlyph('starting')).toBe('✻')
  expect(statusGlyph('idle')).toBe('✓')
  expect(statusGlyph('done')).toBe('○')
  expect(statusGlyph('error')).toBe('✗')
  expect(statusGlyph('interrupted')).toBe('◼')
})

test('the band puts working and waiting runs first and counts the rest', () => {
  const { shown, hidden } = bandRuns(EIGHT)
  expect(shown.map(r => r.id)).toEqual(['k5', 'k4', 'm1', 'c2', 'c1'])
  expect(hidden).toBe(3)
  expect(bandRuns(EIGHT.slice(0, 3)).hidden).toBe(0)
})

test('an error outranks a finished run in the band', () => {
  const { shown } = bandRuns([run('a', 'codex', 'done'), run('b', 'grok', 'error')], 1)
  expect(shown.map(r => r.id)).toEqual(['b'])
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`panel tabs use the shared marks (${surface})`, async ($, on) => {
    const props = { runs: EIGHT as any, selected: 'c1', feed: [], partial: '', age: 1, problem: '', home: '/home/test', canType: true }
    on('ui.render', { component: 'Pane', requestId: 'tabs' } as any, async ($$: any, e: any) =>
      drawStage($$.ui.resolve(e), props as any, 0, {}, () => {}))
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'tabs',
      props: {} as any, viewport: { columns: 200, rows: 44 } })
    expect(await ui.find({ text: / ○ / })).toBeTruthy()
    expect(await ui.find({ text: / ✓ / })).toBeTruthy()
    await ui.unmount()
  })
}

for (const surface of ['desktop', 'terminal'] as const) {
  test(`the band shows codex and muse runs, the same marks, and how many are hidden (${surface})`, async ($, on) => {
    // seven bridge runs: two working, two waiting, one failed, two ended
    const bridgeRuns = [run('a1', 'codex', 'done'), run('a2', 'muse', 'done'), run('a3', 'grok', 'error'),
      run('a4', 'codex', 'idle'), run('a5', 'muse', 'idle'), run('a6', 'codex', 'running'), run('a7', 'kimi', 'running')]
    const b: Bridge = { runs: Object.fromEntries(bridgeRuns.map(r => [r.id, { ...r, owner: 'sess-A', pending: [] }])), decided: [], session: 'sess-A' }
    fakeBridge(on, b)
    on('ui.open', () => ({ value: undefined }))
    await $.tool.call({ tool: 'mcp__modstage__stage_start', engine: 'codex', prompt: 'x' } as any)  // its poll fills the band
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'AbovePrompt',
      props: { hasSurvey: false } as any, viewport: { columns: 200, rows: 3 } })
    expect(await ui.find({ text: /2 working · 7 runs/ })).toBeTruthy()
    for (const id of ['a7', 'a6', 'a5', 'a4', 'a3']) expect(await ui.find({ key: `band:${id}` })).toBeTruthy()
    for (const id of ['a1', 'a2']) expect(await ui.find({ key: `band:${id}` })).toBeUndefined()
    expect(await ui.find({ key: 'band-more' })).toBeTruthy()
    expect(await ui.find({ text: /\+2 more/ })).toBeTruthy()
    expect(await ui.find({ text: '✗' })).toBeTruthy()
    expect(await ui.find({ text: '◉' })).toBeUndefined()  // the band's old running mark is gone
    await ui.unmount()
  })
}

// The header named codex · muse · grok whatever ran; it now shows a live dot per agent that has runs.
test('header dots come from the runs: one per agent, counted, working and ended marked', () => {
  const dots = engineDots([...EIGHT, run('g1', 'antigravity', 'error')])
  expect(dots.map(d => [d.engine, d.count, d.working, d.open])).toEqual([
    ['codex', 2, false, true], ['muse', 1, false, true], ['claude', 5, true, true], ['antigravity', 1, false, true],
  ])
  expect(engineDots([run('x', 'kimi', 'done')])[0]).toMatchObject({ engine: 'kimi', open: false, colour: '#F5C2E7' })
  expect(engineDots([])).toEqual([])
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`header shows live agent dots and no fixed agent list (${surface})`, async ($, on) => {
    const runs = [run('g1', 'antigravity', 'running'), run('q1', 'qwen', 'done')]
    const props = { runs: runs as any, selected: 'g1', feed: [], partial: '', age: 1, problem: '', home: '/home/test', canType: true }
    on('ui.render', { component: 'Pane', requestId: 'hdr' } as any, async ($$: any, e: any) =>
      drawStage($$.ui.resolve(e), props as any, 0, {}, () => {}))
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'hdr',
      props: {} as any, viewport: { columns: 200, rows: 44 } })
    expect(await ui.find({ key: 'dots' })).toBeTruthy()
    expect(await ui.find({ text: /● antigravity/ })).toBeTruthy()  // working
    expect(await ui.find({ text: /○ qwen/ })).toBeTruthy()  // ended
    expect(await ui.find({ text: /[●○] (codex|muse|grok)/ })).toBeUndefined()  // no agent that has no runs
    expect(await ui.find({ text: /codex · muse · grok/ })).toBeUndefined()
    await ui.unmount()
  })
}
