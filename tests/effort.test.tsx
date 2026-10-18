import { expect, test } from 'claude-code/testing'
import { drawLauncher, effortsFor } from '../hooks/ui/native.tsx'
import { efforts } from '../hooks/register.tsx'
import { fakeBridge } from './fake-bridge.ts'
import type { Bridge } from './fake-bridge.ts'

// Thinking effort: Codex, Muse and Grok each take one, in their own way, but the panel gave no way to pick it, so
// every run used the CLI's config default (medium for Codex). The launcher now shows the levels the agent and
// model take, a run starts with the one chosen, and Claude can pass it too.

const CODEX = { id: 'codex', name: 'Codex', color: '#7AA2F7', protocol: 'codex-app-server', steer: 'native', installed: true, version: '0.156', command: 'codex app-server', note: '',
  takes_model: true, default_model: 'gpt-6.1-sol', default_effort: 'medium',
  models: [{ id: 'gpt-6.1-sol', label: 'Sol', efforts: ['low', 'medium', 'high', 'xhigh', 'max', 'ultra'], default_effort: 'low' },
           { id: 'gpt-6-luna', label: 'Luna', efforts: ['low', 'medium', 'high'] },
           { id: 'plain', label: 'Plain' }] }
const GROK = { id: 'grok', name: 'Grok', color: '#E0AF68', protocol: 'acp', steer: 'queue', installed: true, version: '1.0', command: 'grok agent stdio', note: '',
  takes_model: true, default_model: 'grok-4.7', efforts: ['low', 'medium', 'high'], default_effort: 'high', models: [{ id: 'grok-4.7', label: 'grok-4.7' }] }
const AGY = { id: 'antigravity', name: 'Antigravity', color: '#8AB4F8', protocol: 'stream-json', steer: 'queue', installed: true, version: '1.4', command: 'agy', note: '', takes_model: true }

test('the levels follow the agent and the picked model', () => {
  expect(effortsFor(CODEX as any, '')).toEqual(['low', 'medium', 'high', 'xhigh', 'max', 'ultra'])  // the default model's
  expect(effortsFor(CODEX as any, 'gpt-6-luna')).toEqual(['low', 'medium', 'high'])
  expect(effortsFor(CODEX as any, 'plain')).toEqual([])                                            // a model with none shows none
  expect(effortsFor(GROK as any, 'grok-4.7')).toEqual(['low', 'medium', 'high'])                    // one list for every model
  expect(effortsFor(AGY as any, '')).toEqual([])
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`the launcher offers the levels, marks the default and the pick, and launches with it (${surface})`, async ($, on) => {
    const acts: any[] = []
    on('ui.render', { component: 'Pane', requestId: 'efforts' } as any, async ($$: any, e: any) => {
      const el = $$.ui.resolve(e)
      return <el.Box flexDirection="column">
        {drawLauncher(el, [CODEX, GROK, AGY] as any, 'codex', '', true, a => acts.push(a), 'high')}
      </el.Box>
    })
    const ui: any = await $.ui.mount({ plugin: 'modstage', surface, component: 'Pane', requestId: 'efforts', props: {} as any, viewport: { columns: 120, rows: 40 } })
    expect(await ui.find({ text: /effort/ })).toBeTruthy()
    expect(await ui.find({ text: /default \(low\)/ })).toBeTruthy()          // what the CLI uses when none is picked
    for (const level of ['low', 'medium', 'xhigh', 'max', 'ultra']) expect(await ui.find({ key: `effort:${level}` })).toBeTruthy()
    expect(await ui.find({ text: /● high/ })).toBeTruthy()                    // the current pick
    await ui.press({ key: 'effort:max', plugin: 'test' })
    await ui.press({ key: 'effort:high', plugin: 'test' })                      // pressing the pick again clears it
    await ui.input({ key: 'launch-task:codex', text: 'do it', plugin: 'test' })
    expect(acts[0]).toEqual({ type: 'pickEffort', effort: 'max' })
    expect(acts[1]).toEqual({ type: 'pickEffort', effort: '' })
    expect(acts[2]).toMatchObject({ type: 'launch', engine: 'codex', prompt: 'do it', effort: 'high' })
    await ui.unmount()
  })
}

test('stage_start passes the effort to the bridge, and says nothing when none was asked for', async ($, on) => {
  const b: Bridge = { runs: {}, decided: [], session: 'sess-A' }
  fakeBridge(on, b)
  on('ui.open', () => ({ value: undefined }))
  await $.tool.call({ tool: 'mcp__modstage__stage_start', engine: 'codex', prompt: 'x', model: 'gpt-6.1-sol', effort: 'xhigh' } as any)
  await $.tool.call({ tool: 'mcp__modstage__stage_start', engine: 'codex', prompt: 'y' } as any)
  expect(b.started?.[0]).toMatchObject({ engine: 'codex', model: 'gpt-6.1-sol', effort: 'xhigh' })
  expect(b.started?.[1]?.effort).toBeUndefined()
})

test('stage_agents states each agent\'s levels and its default, and where Antigravity keeps its effort', () => {
  expect(efforts(CODEX as any)).toContain('low, medium, high, xhigh, max, ultra')
  expect(efforts(CODEX as any)).toContain('the exact levels differ by model')
  expect(efforts(CODEX as any)).toContain('default medium')
  expect(efforts(GROK as any)).toBe('\n    effort: low, medium, high; default high')
  expect(efforts(AGY as any)).toContain('High, Medium or Low model')
})
