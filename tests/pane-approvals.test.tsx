import { expect, test } from 'claude-code/testing'
import { fakeBridge } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'

// The user reported (18 Oct 2026) that with any agent, the moment an approval arrived the stage between the
// launcher and the message box vanished until the pane was reopened. Drive the real pane with every agent,
// several waiting approvals, and several pane sizes: the stage, the Needs-you card and the message box all stay.

const usage = { input: 1, cached: 0, output: 1, reasoning: 0, context_used: 1, context_window: 100, cost_usd: null }
const ENGINES = ['codex', 'muse', 'antigravity', 'grok', 'kimi', 'qwen', 'opencode']
const big = 'y'.repeat(4000)

for (const surface of ['desktop', 'terminal'] as const) {
  for (const rows of [16, 30, 70]) {
    test(`with approvals from every agent the stage, the card and the message box all stay (${surface}, ${rows} rows)`, async ($, on) => {
      const runs = ENGINES.map((engine, i) => ({
        id: `r${i}`, engine, model: null, label: `${engine} task`, cwd: '/home/test', status: 'running', activity: 'thinking', elapsed_s: 4,
        usage, error: null, owner: 'sess-A', steer: 'queue',
        pending: [0, 1, 2].map(k => ({ id: `a${i}${k}`, run_id: `r${i}`, engine, kind: 'command', title: `step ${k} ${big}`, detail: big, warning: '', asked_at: Date.now() / 1000 })),
      }))
      const b: Bridge = { runs: Object.fromEntries(runs.map(r => [r.id, r])), decided: [], session: 'sess-A' }
      fakeBridge(on, b)
      on('ui.open', () => ({ value: undefined }))
      await $.tool.call({ tool: 'mcp__modstage__stage_start', engine: 'codex', prompt: 'x' } as any) // its poll fills the panel
      const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'modstage',
        props: {} as any, viewport: { columns: 120, rows } })
      expect(await ui.find({ text: /Needs you/ })).toBeTruthy()
      expect(await ui.find(surface === 'desktop' ? { type: 'Svg' } : { key: 'stage' })).toBeTruthy()
      expect(await ui.find({ key: 'composer' })).toBeTruthy()
      await ui.press({ key: 'allow:a00' })
      expect(b.decided.length).toBe(1)
      expect(await ui.find(surface === 'desktop' ? { type: 'Svg' } : { key: 'stage' })).toBeTruthy()
      await ui.unmount()
    })
  }
}
