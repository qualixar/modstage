// Vector drawing helpers for the desktop panel. The engine draws an Svg element as an image, so everything here is
// plain markup built from strings: no script, no external references. Colours that must follow the theme are classes
// (light by default, dark under prefers-color-scheme); the agent's own colour is always passed in as an attribute.
//
// textWidth, fitText and the escape table follow the small helpers in ersinkoc/claude-mods (MIT, Copyright (c) 2026
// Ersin Koç); see THIRD-PARTY-NOTICES.md.

import { FALLBACK, safeColour } from './palette.ts'

/** A colour that is going into markup: a plain hex value, or the neutral fallback. Agent colours come from a user's config file. */
const hexOr = (c: unknown): string => safeColour(c) ?? FALLBACK

export const FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,'Helvetica Neue',sans-serif"
export const MONO = "ui-monospace,'SF Mono','Cascadia Code',Menlo,Consolas,monospace"

const XML: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
export const xml = (s: string): string => s.replace(/[&<>"']/g, c => XML[c]!)

/** Rough rendered width of UI text, for fitting labels. */
export function textWidth(s: string, size: number, mono = false): number {
  if (mono) return s.length * size * 0.62
  let w = 0
  for (const ch of s) w += (/[\s.,:;'|!il1()[\]]/.test(ch) ? 0.3 : /[A-Z@%MWmw]/.test(ch) ? 0.72 : 0.56) * size
  return w
}

export function fitText(s: string, size: number, maxW: number, mono = false): string {
  if (textWidth(s, size, mono) <= maxW) return s
  let out = ''
  for (const ch of s) {
    if (textWidth(out + ch + '…', size, mono) > maxW) break
    out += ch
  }
  return out + '…'
}

/** Shared styles. One 2.4 s beat drives every loop (pulse, look, blink), so animations that run together stay in step. The
 *  pictures are drawn as images, never in a frame: a frame (isInteractive) swallows the mouse wheel and the pane stops scrolling. */
const CSS = `
.pn{fill:#f3f3f1}.ln{stroke:#e0dfda}.tx{fill:#1c1c1a}.t2{fill:#5b5b57}.t3{fill:#8a8a85}.tk{fill:#e3e2dd}.vz{fill:#14151c}
@media (prefers-color-scheme: dark){.pn{fill:#262624}.ln{stroke:#3a3a37}.tx{fill:#ecebe8}.t2{fill:#b3b2ad}.t3{fill:#7d7c77}.tk{fill:#33332f}.vz{fill:#0d0e14}}
@media (prefers-color-scheme: light){.pt{filter:brightness(.68) saturate(1.1)}}
.pulse{animation:pl 2.4s ease-in-out infinite}
@keyframes pl{0%,100%{opacity:1}50%{opacity:.3}}
.look{transform-box:fill-box;transform-origin:center;animation:lk 2.4s ease-in-out infinite}
@keyframes lk{0%,100%{transform:translateX(-2.2px)}50%{transform:translateX(2.2px)}}
.blink{transform-box:fill-box;transform-origin:center;animation:bl 4.8s ease-in-out infinite}
@keyframes bl{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.08)}}
.flick{animation:fl 2.4s steps(1,end) infinite}
@keyframes fl{0%,60%{opacity:1}65%{opacity:.25}70%{opacity:1}}
@media (prefers-reduced-motion: reduce){*{animation:none!important}}
`

export function svgDoc(width: number, height: number, body: string): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><style>${CSS}</style>${body}</svg>`
}

export type TextOpts = { cls?: string; size?: number; weight?: number; anchor?: 'start' | 'middle' | 'end'; fill?: string; mono?: boolean; spacing?: number }
export function text(x: number, y: number, s: string, o: TextOpts = {}): string {
  const { cls = 'tx', size = 12, weight = 400, anchor = 'start', fill, mono = false, spacing } = o
  return `<text ${fill ? `fill="${fill}"` : `class="${cls}"`} x="${x}" y="${y}" font-family="${mono ? MONO : FONT}" font-size="${size}" ` +
    `font-weight="${weight}" text-anchor="${anchor}"${spacing ? ` letter-spacing="${spacing}"` : ''} font-variant-numeric="tabular-nums">${xml(s)}</text>`
}

/** A rounded pill: tinted fill, the colour's own text. Returns its markup and width so callers can lay pills in a row. */
export function pill(x: number, y: number, label: string, colourIn: string, o: { dot?: boolean; pulse?: boolean; h?: number; size?: number } = {}): { svg: string; w: number } {
  const colour = hexOr(colourIn)
  const h = o.h ?? 22
  const size = o.size ?? 11
  const pad = 10
  const dot = o.dot ? 12 : 0
  const w = Math.ceil(textWidth(label, size) + pad * 2 + dot)
  const mid = y + h / 2
  const parts = [`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${h / 2}" fill="${colour}" fill-opacity=".16"/>`]
  if (o.dot) parts.push(`<circle cx="${x + pad + 2.5}" cy="${mid}" r="3" fill="${colour}"${o.pulse ? ' class="pulse"' : ''}/>`)
  parts.push(`<text class="pt" fill="${colour}" x="${x + pad + dot}" y="${mid + size * 0.36}" font-family="${FONT}" font-size="${size}" font-weight="600">${xml(label)}</text>`)
  return { svg: parts.join(''), w }
}

/** A rounded progress bar: track, then the fill, never narrower than its own height so a small value stays a pill. */
export function bar(x: number, y: number, w: number, h: number, ratio: number | null, colourIn: string): string {
  const colour = hexOr(colourIn)
  const r = ratio == null || !Number.isFinite(ratio) ? 0 : Math.max(0, Math.min(1, ratio))
  const fw = r > 0 ? Math.max(h, w * r) : 0
  return `<rect class="tk" x="${x}" y="${y}" width="${w}" height="${h}" rx="${h / 2}"/>` +
    (fw ? `<rect x="${x}" y="${y}" width="${fw.toFixed(1)}" height="${h}" rx="${h / 2}" fill="${colour}"/>` : '')
}

export type RobotState = 'working' | 'waiting' | 'ended' | 'failed' | 'idle'
export const robotState = (status: string, waitingOnYou = false): RobotState =>
  status === 'running' || status === 'starting' ? (waitingOnYou ? 'waiting' : 'working')
    : status === 'error' ? 'failed' : status === 'idle' ? 'idle' : 'ended'

const INK = '#0F1530' // the dark navy outline of ModStage's logo

/** The agent's mark, in the family of ModStage's own logo (flat, rounded, round eyes, an antenna ball): a filled head in
 *  the agent's colour with a navy outline, drawn in a 48 x 48 cell at (x, y). Working: the eyes look left and right and the
 *  ball beats. Waiting on you: wide eyes and an amber ball that beats. Idle: a smile and a blink. Ended: eyes closed.
 *  Failed: crossed eyes and a red ball. Every loop shares the 2.4 s beat, so marks that run together stay in step. */
export function robot(x: number, y: number, colourIn: string, state: RobotState, size = 48): string {
  const colour = hexOr(colourIn)
  const k = size / 48
  const ball = state === 'failed' ? '#F7768E' : state === 'waiting' ? '#F5B93A' : colour
  const beat = state === 'working' || state === 'waiting' ? ' class="pulse"' : ''
  const eye = (cx: number, r: number) => `<circle cx="${cx}" cy="27" r="${r}" fill="${INK}"/><circle cx="${cx - 1.1}" cy="25.6" r="1.1" fill="#fff" fill-opacity=".85"/>`
  const eyes =
    state === 'working' ? `<g class="look">${eye(17.5, 3.7)}${eye(30.5, 3.7)}</g>`
    : state === 'waiting' ? `${eye(17.5, 4.4)}${eye(30.5, 4.4)}`
    : state === 'failed' ? `<g class="flick" stroke="${INK}" stroke-width="2.2" stroke-linecap="round"><path d="M14.5 24l6 6M20.5 24l-6 6M27.5 24l6 6M33.5 24l-6 6"/></g>`
    : state === 'idle' ? `<g class="blink">${eye(17.5, 3.7)}${eye(30.5, 3.7)}</g>`
    : `<path d="M14 28.5q3.5-3.2 7 0M27 28.5q3.5-3.2 7 0" stroke="${INK}" stroke-width="2.2" stroke-linecap="round" fill="none"/>`
  const mouth =
    state === 'failed' ? `<path d="M20 37q4-3 8 0" stroke="${INK}" stroke-width="2" stroke-linecap="round" fill="none"/>`
    : state === 'ended' ? `<path d="M21 36.5h6" stroke="${INK}" stroke-width="2" stroke-linecap="round"/>`
    : `<path d="M20 35.5q4 3.4 8 0" stroke="${INK}" stroke-width="2" stroke-linecap="round" fill="none"/>`
  return `<g transform="translate(${x} ${y}) scale(${k})">` +
    `<rect x="2.2" y="24" width="4.6" height="9" rx="2.3" fill="${colour}" stroke="${INK}" stroke-width="2"/>` +
    `<rect x="41.2" y="24" width="4.6" height="9" rx="2.3" fill="${colour}" stroke="${INK}" stroke-width="2"/>` +
    `<path d="M24 15.5V9" stroke="${INK}" stroke-width="2.4" stroke-linecap="round"/>` +
    `<circle cx="24" cy="6.6" r="3.4" fill="${ball}" stroke="${INK}" stroke-width="2"${beat}/>` +
    `<rect x="6" y="15" width="36" height="28" rx="10" fill="${colour}" stroke="${INK}" stroke-width="2.4"/>` +
    eyes + mouth +
    `</g>`
}

/** ModStage's own logo (assets/logo/modstage-logo.png: four robots on a stage, sound waves either side) redrawn as vector
 *  shapes, because the engine's picture scrub does not draw an embedded bitmap. Drawn in a size x size tile at (x, y). */
export function logoMark(x: number, y: number, size: number): string {
  const k = size / 512
  const ink = '#0D1529'
  const wave = (cx: number, dir: 1 | -1) => [70, 98, 126].map(r => {
    const t0 = (105 * Math.PI) / 180, t1 = (165 * Math.PI) / 180
    const pt = (t: number) => `${(cx + dir * r * Math.cos(t)).toFixed(1)} ${(215 - r * Math.sin(t)).toFixed(1)}`
    return `<path d="M${pt(dir === 1 ? t1 : t0)}A${r} ${r} 0 0 1 ${pt(dir === 1 ? t0 : t1)}" fill="none" stroke="#F3E6C9" stroke-width="9" stroke-linecap="round"/>`
  }).join('')
  const bot = (cx: number, top: number, w: number, h: number, fill: string, ball: number, eyeY: number, eyeR: number, gap: number) =>
    `<path d="M${cx} ${top}V${top - 26}" stroke="${ink}" stroke-width="10" stroke-linecap="round"/>` +
    `<circle cx="${cx}" cy="${top - 34}" r="16" fill="${fill}" stroke="${ink}" stroke-width="8"/>` +
    `<rect x="${cx - w / 2}" y="${top}" width="${w}" height="${h}" rx="36" fill="${fill}" stroke="${ink}" stroke-width="10"/>` +
    `<circle cx="${cx - gap}" cy="${eyeY}" r="${eyeR}" fill="${ink}"/><circle cx="${cx + gap}" cy="${eyeY}" r="${eyeR}" fill="${ink}"/>`
  return `<g transform="translate(${x} ${y}) scale(${k})"><defs><clipPath id="lgc"><rect width="512" height="512" rx="104"/></clipPath></defs>` +
    `<g clip-path="url(#lgc)"><rect width="512" height="512" fill="#0B1221"/>${wave(140, 1)}${wave(372, -1)}` +
    bot(257, 104, 162, 150, '#C28AE9', 0, 176, 17, 40) +
    `<g transform="rotate(-13 125 276)">${bot(125, 206, 172, 140, '#6A9CF8', 0, 264, 17, 36)}</g>` +
    `<g transform="rotate(13 387 276)">${bot(387, 206, 172, 140, '#DEAB60', 0, 264, 17, 36)}</g>` +
    bot(256, 272, 222, 200, '#E47756', 0, 360, 27, 42) +
    `</g></g>`
}

export type SectionIcon = 'spark' | 'flag' | 'chat' | 'list' | 'robot'
const ICONS: Record<SectionIcon, (c: string) => string> = {
  spark: c => `<path d="M11 5v12M5.5 8l11 6M5.5 14l11-6" stroke="${c}" stroke-width="1.8" stroke-linecap="round" fill="none"/>`,
  flag: c => `<path d="M7 17V5M7 5.5h8l-2 3 2 3H7" stroke="${c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`,
  chat: c => `<path d="M5 6.5h12v7H11l-3.5 3v-3H5z" stroke="${c}" stroke-width="1.8" stroke-linejoin="round" fill="none"/>`,
  list: c => `<path d="M6 7h10M6 11h10M6 15h6" stroke="${c}" stroke-width="1.8" stroke-linecap="round" fill="none"/>`,
  robot: c => robot(-1, -1, c, 'idle', 24),
}

/** The title row of a card on the desktop: an icon tile in the card's colour, a bold title, a dim line beside it and a thin
 *  rule under it. One picture of exactly `width` px, 36 px tall, so every card starts the same way. */
export function sectionHead(width: number, oIn: { title: string; sub?: string; colour: string; icon: SectionIcon }): { source: string; height: number; alt: string } {
  const o = { ...oIn, colour: hexOr(oIn.colour) }
  const h = 36
  const titleW = textWidth(o.title, 14) * 1.08 + 4
  const subRoom = width - 34 - titleW - 14
  const body =
    (o.icon === 'robot' ? '' : `<rect x="0" y="4" width="22" height="22" rx="7" fill="${o.colour}" fill-opacity=".18"/>`) +
    `<g class="${o.icon === 'robot' ? '' : 'pt'}" transform="translate(0 4)">${ICONS[o.icon](o.colour)}</g>` +
    // the title and the dim line are one text run, so the gap between them is the same whatever the title says
    `<text x="32" y="20" font-family="${FONT}" font-variant-numeric="tabular-nums"><tspan class="tx" font-size="14" font-weight="700">${xml(o.title)}</tspan>` +
    (o.sub && subRoom > 60 ? `<tspan class="t3" font-size="12" dx="10">${xml(fitText(o.sub, 12, subRoom))}</tspan>` : '') + `</text>` +
    `<line class="ln" x1="0" y1="${h - 3.5}" x2="${width}" y2="${h - 3.5}" stroke-width="1"/>`
  return { source: svgDoc(width, h, body), height: h, alt: o.sub ? `${o.title}. ${o.sub}` : o.title }
}

/** An agent's tile in the picker: its robot on a card, ringed in its colour when picked, grey and asleep when its CLI is not
 *  installed. 64 px square. Its source depends on (colour, picked, installed) only, so it never restarts its animation. */
export function agentFace(colour: string, picked: boolean, installed: boolean): { source: string; size: number } {
  const size = 64
  const c = installed ? hexOr(colour) : '#8A8FA3'
  const state: RobotState = !installed ? 'ended' : picked ? 'working' : 'idle'
  const body = `<rect class="pn" x="1" y="1" width="62" height="62" rx="18"/>` +
    (picked ? `<rect x="1" y="1" width="62" height="62" rx="18" fill="${c}" fill-opacity=".14"/>` : '') +
    `<rect x="1.5" y="1.5" width="61" height="61" rx="17.5" fill="none" stroke="${c}" stroke-opacity="${picked ? 1 : 0.32}" stroke-width="${picked ? 2.5 : 1.5}"/>` +
    robot(10, 11, c, state, 44)
  return { source: svgDoc(size, size, body), size }
}
