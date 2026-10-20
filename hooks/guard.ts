// Guards for Claude's own Bash tool. Mods are not a sandbox: these keep a well-meaning (or prompt-injected)
// Claude on the watched path. External agents run through ModStage so the user sees them, and nothing in
// this session talks to the bridge except the mod itself.

const ENGINES = new Set(['codex', 'muse', 'grok', 'agy', 'antigravity', 'kimi', 'qwen', 'opencode', 'hermes'])
// npx / bunx package names that start one of the engines
const PACKAGES: Record<string, string> = {
  '@openai/codex': 'codex', 'codex': 'codex', '@qwen-code/qwen-code': 'qwen', 'qwen-code': 'qwen',
  'opencode-ai': 'opencode', 'opencode': 'opencode', '@vibe-kit/grok-cli': 'grok', 'kimi-cli': 'kimi',
  'hermes-agent': 'hermes', 'hermes': 'hermes',
}
// first arguments that never start an agent turn
const SAFE_FIRST = new Set(['--help', '-h', 'help', '--version', '-V', '-v', 'version', 'login', 'logout', 'auth',
  'models', 'model-profile', 'mcp', 'config', 'doctor', 'debug', 'update', 'upgrade', 'plugins', 'skills',
  'sandbox', 'schema', 'trace', 'export', 'completion', 'serve', 'acp', 'stdio'])
// hermes flags that take a value, so the value is not mistaken for a subcommand
const HERMES_VALUE_FLAGS = new Set(['-m', '--model', '--provider', '--reasoning', '-t', '--toolsets', '--resume', '--continue', '--in', '--skills', '--usage-file'])
const HELP = new Set(['--help', '-h', '--version', '-V'])
const WRAPPERS = new Set(['command', 'exec', 'nohup', 'time', 'builtin', 'caffeinate', 'stdbuf', 'unbuffer'])
const SHELLS = new Set(['sh', 'bash', 'zsh', 'dash', 'fish'])

/** Remove heredoc bodies: text being written to a file is not a command. */
function stripHeredocs(command: string): string {
  const lines = command.split('\n')
  const out: string[] = []
  let end: string | null = null
  for (const line of lines) {
    if (end !== null) {
      if (line.trim() === end) end = null
      continue
    }
    out.push(line)
    const m = line.match(/<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1/)
    if (m) end = m[2]!
  }
  return out.join('\n')
}

/** Split a shell command into words, keeping quoted text as one word (quotes removed). */
function words(segment: string): string[] {
  const out: string[] = []
  let cur = ''
  let quote: string | null = null
  let has = false
  for (let i = 0; i < segment.length; i++) {
    const ch = segment[i]!
    if (quote) {
      if (ch === quote) quote = null
      else if (ch === '\\' && quote === '"' && i + 1 < segment.length) cur += segment[++i]
      else cur += ch
      continue
    }
    if (ch === '"' || ch === "'") { quote = ch; has = true; continue }
    if (ch === '\\' && i + 1 < segment.length) { cur += segment[++i]; has = true; continue }
    if (/\s/.test(ch)) {
      if (has || cur) out.push(cur)
      cur = ''
      has = false
      continue
    }
    cur += ch
    has = true
  }
  if (has || cur) out.push(cur)
  return out
}

/** Split on ; & | and newlines, but not inside quotes: `grep -E "a|b"` is one command, not two. */
function splitOutsideQuotes(command: string): string[] {
  const out: string[] = []
  let cur = ''
  let quote: string | null = null
  for (let i = 0; i < command.length; i++) {
    const ch = command[i]!
    if (quote) {
      cur += ch
      if (ch === '\\' && quote === '"' && i + 1 < command.length) cur += command[++i]
      else if (ch === quote) quote = null
      continue
    }
    if (ch === '\\' && i + 1 < command.length) { cur += ch + command[++i]; continue }
    if (ch === '"' || ch === "'") { quote = ch; cur += ch; continue }
    if (';&|\n'.includes(ch)) { out.push(cur); cur = ''; continue }
    cur += ch
  }
  out.push(cur)
  return out
}

/** Command segments: split on ; && || | & newlines, and the insides of $( ) and backticks. */
function segments(command: string): string[] {
  const inner: string[] = []
  const flat = command
    .replace(/\$\(([^()]*)\)/g, (_m, body) => { inner.push(body); return ' ' })
    .replace(/`([^`]*)`/g, (_m, body) => { inner.push(body); return ' ' })
  return [...splitOutsideQuotes(flat), ...inner.flatMap(segments)]
}

const base = (word: string) => word.replace(/^.*\//, '')

/** The engine a segment launches for an agent turn, or ''. Peels env assignments and wrappers. */
function launchIn(argv: string[], depth: number): string {
  let i = 0
  const skipFlags = (withValue: Set<string> = new Set()) => {
    while (i < argv.length && argv[i]!.startsWith('-')) i += withValue.has(argv[i]!) ? 2 : 1
  }
  for (;;) {
    while (i < argv.length && /^[A-Za-z_][A-Za-z0-9_]*=/.test(argv[i]!)) i++
    const w = base(argv[i] ?? '')
    if (!w) return ''
    if (w === 'command' && ['-v', '-V'].includes(argv[i + 1] ?? '')) return ''  // a lookup, not a launch
    if (WRAPPERS.has(w)) { i++; continue }
    if (w === 'env') { i++; skipFlags(new Set(['-u', '-C', '-S'])); continue }
    if (w === 'sudo') { i++; skipFlags(new Set(['-u', '-g', '-C', '-D', '-p', '-h', '-U'])); continue }
    if (w === 'nice') { i++; skipFlags(new Set(['-n'])); continue }
    if (w === 'timeout' || w === 'gtimeout') { i++; skipFlags(new Set(['-s', '-k'])); i++; continue }
    if (w === 'xargs') { i++; skipFlags(new Set(['-I', '-n', '-P', '-L', '-d', '-s', '-E'])); continue }
    if (SHELLS.has(w)) {
      const c = argv.indexOf('-c', i)
      if (c >= 0 && depth < 4) return agentLaunchedBy(argv[c + 1] ?? '', depth + 1)
      return ''
    }
    if (['npx', 'bunx', 'pnpx', 'pnpm', 'yarn', 'uvx'].includes(w)) {
      i++
      if ((w === 'pnpm' || w === 'yarn') && ['dlx', 'exec'].includes(argv[i] ?? '')) i++
      skipFlags(new Set(['-p', '--package']))
      const pkg = (argv[i] ?? '').replace(/@[^@/]*$/, '')  // drop a version: @openai/codex@1.2 -> @openai/codex
      const engine = PACKAGES[pkg] ?? (ENGINES.has(base(pkg)) ? base(pkg) : '')
      if (!engine) return ''
      return turnArgs(argv.slice(i + 1), engine) ? engine : ''
    }
    return ENGINES.has(w) && turnArgs(argv.slice(i + 1), w) ? w : ''
  }
}

/** True when these arguments start an agent turn (not help, version or a housekeeping subcommand). */
function turnArgs(args: string[], engine = ''): boolean {
  if (args.some(a => HELP.has(a))) return false
  if (engine === 'hermes') {
    // Hermes has many admin subcommands (sessions, gateway, cron, send, secrets, proxy ...), so only the forms that
    // start an agent turn go through ModStage: a bare `hermes`, `chat`, `acp` and `-z` / `--oneshot`.
    return args.some(a => a === '-z' || a === '--oneshot' || a.startsWith('--oneshot=') || a === 'chat' || a === 'acp')
      || !args.some((a, i) => !a.startsWith('-') && !HERMES_VALUE_FLAGS.has(args[i - 1] ?? ''))
  }
  const first = args.find(a => !a.startsWith('-')) ?? args[0] ?? ''
  return !(args.length && SAFE_FIRST.has(args[0]!)) && !SAFE_FIRST.has(first)
}

/** The agent CLI this Bash command would launch for a turn, or '' when it launches none. */
export function agentLaunchedBy(command: string, depth = 0): string {
  for (const seg of segments(stripHeredocs(command))) {
    const engine = launchIn(words(seg.trim()), depth)
    if (engine) return engine
  }
  return ''
}

/** True when a Bash command reaches the bridge's token file or port directly. Heredoc bodies are text being
 *  written, not commands, and a header name alone reaches nothing, so neither counts. */
export function touchesBridge(command: string, port = '47321'): boolean {
  const run = stripHeredocs(command)
  return /\.modstage\/token\b/.test(run) || new RegExp(`(127\\.0\\.0\\.1|localhost|0\\.0\\.0\\.0|\\[::1\\]):${port}\\b`).test(run)
}
