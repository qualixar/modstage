export type Usage = {
  input: number
  cached: number
  output: number
  reasoning: number
  context_used: number
  context_window: number | null
  cost_usd: number | null
}

/** One approval an agent is waiting on. No answer in time is a deny. */
export type Pending = {
  id: string
  run_id: string
  engine: string
  kind: string
  title: string
  detail: string
  warning: string
  asked_at: number
}

export type RunSummary = {
  id: string
  engine: string
  name?: string
  color?: string | null
  /** native = a message joins the running turn; queue = after the turn; watch = view only (Claude subagents) */
  steer?: string
  model: string | null
  label: string
  cwd: string
  status: string
  activity: string
  autonomy?: string
  elapsed_s: number
  quiet_s?: number
  stuck?: boolean
  usage: Usage
  events: number
  error: string | null
  pending?: Pending[]
  touched?: string[]
  owns?: string[]
  approval_note?: string
  /** the Claude Code session that started the run */
  owner?: string
  /** what the CLI refused because it could not ask (headless Antigravity); empty otherwise */
  blocked?: string
  /** messages the CLI holds until the running turn ends */
  queued?: number
  waiting_on_user?: boolean
}

export type RunEvent = { seq: number; ts: number; kind: string; text: string; detail?: string }

export type StageAgent = {
  id: string
  name: string
  color: string | null
  protocol: string
  steer: string
  installed: boolean
  version: string
  command: string
  note: string
  /** models the CLI listed (capped); empty when it has no list command */
  models?: Array<{ id: string; label: string; variant?: string }>
  /** the model it uses when none is picked, where known */
  default_model?: string
  /** whether a model can be passed at start */
  takes_model?: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'modstage': {
      runs: RunSummary[]
      selected: string
      feed: RunEvent[]
      partial: string
      bridgeError: string
      updatedAt: number
      tick: number
      inbox: Pending[]
      agents: StageAgent[]
      claudeRuns: RunSummary[]
      claudeFeeds: Record<string, RunEvent[]>
      launchAgent: string
      launchModel: string
      others: number
      /** the user's last own prompt: seconds since the epoch, and its text (first 500 chars) */
      userPrompt: { at: number; text: string }
    }
  }
}
