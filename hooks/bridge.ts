// Talking to the ModStage bridge on 127.0.0.1, and the shared state the panel reads.
export const BRIDGE = 'http://127.0.0.1:47321'


export type Json = Record<string, any>

export const env = { home: '', dataDir: '', root: '', useClient: true, token: '' }

export const kTok = (n: number | null | undefined) =>
  n == null ? '–' : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(Math.round(n))
