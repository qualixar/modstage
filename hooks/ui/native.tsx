// Native (non-animated) parts of the panel: they hold input and buttons, so they must never be
// redrawn by the animation clock. Inbox cards, the launcher, the message box, the setup view.
import type { StageAgent, Pending, RunSummary } from '../../types'

export type NativeAction =
  | { type: 'decide'; runId: string; approvalId: string; choice: 'allow' | 'allow_session' | 'deny' }
  | { type: 'send'; id: string; text: string }
  | { type: 'interrupt'; id: string }
  | { type: 'jump'; id: string }
  | { type: 'close'; id: string }
  | { type: 'launch'; engine: string; prompt: string; autonomy: 'ask' | 'auto'; model: string; effort?: string }
  | { type: 'pickAgent'; engine: string }
  | { type: 'pickModel'; model: string }
  | { type: 'pickEffort'; effort: string }

const ACCENT = '#D97757'
const WARN = '#E0AF68'
const MAX_CHIPS = 10

/** Claude Code's own subagent, offered beside the external agents. It starts through the mod API
 *  ($.agent.spawn), not the bridge, so it needs no CLI. */
export const CLAUDE_AGENT: StageAgent = {
  id: 'claude', name: 'Claude', color: ACCENT, protocol: 'subagent', steer: 'message',
  installed: true, version: 'subagent', command: 'built in', note: '', takes_model: true,
  default_model: 'inherits this session\'s model',
  models: [{ id: 'haiku', label: 'Haiku' }, { id: 'sonnet', label: 'Sonnet' }, { id: 'opus', label: 'Opus' },
           { id: 'claude-fable-5-1', label: 'Fable' }],
}
const ago = (t: number) => {
  const s = Math.max(0, Math.round(Date.now() / 1000 - t))
  return s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ago`
}

/** Needs-you inbox: every approval any agent is waiting on, oldest first. */
export function drawInbox(el: any, items: Pending[], colours: Record<string, string>, act: (a: NativeAction) => void) {
  const { Box, Text, Button } = el
  if (!items.length) return null
  return (
    <Box key="inbox" flexDirection="column" borderStyle="round" borderColor={WARN} paddingX={1}>
      <Text>
        <Text color={WARN} bold>⚑ Needs you</Text>
        <Text dimColor>  ·  {items.length} waiting  ·  no answer in 10 min = deny</Text>
      </Text>
      {items.slice(0, 4).map(p => (
        <Box key={`ask:${p.id}`} flexDirection="column" marginTop={1}>
          <Text wrap="truncate-end">
            <Text color={colours[p.engine] ?? '#CDD6F4'} bold>{p.engine}</Text>
            <Text dimColor> wants to </Text>
            <Text bold>{p.title}</Text>
            <Text dimColor>  {ago(p.asked_at)}</Text>
          </Text>
          {p.warning ? <Text color="#F7768E" wrap="truncate-end">⚠ {p.warning}</Text> : null}
          {p.detail ? <Text dimColor wrap="truncate-end">{p.detail.split('\n')[0]}</Text> : null}
          <Box flexDirection="row" columnGap={1}>
            <Button key={`allow:${p.id}`} label="Allow" variant="primary"
              onPress={() => act({ type: 'decide', runId: p.run_id, approvalId: p.id, choice: 'allow' })} />
            <Button key={`session:${p.id}`} label="Allow for this run"
              onPress={() => act({ type: 'decide', runId: p.run_id, approvalId: p.id, choice: 'allow_session' })} />
            <Button key={`deny:${p.id}`} label="Deny"
              onPress={() => act({ type: 'decide', runId: p.run_id, approvalId: p.id, choice: 'deny' })} />
          </Box>
        </Box>
      ))}
      {items.length > 4 ? <Text dimColor>+{items.length - 4} more waiting</Text> : null}
    </Box>
  )
}

/** Start a run in one click: every installed agent is a button, always visible. Clicking one opens
 *  its task box right below; clicking it again (or Cancel) closes it. Runs start in safe (ask) mode. */
export function drawLauncher(el: any, agents: StageAgent[], picked: string, model: string, canType: boolean,
                             act: (a: NativeAction) => void, effort = '') {
  const { Box, Text, Button } = el
  const Input = el.Input
  const ready = agents.filter(a => a.installed)
  const missing = agents.filter(a => !a.installed)
  const agent = ready.find(a => a.id === picked)
  const absent = missing.find(a => a.id === picked)
  if (!agents.length) {
    return <Text key="launcher" dimColor>Looking for agent CLIs on this machine…</Text>
  }
  return (
    <Box key="launcher" flexDirection="column" borderStyle="round" borderColor={agent?.color ?? '#45475A'} paddingX={1}>
      <Text wrap="truncate-end">
        <Text color={ACCENT} bold>✻ Start an agent</Text>
        <Text dimColor>  ·  click one, type the task, press Start</Text>
      </Text>
      <Box flexDirection="row" columnGap={1} rowGap={1} flexWrap="wrap">
        {ready.map(a => (
          <Button key={`pick:${a.id}`} label={`${a.id === picked ? '● ' : '+ '}${a.name}`}
            variant={a.id === picked ? 'primary' : undefined}
            onPress={() => act({ type: 'pickAgent', engine: a.id === picked ? '' : a.id })} />
        ))}
        {missing.map(a => (
          <Button key={`pick:${a.id}`} label={`${a.id === picked ? '● ' : '○ '}${a.name} (not installed)`}
            onPress={() => act({ type: 'pickAgent', engine: a.id === picked ? '' : a.id })} />
        ))}
      </Box>
      {absent ? (
        <Box key={`missing:${absent.id}`} flexDirection="column">
          <Text wrap="wrap"><Text color={WARN} bold>{absent.name} is not installed on this machine.</Text></Text>
          <Text wrap="wrap">{installLine(absent)}</Text>
          <Text dimColor wrap="wrap">Then reopen this panel, or ask Claude to run stage_agents to check.</Text>
          <Box flexDirection="row">
            <Button key="missing-close" label="Close" onPress={() => act({ type: 'pickAgent', engine: '' })} />
          </Box>
        </Box>
      ) : null}
      {agent ? (
        <Box key={`task:${agent.id}`} flexDirection="column">
          <Text wrap="truncate-end">
            <Text color={agent.color ?? '#CDD6F4'} bold>{agent.name}</Text>
            <Text dimColor>  ·  {agent.steer === 'native' ? 'you can steer it mid-turn' : 'your messages queue until its turn ends'}
              {'  ·  works in this session\'s folder, asks before risky steps'}</Text>
          </Text>
          {agent.note ? <Text color={WARN} wrap="wrap">⚠ {agent.note}</Text> : null}
          {drawModels(el, agent, model, act)}
          {drawEfforts(el, agent, model, effort, act)}
          {canType && Input ? (
            <Input key={`launch-task:${agent.id}`} submitLabel="Start" autoFocus
              placeholder={`What should ${agent.name} do?`}
              onSubmit={(v: string) => v.trim() && act({ type: 'launch', engine: agent.id, prompt: v.trim(), autonomy: 'ask', model, effort })} />
          ) : <Text dimColor>Typing is not available here; ask Claude to start the run.</Text>}
          <Box flexDirection="row">
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
      <Text dimColor>model</Text>
      <Box flexDirection="row" columnGap={1} rowGap={1} flexWrap="wrap">
        <Button key="model:" label={`${model ? '' : '● '}${def}`} variant={model ? undefined : 'primary'}
          onPress={() => act({ type: 'pickModel', model: '' })} />
        {listed.slice(0, MAX_CHIPS).map(m => (
          <Button key={`model:${m.id}`} label={`${m.id === model ? '● ' : ''}${m.label}`}
            variant={m.id === model ? 'primary' : undefined}
            onPress={() => act({ type: 'pickModel', model: m.id === model ? '' : m.id })} />
        ))}
      </Box>
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
  const { Box, Text, Button } = el
  const levels = effortsFor(agent, model)
  if (!levels.length) return null
  const entry = (agent.models ?? []).find(m => m.id === (model || agent.default_model))
  const fallback = entry?.default_effort || agent.default_effort || ''
  return (
    <Box key={`efforts:${agent.id}`} flexDirection="column">
      <Text dimColor>thinking effort</Text>
      <Box flexDirection="row" columnGap={1} rowGap={1} flexWrap="wrap">
        <Button key="effort:" label={`${effort ? '' : '● '}default${fallback ? ` (${fallback})` : ''}`} variant={effort ? undefined : 'primary'}
          onPress={() => act({ type: 'pickEffort', effort: '' })} />
        {levels.map(l => (
          <Button key={`effort:${l}`} label={`${l === effort ? '● ' : ''}${l}`} variant={l === effort ? 'primary' : undefined}
            onPress={() => act({ type: 'pickEffort', effort: l === effort ? '' : l })} />
        ))}
      </Box>
    </Box>
  )
}

/** The message box for the selected run. */
export function drawComposer(el: any, run: RunSummary, canType: boolean, act: (a: NativeAction) => void) {
  const { Box, Text, Button } = el
  const Input = el.Input
  const colour = run.color ?? '#CDD6F4'
  const running = run.status === 'running' || run.status === 'starting'
  if (run.steer === 'watch') {
    return (
      <Box key="composer" borderStyle="round" borderColor="#45475A" paddingX={1}>
        <Text dimColor>Claude subagent · watch only. Claude steers its own subagents; message Claude in the chat.</Text>
      </Box>
    )
  }
  const waiting = run.pending ?? []
  if (waiting.length) {
    // A message is never an approval: typing "yes" here once started a new turn over a waiting action.
    return (
      <Box key="composer" borderStyle="round" borderColor={WARN} paddingX={1} flexDirection="column">
        <Text wrap="truncate-end">
          <Text color={WARN} bold>⚑ Answer the approval above first</Text>
          <Text dimColor>  ·  {run.name ?? run.engine} is waiting on: {waiting[0]!.title}</Text>
        </Text>
        <Text dimColor wrap="truncate-end">Use Allow, Allow for this run or Deny in the Needs-you box. A message here would not answer it.</Text>
        <Box flexDirection="row" columnGap={1}>
          {running && run.steer !== 'message' ? <Button key="interrupt" label="◼ Interrupt" onPress={() => act({ type: 'interrupt', id: run.id })} /> : null}
          <Button key="close" label="✕ Close run" onPress={() => act({ type: 'close', id: run.id })} />
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
  return (
    <Box key="composer" borderStyle="round" borderColor={running ? colour : '#45475A'} paddingX={1} flexDirection="column">
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
        <Input key={`say:${run.id}`} submitLabel="Send"
          placeholder={`Tell ${run.name ?? run.engine} what to do next…`}
          onSubmit={(value: string) => value.trim() && act({ type: 'send', id: run.id, text: value.trim() })} />
      ) : <Text dimColor>Typing is not available on this surface; Claude can still message the run.</Text>}
      <Box flexDirection="row" columnGap={1}>
        {quick.map(([label, msg]) => (
          <Button key={`q:${label}`} label={label} onPress={() => act({ type: 'send', id: run.id, text: msg })} />
        ))}
        {running && run.queued ? <Button key="jump" label="Interrupt and send now" variant="primary" onPress={() => act({ type: 'jump', id: run.id })} /> : null}
        {running && run.steer !== 'message' ? <Button key="interrupt" label="◼ Interrupt" onPress={() => act({ type: 'interrupt', id: run.id })} /> : null}
        <Button key="close" label={run.steer === 'message' ? '✕ Close tab' : '✕ Close run'} onPress={() => act({ type: 'close', id: run.id })} />
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
    <Box key="setup" flexDirection="column" borderStyle="round" borderColor="#45475A" paddingX={1}>
      <Text bold>Plugged-in agents</Text>
      {agents.map(a => (
        <Text key={`ag:${a.id}`} wrap="truncate-end">
          <Text color={a.installed ? (a.color ?? '#CDD6F4') : '#585B70'}>{a.installed ? '●' : '○'} {a.name.padEnd(12)}</Text>
          <Text dimColor> {a.installed ? (a.version || 'installed') : `not installed. ${installLine(a)}`}</Text>
          <Text dimColor>  ·  {a.steer === 'native' ? 'steerable' : 'queued messages'}</Text>
          {a.note ? <Text color={WARN}>  ·  {a.note}</Text> : null}
        </Text>
      ))}
      <Text dimColor>Add any ACP agent in ~/.modstage/agents.json.</Text>
    </Box>
  )
}
