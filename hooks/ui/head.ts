// The panel's head on the desktop: a header card (wordmark, live state, one cell per agent), four stat tiles and the
// selected run's card, drawn as one vector picture sized to the pane. Nothing here is interactive (tabs, buttons and
// inputs are drawn natively below it), so the picture animates with CSS alone and needs no frame clock.
//
// Every text is fitted to the room it has, and a block that cannot fit beside another goes under it: nothing is drawn
// outside its card or over a neighbour, from the narrowest pane (240 px) to the widest (1400 px).
import type { RunView, StageProps } from './stage.tsx'
import { ACCENT, BAD, OK, STATUS, WARN, colourOf } from './palette.ts'
import { autonomyLabel, elapsed, kTok, pct, shortPath, steerLabel, totals } from './format.ts'
import { bar, fitText, pill, robot, robotState, svgDoc, text, textWidth, xml } from './vector.ts'
import { engineDots } from './runs.ts'

const PAD = 16 // inner margin of a card
const GAP = 10 // between blocks
export const MIN_W = 240
export const MAX_W = 1400

/** Width in px for a region reporting `columns` cells; the engine's cells are about 8 px wide on the desktop. */
export const widthFor = (columns: number | undefined, fallback = 64): number =>
  Math.max(MIN_W, Math.min(MAX_W, (columns || fallback) * 8 - 4))

type Part = { svg: string; h: number }

/** The header card: wordmark and live state, then one aligned cell per agent that has runs. */
function header(p: StageProps, W: number): Part {
  const live = p.age >= 0 && p.age <= 3
  const label = live ? `live · ${p.runs.length} run${p.runs.length === 1 ? '' : 's'}` : p.age < 0 ? 'connecting' : `stalled ${p.age}s`
  const status = pill(0, 0, label, live ? OK : p.age < 0 ? WARN : BAD, { dot: true, pulse: live, h: 24 })
  const s: string[] = []
  const top = 14
  s.push(`<rect x="${PAD}" y="${top}" width="28" height="28" rx="9" fill="${ACCENT}"/>`)
  s.push(`<path d="M${PAD + 14} ${top + 6.5}v15M${PAD + 7.5} ${top + 10.2}l13 7.6M${PAD + 7.5} ${top + 17.8}l13-7.6" stroke="#fff" stroke-width="2" stroke-linecap="round"/>`)
  s.push(text(PAD + 38, top + 20, 'ModStage', { size: 17, weight: 700 }))
  const beside = W - PAD * 2 >= 38 + textWidth('ModStage', 17) + 16 + status.w
  let y = top + 28
  if (beside) {
    s.push(`<g transform="translate(${W - PAD - status.w} ${top + 2})">${status.svg}</g>`)
  } else {
    y += 12
    s.push(`<g transform="translate(${PAD} ${y - 4})">${status.svg}</g>`)
    y += 24
  }
  const dots = engineDots(p.runs)
  if (dots.length) {
    // Equal cells so the dots and names line up in columns however long a name is.
    const room = W - PAD * 2
    const names = dots.map(d => fitText(d.count > 1 ? `${d.engine} ${d.count}` : d.engine, 12, Math.max(40, room - 22)))
    const cell = Math.min(room, Math.ceil(Math.max(...names.map(n => textWidth(n, 12))) + 30))
    const perRow = Math.max(1, Math.floor(room / cell))
    y += 22
    dots.forEach((d, i) => {
      const x = PAD + (i % perRow) * cell
      const cy = y + Math.floor(i / perRow) * 22
      s.push(`<circle cx="${x + 5}" cy="${cy - 4}" r="4" fill="${d.colour}"${d.working ? ' class="pulse"' : ''}${d.open ? '' : ' fill-opacity=".4"'}/>`)
      s.push(text(x + 16, cy, names[i]!, { cls: d.open ? 't2' : 't3', size: 12, weight: d.working ? 600 : 400 }))
    })
    y += (Math.ceil(dots.length / perRow) - 1) * 22
  }
  const h = y + 16
  return { svg: `<rect class="pn" x="0" y="0" width="${W}" height="${h}" rx="16"/>` + s.join(''), h }
}

/** Why the bridge is not answering, when it is not: the terminal head says it in a line, so does this. */
function notice(p: StageProps, W: number): Part | null {
  if (!p.problem) return null
  const msg = fitText(`bridge: ${p.problem}`, 12, W - PAD * 2)
  return {
    svg: `<rect x="0" y="0" width="${W}" height="34" rx="12" fill="${BAD}" fill-opacity=".14"/>` +
      `<text class="pt" fill="${BAD}" x="${PAD}" y="21" font-family="system-ui,sans-serif" font-size="12" font-weight="600">${xml(msg)}</text>`,
    h: 34,
  }
}

function tiles(p: StageProps, W: number): Part {
  const t = totals(p.runs)
  const cells: Array<{ label: string; value: string; colour: string; live: boolean; muted: boolean; sub?: string }> = [
    { label: 'WORKING', value: String(t.working), colour: STATUS.running!, live: t.working > 0, muted: t.working === 0 },
    { label: 'NEEDS YOU', value: String(t.waiting), colour: WARN, live: t.waiting > 0, muted: t.waiting === 0 },
    { label: 'FINISHED', value: String(t.finished), colour: OK, live: false, muted: t.finished === 0 },
    { label: 'SPEND', value: t.priced ? `$${t.usd < 100 ? t.usd.toFixed(2) : Math.round(t.usd)}` : '–', colour: '#8A8FA3', live: false, muted: !t.priced, sub: 'API price' },
  ]
  const perRow = W >= 480 ? 4 : 2
  const gap = 8
  const tw = (W - gap * (perRow - 1)) / perRow
  const th = 62
  const s: string[] = []
  cells.forEach((c, i) => {
    const x = (i % perRow) * (tw + gap)
    const y = Math.floor(i / perRow) * (th + gap)
    s.push(`<rect class="pn" x="${x.toFixed(1)}" y="${y}" width="${tw.toFixed(1)}" height="${th}" rx="12"/>`)
    s.push(`<circle cx="${(x + 15).toFixed(1)}" cy="${y + 18}" r="3.5" fill="${c.colour}"${c.live ? ' class="pulse"' : ''}${c.muted ? ' fill-opacity=".45"' : ''}/>`)
    s.push(text(x + 26, y + 22, c.label, { cls: 't3', size: 10, weight: 600, spacing: 0.7 }))
    s.push(text(x + 14, y + 50, c.value, { cls: c.muted ? 't3' : 'tx', size: 24, weight: 700 }))
    // the small caption only where it fits beside the number (bold digits run wider than the estimate, so leave room)
    if (c.sub && textWidth(c.value, 24) * 1.15 + textWidth(c.sub, 10.5) + 14 * 2 + 12 <= tw) {
      s.push(text(x + tw - 14, y + 50, c.sub, { cls: 't3', size: 10.5, anchor: 'end' }))
    }
  })
  const rows = Math.ceil(cells.length / perRow)
  return { svg: s.join(''), h: rows * th + (rows - 1) * gap }
}

function runCard(p: StageProps, run: RunView, W: number): Part {
  const colour = colourOf(run)
  const working = run.status === 'running' || run.status === 'starting'
  const waiting = run.pending?.length ?? 0
  const compact = W < 360
  const mark = compact ? 40 : 56
  const x0 = PAD + mark + (compact ? 10 : 14) // text column, after the mark
  const xr = W - PAD
  const room = Math.max(60, xr - x0)
  const s: string[] = []
  const body: string[] = []
  let y = PAD + 14

  // Row 1: agent, model and effort, and the state pill: beside them when there is room, under them when there is not.
  const stateText = `${run.status === 'idle' ? 'waiting for Claude' : run.status} · ${elapsed(run.elapsed_s)}`
  const st = pill(0, 0, stateText, STATUS[run.status] ?? '#8A8FA3', { dot: true, pulse: working, h: 22 })
  const name = run.name ?? run.engine
  const nameW = textWidth(name, 15) + 10
  const inline = room >= nameW + st.w + 16
  if (inline) {
    body.push(`<g transform="translate(${(xr - st.w).toFixed(1)} ${y - 15})">${st.svg}</g>`)
  }
  body.push(`<text class="pt" fill="${colour}" x="${x0}" y="${y}" font-family="system-ui,sans-serif" font-size="15" font-weight="700">${xml(fitText(name, 15, Math.max(40, room - (inline ? st.w + 12 : 0))))}</text>`)
  const meta = [run.model, run.effort, run.id].filter(Boolean).join(' · ')
  const metaRoom = room - (inline ? st.w + 12 : 0) - nameW
  if (metaRoom > 60) body.push(text(x0 + nameW, y, fitText(meta, 12, metaRoom), { cls: 't3', size: 12 }))
  if (!inline) {
    y += 10
    body.push(`<g transform="translate(${x0} ${y})">${st.svg}</g>`)
    y += 22 - 4
  }

  // Row 2: the task.
  y += 24
  body.push(text(x0, y, fitText(run.label, 13.5, room), { size: 13.5, weight: 600 }))

  // Row 3: chips, then the next row of chips when they do not fit on one.
  y += 14
  let cx = x0
  let rowTop = y
  const put = (label: string, c: string, dot = false) => {
    const chip = pill(0, 0, fitText(label, 10.5, room - 30), c, { h: 20, size: 10.5, dot })
    if (cx > x0 && cx + chip.w > xr) { cx = x0; rowTop += 26 }
    body.push(`<g transform="translate(${cx} ${rowTop})">${chip.svg}</g>`)
    cx += chip.w + 6
  }
  put(steerLabel(run), '#8A8FA3')
  const au = autonomyLabel(run)
  put(au.text, au.warn ? BAD : OK)
  if (waiting) put(`${waiting} waiting on you`, WARN, true)
  if (run.stuck) put(`quiet ${Math.round((run.quiet_s ?? 0) / 60)}m`, BAD)
  else if (working && (run.quiet_s ?? 0) >= 45) put(`no output ${(run.quiet_s ?? 0) < 120 ? `${run.quiet_s}s` : `${Math.round((run.quiet_s ?? 0) / 60)}m`}`, '#8A8FA3')
  y = rowTop + 20

  // Notes that need attention.
  const note = run.blocked ? { t: `blocked: ${run.blocked}`, c: BAD } : run.approval_note ? { t: run.approval_note, c: WARN } : null
  if (note) { y += 20; body.push(`<text class="pt" fill="${note.c}" x="${x0}" y="${y}" font-family="system-ui,sans-serif" font-size="12">${xml(fitText(note.t, 12, room))}</text>`) }

  // Path, context gauge and usage.
  y += 22
  body.push(text(x0, y, fitText(shortPath(run.cwd, p.home), 11, room, true), { cls: 't3', size: 11, mono: true }))
  const c = pct(run)
  y += 24
  const used = c != null ? `${c}% · ${kTok(run.usage.context_used)}/${kTok(run.usage.context_window)}` : kTok(run.usage.context_used)
  const usedW = textWidth(used, 11) + 8
  const bx = x0 + 52
  const barW = xr - usedW - bx - 8
  if (barW >= 40) {
    body.push(text(x0, y + 1, 'context', { cls: 't3', size: 11 }))
    body.push(bar(bx, y - 8, barW, 8, c == null ? null : c / 100, c != null && c > 80 ? BAD : colour))
    body.push(text(xr, y + 1, used, { cls: 'tx', size: 11, anchor: 'end' }))
  } else {
    // no room for a gauge beside the numbers: the gauge takes the full width and the numbers go under it
    body.push(bar(x0, y - 8, room, 8, c == null ? null : c / 100, c != null && c > 80 ? BAD : colour))
    y += 18
    body.push(text(x0, y, fitText(`context ${used}`, 11, room), { cls: 'tx', size: 11 }))
  }
  y += 22
  const usage = `in ${kTok(run.usage.input)} (${kTok(run.usage.cached)} cached) · out ${kTok(run.usage.output)}` +
    (run.usage.reasoning ? ` (${kTok(run.usage.reasoning)} thinking)` : '') +
    (run.usage.cost_usd != null ? ` · ≈$${run.usage.cost_usd.toFixed(2)} at API price` : '')
  body.push(text(x0, y, fitText(usage, 11, room), { cls: 't3', size: 11 }))
  y += PAD

  const h = Math.max(y, PAD * 2 + mark)
  s.push(`<rect class="pn" x="0" y="0" width="${W}" height="${h}" rx="16"/>`)
  s.push(`<rect x="0.75" y="0.75" width="${W - 1.5}" height="${h - 1.5}" rx="15.5" fill="none" stroke="${colour}" stroke-opacity=".38" stroke-width="1.5"/>`)
  s.push(robot(PAD, PAD, colour, robotState(run.status, waiting > 0), mark))
  s.push(...body)
  return { svg: s.join(''), h }
}

/** The whole head as one SVG document, with the text a screen reader gets. */
export function headSvg(p: StageProps, W: number): { source: string; height: number; alt: string } {
  const run = p.runs.find(r => r.id === p.selected)
  const parts: Part[] = [header(p, W)]
  const note = notice(p, W)
  if (note) parts.push(note)
  parts.push(tiles(p, W))
  if (run) parts.push(runCard(p, run, W))
  const out: string[] = []
  let y = 0
  parts.forEach(part => {
    out.push(`<g transform="translate(0 ${y})">${part.svg}</g>`)
    y += part.h + GAP
  })
  const height = Math.ceil(y - GAP)
  const t = totals(p.runs)
  const alt = `ModStage: ${p.runs.length} run${p.runs.length === 1 ? '' : 's'}, ${t.working} working, ${t.waiting} waiting on you` +
    (run ? `. Selected: ${run.name ?? run.engine}, ${run.label}, ${run.status}.` : '.') + (p.problem ? ` Bridge problem: ${p.problem}.` : '')
  return { source: svgDoc(W, height, out.join('')), height, alt }
}
