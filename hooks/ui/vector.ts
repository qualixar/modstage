// Vector drawing helpers for the desktop panel. The engine draws an Svg element as an image, so everything here is
// plain markup built from strings: no script, no external references. Colours that must follow the theme are classes
// (light by default, dark under prefers-color-scheme); the agent's own colour is always passed in as an attribute.
//
// textWidth, fitText and the escape table follow the small helpers in ersinkoc/claude-mods (MIT, Copyright (c) 2026
// Ersin Koç); see THIRD-PARTY-NOTICES.md.

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

/** Shared styles. One 2.4 s beat drives every loop (pulse, scan, blink), so animations that run together stay in step. */
const CSS = `
.pn{fill:#f3f3f1}.ln{stroke:#e0dfda}.tx{fill:#1c1c1a}.t2{fill:#5b5b57}.t3{fill:#8a8a85}.tk{fill:#e3e2dd}.vz{fill:#14151c}
@media (prefers-color-scheme: dark){.pn{fill:#262624}.ln{stroke:#3a3a37}.tx{fill:#ecebe8}.t2{fill:#b3b2ad}.t3{fill:#7d7c77}.tk{fill:#33332f}.vz{fill:#0d0e14}}
@media (prefers-color-scheme: light){.pt{filter:brightness(.68) saturate(1.1)}}
.pulse{animation:pl 2.4s ease-in-out infinite}
@keyframes pl{0%,100%{opacity:1}50%{opacity:.3}}
.scan{transform-box:fill-box;transform-origin:center;animation:sc 2.4s ease-in-out infinite}
@keyframes sc{0%,100%{transform:translateX(-7px)}50%{transform:translateX(7px)}}
.blink{transform-box:fill-box;transform-origin:center;animation:bl 4.8s ease-in-out infinite}
@keyframes bl{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.08)}}
.breathe{animation:br 4.8s ease-in-out infinite}
@keyframes br{0%,100%{opacity:.55}50%{opacity:1}}
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
export function pill(x: number, y: number, label: string, colour: string, o: { dot?: boolean; pulse?: boolean; h?: number; size?: number } = {}): { svg: string; w: number } {
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
export function bar(x: number, y: number, w: number, h: number, ratio: number | null, colour: string): string {
  const r = ratio == null || !Number.isFinite(ratio) ? 0 : Math.max(0, Math.min(1, ratio))
  const fw = r > 0 ? Math.max(h, w * r) : 0
  return `<rect class="tk" x="${x}" y="${y}" width="${w}" height="${h}" rx="${h / 2}"/>` +
    (fw ? `<rect x="${x}" y="${y}" width="${fw.toFixed(1)}" height="${h}" rx="${h / 2}" fill="${colour}"/>` : '')
}

export type RobotState = 'working' | 'waiting' | 'ended' | 'failed' | 'idle'
export const robotState = (status: string, waitingOnYou = false): RobotState =>
  status === 'running' || status === 'starting' ? (waitingOnYou ? 'waiting' : 'working')
    : status === 'error' ? 'failed' : status === 'idle' ? 'idle' : 'ended'

/** The agent's mark: a squared head with a visor, an antenna and a neck, in the agent's colour. Drawn in a 48 x 48 cell
 *  at (x, y). Working: a light sweeps the visor and the antenna beats. Waiting on you: the antenna beats amber, eyes lit.
 *  Idle: two eyes that blink. Ended: eyes closed. Failed: a red flicker. Every loop shares the 2.4 s beat. */
export function robot(x: number, y: number, colour: string, state: RobotState, size = 48): string {
  const k = size / 48
  const lit = state === 'failed' ? '#F7768E' : state === 'waiting' ? '#F5B93A' : colour
  const eyes =
    state === 'working' ? `<rect class="scan" x="20" y="22.5" width="8" height="5" rx="2.5" fill="${lit}"/>`
    : state === 'waiting' ? `<rect x="16.5" y="22" width="5" height="6" rx="2.5" fill="${lit}"/><rect x="26.5" y="22" width="5" height="6" rx="2.5" fill="${lit}"/>`
    : state === 'failed' ? `<g class="flick" stroke="${lit}" stroke-width="2" stroke-linecap="round"><path d="M17 23l5 4M22 23l-5 4M26 23l5 4M31 23l-5 4"/></g>`
    : state === 'idle' ? `<rect class="blink" x="16.5" y="22" width="5" height="6" rx="2.5" fill="${lit}"/><rect class="blink" x="26.5" y="22" width="5" height="6" rx="2.5" fill="${lit}"/>`
    : `<path d="M16 25.5h6M26 25.5h6" stroke="${colour}" stroke-opacity=".5" stroke-width="2" stroke-linecap="round"/>`
  const beat = state === 'working' || state === 'waiting' ? ' class="pulse"' : ''
  return `<g transform="translate(${x} ${y}) scale(${k})">` +
    `<rect x="3" y="21" width="3" height="10" rx="1.5" fill="${colour}" fill-opacity=".55"/><rect x="42" y="21" width="3" height="10" rx="1.5" fill="${colour}" fill-opacity=".55"/>` +
    `<rect x="7" y="11" width="34" height="30" rx="10" class="pn"/>` +
    `<rect x="7" y="11" width="34" height="30" rx="10" fill="none" stroke="${colour}" stroke-width="1.6" stroke-opacity=".9"/>` +
    `<rect x="11.5" y="18" width="25" height="14" rx="7" class="vz"/>` + eyes +
    `<path d="M24 11V6" stroke="${colour}" stroke-width="1.6" stroke-linecap="round"/><circle cx="24" cy="4.5" r="2.4" fill="${lit}"${beat}/>` +
    `<rect x="16" y="42" width="16" height="3.5" rx="1.75" fill="${colour}" fill-opacity=".45"/>` +
    `</g>`
}
