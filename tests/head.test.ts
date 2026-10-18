import { expect, test } from 'claude-code/testing'
import { ENGINE } from '../hooks/ui/palette.ts'
import { headSvg, widthFor } from '../hooks/ui/head.ts'
import { robot } from '../hooks/ui/vector.ts'

// Every agent has its own colour, the desktop head is one well-formed vector picture that fits its width whatever the
// text in it, and the robot shows each state in its own way (18 Oct 2026: "every agent a different colour, robots more
// mature, alignment perfect").

const usage = (o: any = {}) => ({ input: 12300, cached: 8000, output: 2100, reasoning: 900, context_used: 120000, context_window: 1000000, cost_usd: 0.42, ...o })
const run = (id: string, engine: string, status: string, o: any = {}) => ({
  id, engine, model: 'gpt-6.1-sol', label: 'Fix the gate', cwd: '/home/test/project', status, activity: status, elapsed_s: 134,
  usage: usage(), error: null, steer: 'native', autonomy: 'ask', ...o,
})
const props = (runs: any[], selected: string, extra: any = {}) => ({ runs, selected, feed: [], partial: '', age: 1, problem: '', home: '/home/test', canType: true, ...extra }) as any

const rgb = (c: string) => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16))
const distance = (a: string, b: string) => Math.hypot(...rgb(a).map((v, i) => v - rgb(b)[i]!))

test('no two agents share a colour, and none is close enough to be mistaken for another', () => {
  const names = Object.keys(ENGINE)
  expect(new Set(Object.values(ENGINE)).size).toBe(names.length)
  for (const a of names) for (const b of names) if (a < b) expect(distance(ENGINE[a]!, ENGINE[b]!)).toBeGreaterThan(55)
})

// A tiny well-formedness check: tags nest and close, and every attribute value is quoted.
function wellFormed(svg: string): boolean {
  const stack: string[] = []
  for (const m of svg.matchAll(/<(\/?)([a-zA-Z][\w:-]*)((?:\s+[\w:-]+="[^"]*")*)\s*(\/?)>/g)) {
    const [, close, name, , self] = m
    if (self) continue
    if (close) { if (stack.pop() !== name) return false } else stack.push(name!)
  }
  return stack.length === 0 && !/<[^>]*[^"\s=\w/-]>/.test(svg.replace(/<text[^>]*>[^<]*<\/text>/g, '<text/>').replace(/<style>[\s\S]*?<\/style>/, ''))
}

for (const W of [240, 420, 760, 1400]) {
  test(`the desktop head is one well-formed picture of exactly the pane's width (${W} px)`, () => {
    const runs = [run('a1', 'codex', 'running', { pending: [{ title: 'curl' }], effort: 'high' }), run('a2', 'muse', 'idle'),
      run('a3', 'grok', 'error'), run('a4', 'antigravity', 'running', { autonomy: 'auto', steer: 'queue' }), run('a5', 'kimi', 'done'),
      run('a6', 'qwen', 'interrupted'), run('a7', 'opencode', 'idle'), run('a8', 'claude', 'running', { steer: 'watch', color: null })]
    for (const sel of runs.map(r => r.id)) {
      const h = headSvg(props(runs, sel), W)
      expect(h.source.startsWith(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${h.height}"`)).toBe(true)
      expect(wellFormed(h.source)).toBe(true)
      expect(h.height).toBeGreaterThan(150)
      expect(h.alt).toMatch(/8 runs, 3 working, 1 waiting on you/)
    }
  })
}

test('text from an agent is escaped, never drawn as markup', () => {
  const evil = run('x1', 'codex', 'running', { label: '</text><script>alert(1)</script>&"\'', cwd: '/h/<b>/&', model: '<m>' })
  const { source } = headSvg(props([evil], 'x1'), 600)
  expect(source).not.toContain('<script')
  expect(source).toContain('&lt;/text&gt;')  // the label's own closing tag is escaped
  expect(source).toContain('&lt;script&gt;')
  expect(wellFormed(source)).toBe(true)
})

test('the head draws an agent that has no runs yet, and one whose numbers are unknown', () => {
  expect(wellFormed(headSvg(props([], ''), 500).source)).toBe(true)
  const blank = run('u1', 'muse', 'running', { usage: usage({ context_window: null, cost_usd: null }) })
  const { source } = headSvg(props([blank], 'u1', { age: -1 }), 500)
  expect(source).toContain('connecting')
  expect(wellFormed(source)).toBe(true)
})

test('the width follows the pane in cells, never below a readable minimum or past a sane maximum', () => {
  expect(widthFor(0)).toBeGreaterThan(300)
  expect(widthFor(10)).toBe(240)
  expect(widthFor(80)).toBe(636)
  expect(widthFor(5000)).toBe(1400)
})

test('the robot shows each state its own way, in the agent\'s colour, on one shared beat', () => {
  const c = ENGINE.codex!
  const w = robot(0, 0, c, 'working'), g = robot(0, 0, c, 'waiting'), i = robot(0, 0, c, 'idle'), e = robot(0, 0, c, 'ended'), f = robot(0, 0, c, 'failed')
  expect(w).toContain('class="look"')
  expect(g).toContain('#F5B93A')            // waiting on you: amber eyes
  expect(i).toContain('class="blink"')
  expect(e).not.toMatch(/class="(look|blink|flick)"/)
  expect(f).toContain('class="flick"')
  for (const m of [w, g, i, e, f]) expect(m).toContain(c)
})

// ---- layout: nothing outside the picture, nothing drawn over a neighbour -------------------------------------------------
type Box = { x0: number; x1: number; y: number; text: string }
function textBoxes(svg: string): Box[] {
  const out: Box[] = []
  const shift: Array<[number, number]> = [[0, 0]]
  for (const m of svg.matchAll(/<(\/?)(g|text)\b([^>]*)>([^<]*)/g)) {
    const [, close, tag, attrs, inner] = m
    if (tag === 'g') {
      if (close) { shift.pop(); continue }
      const t = /transform="translate\(([-\d.]+) ([-\d.]+)\)/.exec(attrs!)
      const [ox, oy] = shift[shift.length - 1]!
      shift.push(t ? [ox + Number(t[1]), oy + Number(t[2])] : [ox, oy])
      if (/\/\s*$/.test(attrs!)) shift.pop()
    } else if (!close) {
      const [ox, oy] = shift[shift.length - 1]!
      const num = (k: string) => Number(new RegExp(`\\b${k}="([-\\d.]+)"`).exec(attrs!)?.[1])
      const content = inner!.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&')
      const w = textWidth(content, num('font-size'), /ui-monospace/.test(attrs!))
      const x = ox + num('x')
      const anchor = /text-anchor="(\w+)"/.exec(attrs!)?.[1] ?? 'start'
      const x0 = anchor === 'end' ? x - w : anchor === 'middle' ? x - w / 2 : x
      out.push({ x0, x1: x0 + w, y: Math.round(oy + num('y')), text: content })
    }
  }
  return out
}
import { textWidth } from '../hooks/ui/vector.ts'

const longRuns = [
  run('L1', 'codex', 'idle', { model: 'a-very-long-model-name-from-a-custom-agent-1.0', label: 'A very long task description that goes on and on and on past any width', cwd: '/Users/someone/Documents/work/a/very/deep/folder/structure/project', effort: 'xhigh', blocked: 'something long went wrong and the agent says so at length', usage: usage({ cost_usd: 99.99 }) }),
  run('L2', 'a-custom-agent-with-a-very-long-id', 'running', { steer: 'queue', autonomy: 'auto', stuck: true, quiet_s: 4000, pending: [{ title: 'x' }, { title: 'y' }], elapsed_s: 4000 }),
  run('L3', 'muse', 'interrupted'),
]
for (const W of [240, 300, 360, 420, 600, 760, 1400]) {
  for (const sel of ['L1', 'L2', 'L3']) {
    test(`no text leaves the picture or runs into another (${W} px, ${sel})`, () => {
      const { source } = headSvg(props(longRuns, sel, { problem: 'connection refused to the local bridge at 127.0.0.1' }), W)
      const boxes = textBoxes(source)
      expect(boxes.length).toBeGreaterThan(12)
      for (const b of boxes) {
        expect(b.x0).toBeGreaterThanOrEqual(-1)
        expect(b.x1).toBeLessThanOrEqual(W + 1)
      }
      for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i]!, b = boxes[j]!
        if (Math.abs(a.y - b.y) > 5) continue
        const overlap = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0)
        expect(overlap, `"${a.text}" and "${b.text}" overlap by ${overlap}px at ${W}`).toBeLessThanOrEqual(1)
      }
    })
  }
}

test('a colour from a custom agent that is not a plain hex value never reaches the picture', () => {
  const sly = run('c1', 'codex', 'running', { color: '#fff" onload="alert(1)' })
  const { source } = headSvg(props([sly], 'c1'), 500)
  expect(source).not.toContain('onload')
  expect(source).toContain(ENGINE.codex!)
})

test('the bridge problem is shown on the desktop too', () => {
  const { source, alt } = headSvg(props([run('p1', 'codex', 'idle')], 'p1', { problem: 'refused' }), 500)
  expect(source).toContain('bridge: refused')
  expect(alt).toContain('Bridge problem: refused')
})

test('the layout checker itself sees an overlap and a text outside the picture', () => {
  const svg = '<svg><g transform="translate(10 0)"><text x="0" y="20" font-size="12" font-family="sans">hello world</text></g>' +
    '<text x="40" y="22" font-size="12" font-family="sans">overlapping words</text><text x="300" y="60" font-size="12" font-family="sans" text-anchor="end">gone left</text></svg>'
  const boxes = textBoxes(svg)
  expect(boxes.length).toBe(3)
  expect(Math.min(boxes[0]!.x1, boxes[1]!.x1) - Math.max(boxes[0]!.x0, boxes[1]!.x0)).toBeGreaterThan(1)
  expect(boxes[2]!.x1).toBe(300)
})

test('the header carries ModStage\'s own logo, embedded, never loaded from anywhere', () => {
  const { source } = headSvg(props([run('l1', 'codex', 'idle')], 'l1'), 500)
  expect(source).toMatch(/<image href="data:image\/png;base64,[A-Za-z0-9+\/=]{2000,}"/)
  expect(source).not.toMatch(/href="https?:/)
})

// ---- animation: a picture that changes restarts its animation, so the animated ones must not change without cause ----------
import { headParts } from '../hooks/ui/head.ts'
const flat = (p: any, W: number) => headParts(p, W).flat()

test('the robot picture does not change while only the numbers beside it do', () => {
  const a = run('s1', 'codex', 'running', { elapsed_s: 61, usage: usage({ input: 100 }) })
  const b = run('s1', 'codex', 'running', { elapsed_s: 77, usage: usage({ input: 5000, cost_usd: 1.5 }) })
  const mark = (r: any) => flat(props([r], 's1'), 700).find(x => x.key === 'hd-mark')!
  expect(mark(a).source).toBe(mark(b).source)
  expect(mark(a).animated).toBe(true)
})

test('the run card changes only when something worth showing changed (time moves in coarse steps)', () => {
  const card = (s: number) => flat(props([run('s2', 'muse', 'running', { elapsed_s: s })], 's2'), 700).find(x => x.key === 'hd-run')!.source
  expect(card(61)).toBe(card(89))            // the same half-minute
  expect(card(61)).not.toBe(card(95))        // the next one
  expect(card(5)).toBe(card(14))             // under a minute: 15 s steps
  expect(card(14)).not.toBe(card(16))
})

test('the robot\'s picture is the agent\'s state and nothing else: another agent, another colour; another state, another face', () => {
  const m = (r: any) => flat(props([r], 'x'), 700).find(p => p.key === 'hd-mark')!.source
  expect(m(run('x', 'codex', 'running'))).not.toBe(m(run('x', 'muse', 'running')))
  expect(m(run('x', 'codex', 'running'))).not.toBe(m(run('x', 'codex', 'error')))
  expect(m(run('x', 'codex', 'running'))).not.toBe(m(run('x', 'codex', 'running', { pending: [{ title: 'a' }] })))
})
