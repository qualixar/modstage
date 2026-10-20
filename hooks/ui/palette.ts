// One colour per agent, no two alike: hues are spread round the wheel at similar brightness so each reads on a dark or a
// light panel. The bridge sends a run's own colour (bridge/modstage/registry.py keeps the same values); these are the
// fallback for a run that carries none and for the Claude subagent tab.
export const ENGINE: Record<string, string> = {
  claude: '#E8775A', // coral
  codex: '#4C9BFF', // blue
  muse: '#A77BFF', // violet
  grok: '#F5B93A', // amber
  antigravity: '#2EC4B6', // teal
  kimi: '#FF6B9D', // pink
  qwen: '#6FCF5B', // green
  opencode: '#8E9AAF', // slate
  hermes: '#E4572E', // vermilion
}

export const ACCENT = '#D97757' // ModStage's own coral, used for the wordmark and primary actions
export const FALLBACK = '#CDD6F4'

export const STATUS: Record<string, string> = {
  running: '#8B7CFF', starting: '#8B7CFF', idle: '#5FD38D', done: '#7F849C', error: '#F7768E', interrupted: '#F5B93A',
}
export const WARN = '#F5B93A'
export const BAD = '#F7768E'
export const OK = '#5FD38D'

/** A colour from outside (a run's own, from ~/.modstage/agents.json) only if it is a plain hex value: it is written into
 *  vector markup, so anything else is dropped. */
export const safeColour = (c: unknown): string | undefined => (typeof c === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(c) ? c : undefined)

/** The colour a run is drawn in: its own, else its agent's, else neutral. */
export const colourOf = (run: { engine: string; color?: string | null }): string => safeColour(run.color) ?? ENGINE[run.engine] ?? FALLBACK

const hex = (c: string): [number, number, number] => {
  const h = c.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map(x => x + x).join('') : h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
const toHex = (r: number, g: number, b: number) =>
  '#' + [r, g, b].map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')

/** `a` blended towards `b` by `t` (0 to 1). */
export function mix(a: string, b: string, t: number): string {
  const [r1, g1, b1] = hex(a)
  const [r2, g2, b2] = hex(b)
  return toHex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)
}
