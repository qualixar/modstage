import { expect, test } from 'claude-code/testing'
import { fakeBridge } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'

// 0.0.17 drew the head's pictures in a frame (isInteractive) so they would animate, and the pane stopped scrolling: a frame
// swallows the mouse wheel (reported 19 Oct 2026, a P1). No picture may be framed again.

const usage = { input: 1, cached: 0, output: 1, reasoning: 0, context_used: 1, context_window: 100, cost_usd: null }

test('no picture in the panel is drawn in a frame, so nothing under the pointer swallows the wheel', async ($, on) => {
  const b: Bridge = {
    runs: { r0: { id: 'r0', engine: 'codex', model: null, label: 'x', cwd: '/home/test', status: 'running', activity: 'thinking', elapsed_s: 4, usage, error: null, owner: 'sess-A', steer: 'native', pending: [] } },
    decided: [], session: 'sess-A',
  }
  fakeBridge(on, b)
  on('ui.open', () => ({ value: undefined }))
  await $.tool.call({ tool: 'mcp__modstage__stage_start', engine: 'codex', prompt: 'x' } as any)
  const ui: any = await $.ui.mount({ plugin: 'modstage', surface: 'desktop', component: 'Pane', requestId: 'modstage', props: {} as any, viewport: { columns: 120, rows: 40 } })
  const pictures: any[] = await ui.findAll({ type: 'Svg' })
  expect(pictures.length).toBeGreaterThanOrEqual(4)           // header, tiles, the mark, the run card (and the card titles)
  for (const p of pictures) {
    expect(p.props.isInteractive).toBeUndefined()
    expect(p.props.alt).toBeTruthy()
  }
  await ui.unmount()
})
