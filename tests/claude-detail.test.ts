import { expect, test } from 'claude-code/testing'
import { claudeEditDetail, claudeToolDetail, describe } from '../hooks/claude-agents.ts'

// Claude subagents' tabs showed the tool's name and the last line of its result. They now carry what the
// subagent ran in full and what its edits changed, like the other agents' rows.

test('a command is shown whole, and its other arguments are listed', () => {
  const cmd = 'grep -rn ' + 'x'.repeat(400)
  expect(describe('Bash', { command: cmd })).toContain(cmd)          // was cut at 140
  expect(claudeToolDetail('Bash', { command: cmd })).toBe('')         // the row already says it all
  expect(claudeToolDetail('Bash', { command: 'ls', timeout: 5000 })).toContain('timeout: 5000')
})

test('Edit, MultiEdit and Write inputs become a diff on the edit row', () => {
  const edit = claudeEditDetail('Edit', { file_path: 'a.py', old_string: 'x = 1', new_string: 'x = 2\ny = 3' })
  expect(edit).toContain('--- a/a.py')
  expect(edit).toContain('-x = 1')
  expect(edit).toContain('+y = 3')
  const multi = claudeEditDetail('MultiEdit', { file_path: 'b.py', edits: [{ old_string: 'a', new_string: 'b' }, { old_string: 'c', new_string: 'd' }] })
  expect(multi).toContain('-c')
  expect(multi).toContain('+d')
  expect(claudeEditDetail('Write', { file_path: 'n.py', content: 'print(1)' })).toContain('+print(1)')
  expect(claudeEditDetail('Bash', { command: 'ls' })).toBe('')
  expect(claudeEditDetail('Write', { file_path: 'big', content: 'z\n'.repeat(5000) }).length).toBeLessThan(4000)
})
