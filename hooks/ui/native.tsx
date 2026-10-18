// Native (non-animated) parts of the panel: they hold input and buttons, so they must never be redrawn by an animation
// clock. Inbox cards, the launcher, the message box, the setup view.
//
// Every block is one card: a round border in its own colour, one padding, a title row, then labelled rows that share one
// label column so controls line up. Text boxes are tall (several lines), full width and keep what was typed per box.
// A button that was just pressed shows what it did ("Allowing…", "✓ Allowed") for a moment, so a click is felt.
import type { StageAgent, Pending, RunSummary } from '../../types'
import { ENGINE, WARN as AMBER } from './palette.ts'

export type NativeAction =
  | { type: 'decide'; runId: string; approvalId: string; choice: 'allow' | 'allow_session' | 'deny' }
  | { type: 'send'; id: string; text: string; via?: string }
  | { type: 'interrupt'; id: string }
  | { type: 'jump'; id: string }
  | { type: 'close'; id: string }
  | { type: 'launch'; engine: string; prompt: string; autonomy: 'ask' | 'auto'; model: string; effort?: string }
  | { type: 'pickAgent'; engine: string }
  | { type: 'pickModel'; model: string }
  | { type: 'pickEffort'; effort: string }

/** What is pressed right now: a button's slot to `busy` (the bridge has not answered yet) or `done` (it did, and the
 *  button says so for a moment). A failed action never reaches `done`: its button simply returns. */
export type Pressed = Record<string, 'busy' | 'done'>

/** How long a pressed button shows its result, at least. */
export const PRESS_MS = 800
/** How long a line confirms an approval the person just answered, after its card is gone. */
export const ANSWER_MS = 1800

/** An approval answered a moment ago: kept to confirm what the click did. */
export type Answered = Record<string, { engine: string; title: string; choice: 'allow' | 'allow_session' | 'deny' }>

/** The slot of the button that performs an action: its key, and for the buttons of one run's card that run, so pressing
 *  Close on one run never marks another run's Close. */
export function pressKey(a: { type: string } & Record<string, any>): string {
  switch (a.type) {
    case 'decide': return `${a.choice === 'allow' ? 'allow' : a.choice === 'allow_session' ? 'session' : 'deny'}:${a.approvalId}`
    case 'launch': return `launch-start|${a.engine}`
    case 'send': return `${a.via ? `q:${a.via}` : 'send-btn'}|${a.id}`
    case 'interrupt': case 'close': case 'jump': return `${a.type}|${a.id}`
    default: return ''
  }
}

/** The box whose draft an action empties once it has gone through. */
export function draftKeyOf(a: { type: string } & Record<string, any>): string {
  return a.type === 'send' && !a.via ? `say:${a.id}` : a.type === 'launch' ? `launch:${a.engine}` : ''
}

// What a person typed into a box and has not sent yet, per box, kept in this module so a redraw (a poll, a click on
// another tab) never empties a half-written message. No atom: typing must not redraw the pane.
const drafts = new Map<string, string>()
export const draftOf = (key: string): string => drafts.get(key) ?? ''
export const setDraft = (key: string, text: string): void => { if (text) drafts.set(key, text); else drafts.delete(key) }
export const clearDrafts = (): void => drafts.clear()
/** The `value` prop only when there is a draft to restore: a box with nothing saved is never told its text. */
const asValue = (d: string): { value?: string } => (d ? { value: d } : {})

const ACCENT = '#D97757'
const WARN = AMBER
const OK = '#5FD38D'
const BAD = '#F7768E'
const LINE = '#45475A'
const LABEL_W = 9 // the shared label column of every labelled row
const MAX_CHIPS = 10
const TASK_ROWS = 4
const MESSAGE_ROWS = 3

/** Claude Code's own subagent, offered beside the external agents. It starts through the mod API
 *  ($.agent.spawn), not the bridge, so it needs no CLI. */
export const CLAUDE_AGENT: StageAgent = {
  id: 'claude', name: 'Claude', color: ENGINE.claude, protocol: 'subagent', steer: 'message',
  installed: true, version: 'subagent', command: 'built in', note: '', takes_model: true,
  default_model: 'inherits this session\'s model',
  models: [{ id: 'haiku', label: 'Haiku' }, { id: 'sonnet', label: 'Sonnet' }, { id: 'opus', label: 'Opus' },
           { id: 'claude-fable-5-1', label: 'Fable' }],
}
const ago = (t: number) => {
  const s = Math.max(0, Math.round(Date.now() / 1000 - t))
  return s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ago`
}

/** A button that shows `busy` while the bridge has not answered and `done` once it has (a click is felt), `label` otherwise.
 *  `slot` is where its state is kept (see pressKey); the button's own key stays `key`. */
function press(el: any, p: { key: string; slot: string; label: string; busy: string; done: string; pressed: Pressed; onPress: () => void; variant?: 'primary' | 'secondary' }) {
  const { Button } = el
  const state = p.pressed[p.slot]
  return <Button key={p.key} label={state === 'done' ? p.done : state === 'busy' ? p.busy : p.label} variant={state ? 'primary' : p.variant}
    onPress={() => { if (!state) p.onPress() }} />
}

/** A labelled row: a fixed label column, then the controls. Every row of a card uses it, so they line up. */
function row(el: any, key: string, label: string, children: any) {
  const { Box, Text } = el
  return (
    <Box key={key} flexDirection="row" columnGap={1}>
      <Box width={LABEL_W} flexShrink={0}><Text dimColor>{label}</Text></Box>
      <Box flexDirection="row" columnGap={1} rowGap={1} flexWrap="wrap" flexGrow={1} flexShrink={1} minWidth={0}>{children}</Box>
    </Box>
  )
}

/** Needs-you inbox: every approval any agent is waiting on, oldest first. */
export function drawInbox(el: any, items: Pending[], colours: Record<string, string>, act: (a: NativeAction) => void,
                          pressed: Pressed = {}, answered: Answered = {}) {
  const { Box, Text } = el
  const done = Object.entries(answered)
  if (!items.length && !done.length) return null
  return (
    <Box key="inbox" flexDirection="column" borderStyle="round" borderColor={items.length ? WARN : OK} paddingX={1} rowGap={1}>
      <Text>
        <Text color={items.length ? WARN : OK} bold>{items.length ? '⚑ Needs you' : '✓ All answered'}</Text>
        {items.length ? <Text dimColor>  ·  {items.length} waiting  ·  no answer in 10 min = deny</Text> : null}
      </Text>
      {done.map(([id, a]) => (
        <Text key={`done:${id}`} wrap="truncate-end">
          <Text color={a.choice === 'deny' ? BAD : OK} bold>{a.choice === 'deny' ? '✓ Denied' : a.choice === 'allow_session' ? '✓ Allowed for this run' : '✓ Allowed'}</Text>
          <Text dimColor>  ·  </Text>
          <Text color={colours[a.engine] ?? ENGINE[a.engine] ?? '#CDD6F4'} bold>{a.engine}</Text>
          <Text dimColor> {a.title}</Text>
        </Text>
      ))}
      {items.slice(0, 4).map(p => (
        <Box key={`ask:${p.id}`} flexDirection="column">
          <Text wrap="truncate-end">
            <Text color={colours[p.engine] ?? ENGINE[p.engine] ?? '#CDD6F4'} bold>{p.engine}</Text>
            <Text dimColor> wants to </Text>
            <Text bold>{p.title}</Text>
            <Text dimColor>  {ago(p.asked_at)}</Text>
          </Text>
          {p.warning ? <Text color={BAD} wrap="truncate-end">⚠ {p.warning}</Text> : null}
          {p.detail ? <Text dimColor wrap="truncate-end">{p.detail.split('\n')[0]}</Text> : null}
          <Box flexDirection="row" columnGap={1} marginTop={1}>
            {press(el, { key: `allow:${p.id}`, slot: `allow:${p.id}`, label: 'Allow', busy: 'Allowing…', done: '✓ Allowed', pressed, variant: 'primary',
              onPress: () => act({ type: 'decide', runId: p.run_id, approvalId: p.id, choice: 'allow' }) })}
            {press(el, { key: `session:${p.id}`, slot: `session:${p.id}`, label: 'Allow for this run', busy: 'Allowing…', done: '✓ Allowed for this run', pressed,
              onPress: () => act({ type: 'decide', runId: p.run_id, approvalId: p.id, choice: 'allow_session' }) })}
            {press(el, { key: `deny:${p.id}`, slot: `deny:${p.id}`, label: 'Deny', busy: 'Denying…', done: '✓ Denied', pressed,
              onPress: () => act({ type: 'decide', runId: p.run_id, approvalId: p.id, choice: 'deny' }) })}
          </Box>
        </Box>
      ))}
      {items.length > 4 ? <Text dimColor>+{items.length - 4} more waiting</Text> : null}
    </Box>
  )
}

/** The hint under a text box: what Enter does, and that a pasted block stays whole. */
const boxHint = (el: any, key: string, enter: string) => {
  const { Text } = el
  return <Text key={key} dimColor wrap="truncate-end">Enter {enter} · a new line is typed as in the prompt box · paste as much text as you like</Text>
}

/** Start a run in one click: every installed agent is a button, always visible. Clicking one opens
 *  its task box right below; clicking it again (or Cancel) closes it. Runs start in safe (ask) mode. */
export function drawLauncher(el: any, agents: StageAgent[], picked: string, model: string, canType: boolean,
                             act: (a: NativeAction) => void, effort = '', pressed: Pressed = {}) {
  const { Box, Text, Button } = el
  const Input = el.Input
  const ready = agents.filter(a => a.installed)
  const missing = agents.filter(a => !a.installed)
  const agent = ready.find(a => a.id === picked)
  const absent = missing.find(a => a.id === picked)
  if (!agents.length) {
    return <Text key="launcher" dimColor>Looking for agent CLIs on this machine…</Text>
  }
  const submit = (a: StageAgent, v: string) => {
    const prompt = v.trim()
    if (!prompt) return
    act({ type: 'launch', engine: a.id, prompt, autonomy: 'ask', model, effort }) // the draft is emptied once it has started
  }
  return (
    <Box key="launcher" flexDirection="column" borderStyle="round" borderColor={agent?.color ?? LINE} paddingX={1} rowGap={1}>
      <Text wrap="truncate-end">
        <Text color={ACCENT} bold>✻ Start an agent</Text>
        <Text dimColor>  ·  pick one, describe the task, press Start</Text>
      </Text>
      {row(el, 'agents', 'agent', [
        ...ready.map(a => (
          <Button key={`pick:${a.id}`} label={`${a.id === picked ? '● ' : '+ '}${a.name}`}
            variant={a.id === picked ? 'primary' : undefined}
            onPress={() => act({ type: 'pickAgent', engine: a.id === picked ? '' : a.id })} />
        )),
        ...missing.map(a => (
          <Button key={`pick:${a.id}`} label={`${a.id === picked ? '● ' : '○ '}${a.name} (not installed)`}
            onPress={() => act({ type: 'pickAgent', engine: a.id === picked ? '' : a.id })} />
        )),
      ])}
      {absent ? (
        <Box key={`missing:${absent.id}`} flexDirection="column">
          <Text wrap="wrap"><Text color={WARN} bold>{absent.name} is not installed on this machine.</Text></Text>
          <Text wrap="wrap">{installLine(absent)}</Text>
          <Text dimColor wrap="wrap">Then reopen this panel, or ask Claude to run stage_agents to check.</Text>
          <Box flexDirection="row" marginTop={1}>
            <Button key="missing-close" label="Close" onPress={() => act({ type: 'pickAgent', engine: '' })} />
          </Box>
        </Box>
      ) : null}
      {agent ? (
        <Box key={`task:${agent.id}`} flexDirection="column" rowGap={1}>
          <Text wrap="truncate-end">
            <Text color={agent.color ?? '#CDD6F4'} bold>{agent.name}</Text>
            <Text dimColor>  ·  {agent.steer === 'native' ? 'you can steer it mid-turn' : 'your messages queue until its turn ends'}
              {'  ·  works in this session\'s folder, asks before risky steps'}</Text>
          </Text>
          {agent.note ? <Text color={WARN} wrap="wrap">⚠ {agent.note}</Text> : null}
          {drawModels(el, agent, model, act)}
          {drawEfforts(el, agent, model, effort, act)}
          {canType && Input ? (
            <Box key={`taskbox:${agent.id}`} flexDirection="column">
              <Input key={`launch-task:${agent.id}`} rows={TASK_ROWS} submitLabel="Start" autoFocus
                placeholder={`What should ${agent.name} do? Describe it, or paste what it needs to know.`}
                {...asValue(draftOf(`launch:${agent.id}`))} onInput={(v: string) => setDraft(`launch:${agent.id}`, v)}
                onSubmit={(v: string) => submit(agent, v)} />
              {boxHint(el, `hint:${agent.id}`, 'starts the run')}
            </Box>
          ) : <Text dimColor>Typing is not available here; ask Claude to start the run.</Text>}
          <Box flexDirection="row" columnGap={1}>
            {canType && Input ? press(el, { key: 'launch-start', slot: `launch-start|${agent.id}`, label: 'Start', busy: 'Starting…', done: '✓ Started', pressed, variant: 'primary',
              onPress: () => submit(agent, draftOf(`launch:${agent.id}`)) }) : null}
            <Button key="launch-cancel" label="Cancel" onPress={() => act({ type: 'pickAgent', engine: '' })} />
          </Box>
        </Box>
      ) : null}
    </Box>
  )
}

/** Model chips for the picked agent: "default" first, then what its CLI listed. Claude (the
 *  orchestrator) can pass any model id through stage_start, including ones not shown here. */
function drawModels(el: any, agent: StageAgent, model: string, act: (a: NativeAction) => void) {
  const { Box, Text, Button } = el
  if (!agent.takes_model) return null
  const listed = agent.models ?? []
  const def = agent.default_model ? `default (${agent.default_model})` : 'default'
  return (
    <Box key={`models:${agent.id}`} flexDirection="column">
      {row(el, `models:${agent.id}`, 'model', [
        <Button key="model:" label={`${model ? '' : '● '}${def}`} variant={model ? undefined : 'primary'}
          onPress={() => act({ type: 'pickModel', model: '' })} />,
        ...listed.slice(0, MAX_CHIPS).map(m => (
          <Button key={`model:${m.id}`} label={`${m.id === model ? '● ' : ''}${m.label}`}
            variant={m.id === model ? 'primary' : undefined}
            onPress={() => act({ type: 'pickModel', model: m.id === model ? '' : m.id })} />
        )),
      ])}
      {listed.length > MAX_CHIPS ? (
        <Text dimColor wrap="truncate-end">+{listed.length - MAX_CHIPS} more: ask Claude to start it on any model id</Text>
      ) : !listed.length ? <Text dimColor wrap="truncate-end">this CLI lists no models; ask Claude to start it on a specific model id</Text> : null}
    </Box>
  )
}

/** The thinking levels this agent takes for the picked model (its default model when none is picked): the model's own
 *  list from its CLI, else the agent's one list. Empty means the CLI has no effort setting ModStage can apply. */
export function effortsFor(agent: StageAgent, model: string): string[] {
  const entry = (agent.models ?? []).find(m => m.id === (model || agent.default_model) || m.variant === (model || agent.default_model))
  return entry?.efforts ?? agent.efforts ?? []
}

/** Thinking-effort chips for the picked agent and model: "default" first (what its own config uses), then each level. */
function drawEfforts(el: any, agent: StageAgent, model: string, effort: string, act: (a: NativeAction) => void) {
  const { Button } = el
  const levels = effortsFor(agent, model)
  if (!levels.length) return null
  const entry = (agent.models ?? []).find(m => m.id === (model || agent.default_model))
  const fallback = entry?.default_effort || agent.default_effort || ''
  return row(el, `efforts:${agent.id}`, 'effort', [
    <Button key="effort:" label={`${effort ? '' : '● '}default${fallback ? ` (${fallback})` : ''}`} variant={effort ? undefined : 'primary'}
      onPress={() => act({ type: 'pickEffort', effort: '' })} />,
    ...levels.map(l => (
      <Button key={`effort:${l}`} label={`${l === effort ? '● ' : ''}${l}`} variant={l === effort ? 'primary' : undefined}
        onPress={() => act({ type: 'pickEffort', effort: l === effort ? '' : l })} />
    )),
  ])
}

/** The message box for the selected run. */
export function drawComposer(el: any, run: RunSummary, canType: boolean, act: (a: NativeAction) => void, pressed: Pressed = {}) {
  const { Box, Text, Button } = el
  const Input = el.Input
  const colour = run.color ?? ENGINE[run.engine] ?? '#CDD6F4'
  const running = run.status === 'running' || run.status === 'starting'
  if (run.steer === 'watch') {
    return (
      <Box key="composer" borderStyle="round" borderColor={LINE} paddingX={1}>
        <Text dimColor>Claude subagent · watch only. Claude steers its own subagents; message Claude in the chat.</Text>
      </Box>
    )
  }
  const waiting = run.pending ?? []
  if (waiting.length) {
    // A message is never an approval: typing "yes" here once started a new turn over a waiting action.
    return (
      <Box key="composer" borderStyle="round" borderColor={WARN} paddingX={1} flexDirection="column" rowGap={1}>
        <Text wrap="truncate-end">
          <Text color={WARN} bold>⚑ Answer the approval above first</Text>
          <Text dimColor>  ·  {run.name ?? run.engine} is waiting on: {waiting[0]!.title}</Text>
        </Text>
        <Text dimColor wrap="truncate-end">Use Allow, Allow for this run or Deny in the Needs-you box. A message here would not answer it.</Text>
        <Box flexDirection="row" columnGap={1}>
          {running && run.steer !== 'message'
            ? press(el, { key: 'interrupt', slot: `interrupt|${run.id}`, label: '◼ Interrupt', busy: 'Interrupting…', done: '✓ Interrupted', pressed, onPress: () => act({ type: 'interrupt', id: run.id }) }) : null}
          {press(el, { key: 'close', slot: `close|${run.id}`, label: '✕ Close run', busy: 'Closing…', done: '✓ Closed', pressed, onPress: () => act({ type: 'close', id: run.id }) })}
        </Box>
      </Box>
    )
  }
  const stopped = run.status === 'done' || run.status === 'error'
  const how = run.steer === 'message' ? (running ? 'reaches the subagent after its current step' : 'continues the subagent')
    : stopped ? 'agent stopped · a message restarts it with a recap of this run'
    : !running ? 'starts a follow-up turn'
    : run.steer === 'native' ? 'joins the running turn now' : 'queued until the current turn ends'
  const quick: Array<[string, string]> = [
    ['Status?', 'Give me a two-line status: what you have done and what is next.'],
    ['Wrap up', 'Stop adding scope. Finish the current step, then summarise what you changed and what is left.'],
  ]
  const draftKey = `say:${run.id}`
  const send = (text: string, via?: string) => {
    const t = text.trim()
    if (!t) return
    act({ type: 'send', id: run.id, text: t, ...(via ? { via } : {}) }) // the draft is emptied once it has been sent
  }
  return (
    <Box key="composer" borderStyle="round" borderColor={running ? colour : LINE} paddingX={1} flexDirection="column" rowGap={1}>
      <Text wrap="truncate-end">
        <Text color={colour} bold>› message {run.name ?? run.engine}</Text>
        <Text dimColor>  ·  {how}</Text>
      </Text>
      {run.blocked && !running ? (
        <Text key="blocked" color={WARN} wrap="wrap">⛔ Turn ended blocked: {run.blocked}</Text>
      ) : null}
      {running && run.queued ? (
        <Text color={WARN} wrap="truncate-end">⇢ {run.queued} queued · runs when the turn ends{run.engine === 'antigravity' ? ' · sending now restarts agy with a recap' : ''}</Text>
      ) : null}
      {canType && Input ? (
        <Box flexDirection="column">
          <Input key={`say:${run.id}`} rows={MESSAGE_ROWS} submitLabel="Send"
            placeholder={`Tell ${run.name ?? run.engine} what to do next… paste text, notes or a stack trace.`}
            {...asValue(draftOf(draftKey))} onInput={(v: string) => setDraft(draftKey, v)}
            onSubmit={(value: string) => send(value)} />
          {boxHint(el, `hint:${run.id}`, 'sends')}
        </Box>
      ) : <Text dimColor>Typing is not available on this surface; Claude can still message the run.</Text>}
      <Box flexDirection="row" justifyContent="space-between" columnGap={2}>
        <Box flexDirection="row" columnGap={1}>
          {canType && Input ? press(el, { key: 'send-btn', slot: `send-btn|${run.id}`, label: 'Send', busy: 'Sending…', done: '✓ Sent', pressed, variant: 'primary', onPress: () => send(draftOf(draftKey)) }) : null}
          {quick.map(([label, msg]) => press(el, { key: `q:${label}`, slot: `q:${label}|${run.id}`, label, busy: 'Sending…', done: '✓ Sent', pressed, onPress: () => send(msg, label) }))}
          {running && run.queued
            ? press(el, { key: 'jump', slot: `jump|${run.id}`, label: 'Interrupt and send now', busy: 'Interrupting…', done: '✓ Sent', pressed, variant: 'primary', onPress: () => act({ type: 'jump', id: run.id }) }) : null}
        </Box>
        <Box flexDirection="row" columnGap={1}>
          {running && run.steer !== 'message'
            ? press(el, { key: 'interrupt', slot: `interrupt|${run.id}`, label: '◼ Interrupt', busy: 'Interrupting…', done: '✓ Interrupted', pressed, onPress: () => act({ type: 'interrupt', id: run.id }) }) : null}
          {press(el, { key: 'close', slot: `close|${run.id}`, label: run.steer === 'message' ? '✕ Close tab' : '✕ Close run', busy: 'Closing…', done: '✓ Closed', pressed,
            onPress: () => act({ type: 'close', id: run.id }) })}
        </Box>
      </Box>
    </Box>
  )
}

/** The line that tells a person how to install a missing agent's CLI. */
export function installLine(a: StageAgent): string {
  const how = a.install ?? ''
  return how ? `Install it: ${how}` : `Install it and make sure \`${a.command.split(' ')[0]}\` is on your PATH.`
}

/** Shown when there are no runs: what is plugged in and ready. */
export function drawSetup(el: any, agents: StageAgent[]) {
  const { Box, Text } = el
  if (!agents.length) return null
  return (
    <Box key="setup" flexDirection="column" borderStyle="round" borderColor={LINE} paddingX={1}>
      <Text bold>Plugged-in agents</Text>
      {agents.map(a => (
        <Text key={`ag:${a.id}`} wrap="truncate-end">
          <Text color={a.installed ? (a.color ?? ENGINE[a.id] ?? '#CDD6F4') : '#585B70'}>{a.installed ? '●' : '○'} {a.name.padEnd(12)}</Text>
          <Text dimColor> {a.installed ? (a.version || 'installed') : `not installed. ${installLine(a)}`}</Text>
          <Text dimColor>  ·  {a.steer === 'native' ? 'steerable' : 'queued messages'}</Text>
          {a.note ? <Text color={WARN}>  ·  {a.note}</Text> : null}
        </Text>
      ))}
      <Text dimColor>Add any ACP agent in ~/.modstage/agents.json.</Text>
    </Box>
  )
}
