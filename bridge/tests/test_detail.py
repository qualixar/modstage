import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import Harness  # noqa: E402
from modstage.detail import args_detail, diff_blocks, edit_detail, unified  # noqa: E402

LONG = "line of output\n" * 400  # about 6000 characters


def events(h, kind):
    return [e for e in h.run.events if e["kind"] == kind]


class HelperTest(unittest.TestCase):
    def test_a_replacement_edit_becomes_a_unified_diff(self):
        d = edit_detail({"path": "a.py", "old_str": "x=1\ny=2", "new_str": "x=1\ny=3"})
        self.assertIn("-y=2", d)
        self.assertIn("+y=3", d)
        self.assertIn("--- a/a.py", d)

    def test_a_write_shows_the_new_text_as_added_lines(self):
        d = edit_detail('{"file_path": "n.py", "content": "print(1)\\nprint(2)"}')
        self.assertIn("+print(1)", d)
        self.assertIn("+print(2)", d)

    def test_acp_diff_blocks_become_one_diff_and_other_blocks_are_ignored(self):
        content = [{"type": "content", "content": {"type": "text", "text": "ok"}},
                   {"type": "diff", "path": "a.py", "oldText": "a\n", "newText": "b\n"}]
        d = diff_blocks(content)
        self.assertIn("-a", d)
        self.assertIn("+b", d)
        self.assertEqual(diff_blocks([{"type": "content"}]), "")

    def test_arguments_are_listed_in_full_unless_the_summary_already_says_it(self):
        self.assertEqual(args_detail({"command": "ls -la"}, "ls -la"), "")
        both = args_detail({"command": "ls", "cwd": "/x"}, "ls")
        self.assertIn("command: ls", both)
        self.assertIn("cwd: /x", both)

    def test_everything_stays_under_the_runs_event_cap(self):
        self.assertLess(len(edit_detail({"path": "p", "content": LONG * 3})), 4000)
        self.assertLess(len(unified("p", None, LONG * 3)), 40000)


class CodexDetailTest(unittest.TestCase):
    def test_edit_carries_each_files_diff_and_a_command_its_full_output(self):
        h = Harness("codex")
        self.addCleanup(h.stop)
        h.adapter._item({"type": "fileChange", "id": "f1", "changes": [
            {"path": "a.py", "kind": "update", "diff": "@@ -1 +1 @@\n-old\n+new"},
            {"path": "b.py", "kind": "add", "diff": "+hello"}]}, done=True)
        edit = events(h, "edit")[0]
        self.assertEqual(edit["text"], "edited a.py, b.py")
        self.assertIn("+new", edit["detail"])
        self.assertIn("+hello", edit["detail"])
        h.adapter._item({"type": "commandExecution", "command": "pytest", "exitCode": 1, "aggregatedOutput": LONG}, done=True)
        out = events(h, "result")[0]["detail"]
        self.assertGreater(len(out), 3000)   # was cut at 1500
        self.assertLessEqual(len(out), 4000)

    def test_mcp_and_dynamic_tool_results_are_recorded(self):
        h = Harness("codex")
        self.addCleanup(h.stop)
        h.adapter._item({"type": "mcpToolCall", "server": "docs", "tool": "search", "status": "completed",
                         "result": {"content": [{"type": "text", "text": "found 3 pages"}]}}, done=True)
        h.adapter._item({"type": "dynamicToolCall", "tool": "lookup", "success": True,
                         "contentItems": [{"type": "inputText", "text": "answer 42"}]}, done=True)
        details = [e["detail"] for e in events(h, "result")]
        self.assertIn("found 3 pages", details[0])
        self.assertIn("answer 42", details[1])
        h.adapter._item({"type": "mcpToolCall", "server": "docs", "tool": "search", "status": "failed",
                         "error": {"message": "401 unauthorized"}}, done=True)
        self.assertIn("401 unauthorized", events(h, "result")[-1]["detail"])


class MuseDetailTest(unittest.TestCase):
    def test_command_edit_and_result_are_in_full(self):
        h = Harness("muse")
        self.addCleanup(h.stop)
        cmd = "grep -rn " + "x" * 400
        h.adapter._item({"kind": "toolCall", "tool": "run_command", "args": {"command": cmd, "cwd": "/w"}}, done=False)
        tool = events(h, "tool")[0]
        self.assertIn(cmd, tool["text"])            # was cut at 160
        self.assertIn("cwd: /w", tool["detail"])    # the rest of the input
        h.adapter._item({"kind": "toolCall", "tool": "str_replace", "toolStatus": "ok", "output": LONG,
                         "args": {"path": "a.py", "old_str": "one", "new_str": "two"}}, done=True)
        self.assertIn("+two", events(h, "edit")[0]["detail"])
        self.assertGreater(len(events(h, "result")[0]["detail"]), 3000)


class AcpDetailTest(unittest.TestCase):
    def test_diffs_from_the_result_or_the_call_reach_the_edit_row(self):
        for agent in ("grok", "kimi", "qwen", "opencode"):
            h = Harness(agent)
            self.addCleanup(h.stop)
            n = h.adapter._notify
            n({"method": "session/update", "params": {"update": {
                "sessionUpdate": "tool_call", "toolCallId": "t1", "title": "Edit a.py", "kind": "edit",
                "rawInput": {"path": "a.py", "mode": "replace"}}}})
            n({"method": "session/update", "params": {"update": {
                "sessionUpdate": "tool_call_update", "toolCallId": "t1", "status": "completed", "kind": "edit",
                "locations": [{"path": "a.py"}],
                "content": [{"type": "diff", "path": "a.py", "oldText": "a\n", "newText": "b\n"}]}}})
            edit = events(h, "edit")[0]
            self.assertIn("+b", edit["detail"], agent)
            self.assertIn("mode: replace", events(h, "tool")[0]["detail"], agent)

    def test_a_diff_sent_with_the_call_is_kept_until_the_result(self):
        h = Harness("kimi")
        self.addCleanup(h.stop)
        n = h.adapter._notify
        n({"method": "session/update", "params": {"update": {
            "sessionUpdate": "tool_call", "toolCallId": "t2", "title": "Write n.py", "kind": "edit", "rawInput": {"path": "n.py"},
            "content": [{"type": "diff", "path": "n.py", "oldText": None, "newText": "print(1)"}]}}})
        n({"method": "session/update", "params": {"update": {
            "sessionUpdate": "tool_call_update", "toolCallId": "t2", "status": "completed", "kind": "edit"}}})
        self.assertIn("+print(1)", events(h, "edit")[0]["detail"])


class AntigravityDetailTest(unittest.TestCase):
    def test_edit_shows_what_changed_and_a_result_is_not_cut_at_1500(self):
        h = Harness("antigravity")
        self.addCleanup(h.stop)
        step = lambda state, **extra: {"event": "step_update", "step_update": {"step_type": "tool", "state": state, "tool_info": {
            "name": "replace_file_content", "parameters": {"TargetFile": "a.py", "TargetContent": "one", "ReplacementContent": "two"}, **extra}}}
        h.adapter._event(step("ACTIVE"))
        h.adapter._event(step("DONE", output=LONG))
        self.assertIn("+two", events(h, "edit")[0]["detail"])
        self.assertGreater(len(events(h, "result")[0]["detail"]), 3000)
        self.assertIn("TargetContent: one", events(h, "tool")[0]["detail"])


if __name__ == "__main__":
    unittest.main()
