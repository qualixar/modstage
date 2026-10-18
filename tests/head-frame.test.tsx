import { expect, test } from 'claude-code/testing'
import { fakeBridge } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'

// The engine draws a plain Svg as a still image; only a frame (isInteractive) runs the CSS and SMIL animation. The animated
// pictures of the head must ask for the frame (18 Oct 2026: "animation should work perfectly with all these things").

const usage = { input: 1, cached: 0, output: 1, reasoning: 0, context_used: 1, context_window: 100, cost_usd: null }

test('on the desktop the head is several pictures and the animated ones are drawn in a frame', async ($, on) => {
  const b: Bridge = {
    runs: { r0: { id: 'r0', engine: 'codex', model: null, label: 'x', cwd: '/home/test', status: 'running', activity: 'thinking', elapsed_s: 4, usage, error: null, owner: 'sess-A', steer: 'native', pending: [] } },
    decided: [], session: 'sess-A',
  }
  fakeBridge(on, b)
  on('ui.open', () => ({ value: undefined }))
  await $.tool.call({ tool: 'mcp__modstage__stage_start', engine: 'codex', prompt: 'x' } as any)
  const ui: any = await $.ui.mount({ plugin: 'modstage', surface: 'desktop', component: 'Pane', requestId: 'modstage', props: {} as any, viewport: { columns: 120, rows: 40 } })
  const pictures: any[] = await ui.findAll({ type: 'Svg' })
  const animated = pictures.filter(p => p.props?.isInteractive === true)
  expect(animated.length).toBe(4)                                              // header, tiles, the mark and the run card
  expect(animated.some(p => /codex is running/.test(p.props.alt))).toBe(true)   // the mark
  for (const p of pictures) expect(p.props.alt).toBeTruthy()
  await ui.unmount()
})
