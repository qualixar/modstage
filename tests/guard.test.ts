import { expect, test } from 'claude-code/testing'

test('direct codex exec in Bash is refused and pointed at ModStage', async ($, on) => {
  let ran = false
  on('tool.call', { tool: 'Bash' }, () => {
    ran = true
    return { result: { stdout: '', stderr: '', interrupted: false } } as any
  })
  const res: any = await $.tool.call({ tool: 'Bash', command: 'cd /tmp && codex exec -m gpt-6-luna "hi"' } as any)
  expect(ran).toBe(false)
  expect(String(res.deny ?? res.text)).toContain('stage_start')
})

test('muse exec and grok -p are refused too', async ($, on) => {
  on('tool.call', { tool: 'Bash' }, () => ({ result: { stdout: '', stderr: '', interrupted: false } }) as any)
  for (const command of ['muse exec --json "x"', 'grok -p "x" --output-format json']) {
    const res: any = await $.tool.call({ tool: 'Bash', command } as any)
    expect(String(res.deny ?? res.text)).toContain('stage_start')
  }
})

test('ordinary Bash commands pass through', async ($, on) => {
  let ran = false
  on('tool.call', { tool: 'Bash' }, () => {
    ran = true
    return { result: { stdout: 'ok', stderr: '', interrupted: false } } as any
  })
  await $.tool.call({ tool: 'Bash', command: 'ls -la && echo codex is a word here' } as any)
  expect(ran).toBe(true)
})

test('help, version and plain text mentioning agent CLIs are not blocked', async ($, on) => {
  let ran = 0
  on('tool.call', { tool: 'Bash' }, () => {
    ran += 1
    return { result: { stdout: '', stderr: '', interrupted: false } } as any
  })
  const g = 'grok'
  const c = 'codex'
  for (const command of [
    `${g} agent --help`,
    `${c} exec --version`,
    `cat > notes.md <<'X'\nGrok runs as ${g} agent stdio over ACP\nX`,
    `echo "use ${c} exec carefully"`,
    `git commit -m "document ${g} -p usage"`,
  ]) {
    await $.tool.call({ tool: 'Bash', command } as any)
  }
  expect(ran).toBe(5)
})

test('a real launch after && or in a subshell is still blocked', async ($, on) => {
  on('tool.call', { tool: 'Bash' }, () => ({ result: { stdout: '', stderr: '', interrupted: false } }) as any)
  const g = 'grok'
  const c = 'codex'
  const m = 'muse'
  for (const command of [`cd /tmp && ${c} exec "hi"`, `OUT=$(${g} -p "x")`, `FOO=1 ${m} exec --json "x"`]) {
    const res: any = await $.tool.call({ tool: 'Bash', command } as any)
    expect(String(res.deny ?? res.text)).toContain('stage_start')
  }
})

// Bypasses the 17 Oct audit found against the old regex guard, and engines it did not cover.
test('wrappers, flag order and every engine are caught', async ($, on) => {
  on('tool.call', { tool: 'Bash' }, () => ({ result: { stdout: '', stderr: '', interrupted: false } }) as any)
  const [c, g, m] = ['codex', 'grok', 'muse']
  for (const command of [
    `env FOO=1 ${c} exec "hi"`, `npx -y @openai/${c} exec "hi"`, `sh -c '${c} exec "hi"'`, `bash -c "${g} -p x"`,
    `timeout 60 ${c} exec "hi"`, `nice -n 5 ${m} exec "x"`, `sudo -u me ${c} exec "x"`, `time ${g} --prompt "x"`,
    `echo x | xargs ${c} exec`, '`' + `${c} exec "x"` + '`', `"${c}" exec "x"`, `${c} e "x"`, `${c} -m luna exec "x"`,
    `${g} -m grok-4.7 -p "x"`, 'agy -p "x"', 'kimi -p "x"', 'qwen -p "x"', 'opencode run "x"', `/usr/local/bin/${c} exec "x"`,
    `${c} exec "what does -h do"`,
  ]) {
    const res: any = await $.tool.call({ tool: 'Bash', command } as any)
    expect([command, String(res.deny ?? res.text)]).toEqual([command, expect.stringContaining('stage_start')])
  }
})

test('housekeeping commands and heredoc text are not blocked', async ($, on) => {
  let ran = 0
  on('tool.call', { tool: 'Bash' }, () => { ran += 1; return { result: { stdout: '', stderr: '', interrupted: false } } as any })
  const cmds = ['codex login', 'codex debug models', 'grok models', 'agy models', 'opencode models', 'kimi --version',
    'muse --help', `cat > probe.sh <<'EOF'\ncodex exec "hi"\nnpx @openai/codex exec x\nEOF`, 'ls ~/.codex']
  for (const command of cmds) await $.tool.call({ tool: 'Bash', command } as any)
  expect(ran).toBe(cmds.length)
})

test("the bridge's token file and port are not used directly from Bash or Read", async ($, on) => {
  let ran = 0
  on('tool.call', { tool: 'Bash' }, () => { ran += 1; return { result: { stdout: '', stderr: '', interrupted: false } } as any })
  on('tool.call', { tool: 'Read' }, () => { ran += 1; return { result: { type: 'text', file: { content: '' } } } as any })
  for (const command of ['cat ~/.modstage/token', 'curl -s http://127.0.0.1:47321/runs', 'curl localhost:47321/health -H "X-ModStage-Session: k"']) {
    const res: any = await $.tool.call({ tool: 'Bash', command } as any)
    expect(String(res.deny ?? res.text)).toContain('stage_*')
  }
  const read: any = await $.tool.call({ tool: 'Read', file_path: '/home/test/.modstage/token' } as any)
  expect(String(read.deny ?? read.text)).toContain('stage_*')
  expect(ran).toBe(0)
})
