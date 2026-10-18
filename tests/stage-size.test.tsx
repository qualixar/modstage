import { expect, test } from 'claude-code/testing'
import StageClient from '../hooks/ui/stage.tsx'

// A Client whose content follows its own measured region is unmounted by the engine ("changed its own
// size after each of 3 draws") the moment an approval card above it shrinks that region. The stage's
// height must come from its props, whatever the surface reports as its rows.
const el = (tag: string) => (props: any) => ({ tag, props: props ?? {}, children: props?.children })
const fakeSurface = (rows: number): any => ({
  elements: { Box: el('Box'), Text: el('Text'), Button: el('Button'), Input: el('Input') },
  rows, columns: 100, state: { tick: 3 }, every: () => () => {}, setState: () => {}, post: () => {},
})
const usage = { input: 1, cached: 0, output: 1, reasoning: 0, context_used: 1, context_window: 100, cost_usd: null }
const props = (rows: number | undefined): any => ({
  runs: [{ id: 'a1', engine: 'muse', model: null, label: 'x', cwd: '/h', status: 'running', activity: 'thinking', elapsed_s: 3, usage, error: null }],
  selected: 'a1', feed: Array.from({ length: 50 }, (_, i) => ({ seq: i + 1, kind: 'tool', text: `step ${i}` })),
  partial: '', age: 1, problem: '', home: '/h', canType: true, })
const height = (tree: any) => tree?.props?.height

test('the head draws the same whatever its region measures, and is not given a height', () => {
  const tall = StageClient(props(undefined), fakeSurface(90))
  const short = StageClient(props(undefined), fakeSurface(8))
  expect(JSON.stringify(tall)).toBe(JSON.stringify(short))
  expect(tall?.props?.height).toBeUndefined()
})

// Another way the engine unmounts a Client: props past 100000 characters. Approvals carry up to 4000
// characters of detail each; eight runs with several waiting must still fit.
import { CLIENT_PROP_LIMIT, forClient } from '../hooks/ui/stage.tsx'

test('client props stay under the engine limit with many large approvals, and keep what the stage draws', () => {
  const big = 'x'.repeat(4000)
  const runs = ['codex', 'muse', 'antigravity', 'grok', 'kimi', 'qwen', 'opencode', 'claude'].map((engine, i) => ({
    id: `r${i}`, engine, model: 'm', label: 'task '.repeat(80), cwd: '/h/' + 'd'.repeat(500), status: 'running', activity: 'thinking',
    elapsed_s: 5, usage, error: null, touched: Array.from({ length: 300 }, (_, k) => `f${k}`),
    pending: Array.from({ length: 6 }, (_, k) => ({ id: `a${k}`, title: `run ${big}`, detail: big, run_id: `r${i}` })),
  }))
  const feed = Array.from({ length: 60 }, (_, i) => ({ seq: i + 1, kind: 'result', text: big.slice(0, 400), detail: big.slice(0, 240) }))
  const raw: any = { ...props(30), runs, feed }
  expect(JSON.stringify(raw).length).toBeGreaterThan(CLIENT_PROP_LIMIT)
  const slim = forClient(raw)
  expect(JSON.stringify(slim).length).toBeLessThan(100000)
  expect(slim.runs.length).toBe(8)
  expect(slim.runs[0]!.pending!.length).toBe(6)
  expect(slim.feed.length).toBeGreaterThan(3)
  expect(slim.selected).toBe('a1')
})
