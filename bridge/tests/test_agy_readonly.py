"""Antigravity ask runs are read-only, not dead ends (run 120c4f36, 17 Oct 2026).

Event shapes are the ones agy 1.4.0 emitted in the 17 Oct probes: tool steps named read_url_content,
search_web, view_file, write_to_file and run_command; result.denied_actions with action read_url,
read_file, write_file or command.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import Harness  # noqa: E402
from modstage import agy_project, registry  # noqa: E402


def tool(h, name, **params):
    for state in ("ACTIVE", "DONE"):
        h.adapter._event({"event": "step_update", "step_update": {
            "step_type": "tool", "state": state, "tool_info": {"name": name, "parameters": params}}})


def result(h, *denied):
    h.adapter._event({"event": "result", "result": {"status": "SUCCESS", "response": "",
                      "denied_actions": [{"action": a, "display_name": a.title()} for a in denied]}})


def project_files() -> list[Path]:
    return sorted(agy_project.projects_dir().glob("modstage-*.json"))


class AskRunProjectTest(unittest.TestCase):
    def setUp(self):
        self.h = Harness("antigravity")

    def tearDown(self):
        self.h.adapter.close()
        self.h.stop()

    def test_ask_run_passes_a_readonly_project(self):
        argv = self.h.argv_used()
        self.assertNotIn("--dangerously-skip-permissions", argv)
        self.assertIn("--project", argv)
        pid = argv[argv.index("--project") + 1]
        path = agy_project.projects_dir() / f"{pid}.json"
        data = json.loads(path.read_text())
        folder = os.path.realpath(self.h.run.cwd)
        self.assertEqual(data["id"], pid)
        self.assertEqual(data["projectResources"]["resources"], [{"folderUri": Path(folder).as_uri()}])
        rules = data["permissionGrants"]["permissionGrants"]
        self.assertEqual(rules["allow"], ["read_url(*)", f"read_file({folder})"])
        self.assertEqual(rules["ask"], [f"write_file({folder})", "command(*)"])

    def test_project_file_is_removed_when_the_run_closes(self):
        argv = self.h.argv_used()
        path = agy_project.projects_dir() / f"{argv[argv.index('--project') + 1]}.json"
        self.assertTrue(path.exists())
        self.h.adapter.close()
        self.assertFalse(path.exists())

    def test_reads_finish_cleanly_without_blocking(self):
        self.h.started()
        tool(self.h, "read_url_content", Url="https://example.com")
        tool(self.h, "search_web", query="example domain")
        tool(self.h, "view_file", AbsolutePath=os.path.join(self.h.run.cwd, "a.txt"))
        result(self.h)
        self.assertEqual(self.h.run.status, "idle")
        self.assertEqual(self.h.run.blocked, "")
        self.assertNotIn("denied", self.h.kinds())

    def test_refused_write_names_the_step_and_the_way_out(self):
        self.h.started()
        tool(self.h, "read_url_content", Url="https://example.com")
        tool(self.h, "write_to_file", TargetFile="/w/b.txt")
        result(self.h, "write_file")
        blocked = self.h.run.blocked
        self.assertIn("a file write: write_to_file /w/b.txt", blocked)
        self.assertIn('autonomy "auto"', blocked)
        self.assertIn("isolated folder", blocked)
        self.assertTrue(self.h.run.activity.startswith("blocked: refused a file write"))
        denied = [e for e in self.h.run.events if e["kind"] == "denied"]
        self.assertEqual(len(denied), 1)
        self.assertIn("write_to_file /w/b.txt", denied[0]["text"])
        self.assertIn("read-only", denied[0]["detail"])
        self.assertIn('autonomy "auto"', denied[0]["detail"])

    def test_each_refusal_is_listed_once_with_its_own_step(self):
        self.h.started()
        tool(self.h, "run_command", CommandLine="ls -la")
        tool(self.h, "view_file", AbsolutePath="/etc/hosts")
        tool(self.h, "run_command", CommandLine="echo hi")
        result(self.h, "command", "read_file", "command")
        texts = [e["text"] for e in self.h.run.events if e["kind"] == "denied"]
        self.assertEqual(texts, ["Antigravity refused a shell command: run_command echo hi",
                                 "Antigravity refused a file read outside its folder: view_file /etc/hosts"])

    def test_first_turn_tells_agy_it_is_read_only(self):
        self.h.started()
        first = self.h.proc.lines()[0]["message"]["content"]
        self.assertIn("read-only", first)
        self.assertIn("Shell commands, file writes and files outside this folder will be refused", first)

    def test_auto_run_gets_no_read_only_notice(self):
        h = Harness("antigravity", autonomy="auto")
        try:
            h.started()
            self.assertNotIn("read-only", h.proc.lines()[0]["message"]["content"])
        finally:
            h.adapter.close()
            h.stop()

    def test_cumulative_denials_report_only_this_turns(self):
        # agy repeats earlier refusals in every later result of the same process
        self.h.started()
        tool(self.h, "run_command", CommandLine="echo one")
        result(self.h, "command")
        self.h.adapter.send("write it instead")
        tool(self.h, "write_to_file", TargetFile="/w/b.txt")
        result(self.h, "command", "write_file")
        self.assertEqual(self.h.run.blocked.split(". agy")[0], "refused a file write: write_to_file /w/b.txt")
        texts = [e["text"] for e in self.h.run.events if e["kind"] == "denied"]
        self.assertEqual(texts, ["Antigravity refused a shell command: run_command echo one",
                                 "Antigravity refused a file write: write_to_file /w/b.txt"])

    def test_next_turn_clears_blocked_and_forgets_old_steps(self):
        self.h.started()
        tool(self.h, "run_command", CommandLine="echo hi")
        result(self.h, "command")
        self.assertTrue(self.h.run.blocked)
        self.h.adapter.send("only read this time")
        self.assertEqual(self.h.run.blocked, "")
        result(self.h, "command", "read_url")  # agy repeats turn 1's refusal
        self.assertIn("refused a web read", self.h.run.blocked)
        self.assertNotIn("echo hi", self.h.run.blocked)


class AutoRunTest(unittest.TestCase):
    def test_auto_run_skips_permissions_and_writes_no_project(self):
        before = project_files()
        h = Harness("antigravity", autonomy="auto")
        try:
            self.assertIn("--dangerously-skip-permissions", h.argv_used())
            self.assertNotIn("--project", h.argv_used())
            self.assertEqual(project_files(), before)
        finally:
            h.adapter.close()
            h.stop()


class ProjectModuleTest(unittest.TestCase):
    def test_remove_only_touches_modstage_files(self):
        base = agy_project.projects_dir()
        base.mkdir(parents=True, exist_ok=True)
        theirs = base / "08f3689d-user-project.json"
        theirs.write_text("{}")
        agy_project.remove("08f3689d-user-project")
        self.assertTrue(theirs.exists())
        theirs.unlink()

    def test_restarted_process_gets_its_own_file(self):
        cwd = tempfile.mkdtemp()
        a, b = agy_project.create("run1", cwd), agy_project.create("run1", cwd)
        self.assertNotEqual(a, b)
        agy_project.remove(a)
        self.assertTrue((agy_project.projects_dir() / f"{b}.json").exists())
        agy_project.remove(b)

    def test_stale_files_are_swept(self):
        base = agy_project.projects_dir()
        base.mkdir(parents=True, exist_ok=True)
        old = base / "modstage-dead00-abc123.json"
        old.write_text("{}")
        os.utime(old, (1, 1))
        pid = agy_project.create("run2", tempfile.mkdtemp())
        self.assertFalse(old.exists())
        agy_project.remove(pid)

    def test_unwritable_dir_warns_and_still_starts(self):
        blocker = Path(tempfile.mkdtemp()) / "file"
        blocker.write_text("")
        old = os.environ["MODSTAGE_AGY_PROJECTS"]
        os.environ["MODSTAGE_AGY_PROJECTS"] = str(blocker / "projects")
        try:
            h = Harness("antigravity")
            self.assertNotIn("--project", h.argv_used())
            self.assertIn("warning", h.kinds())
            h.adapter.close()
            h.stop()
        finally:
            os.environ["MODSTAGE_AGY_PROJECTS"] = old


class NoteTest(unittest.TestCase):
    def test_note_explains_readonly_ask_and_the_auto_restart(self):
        note = registry._approval_note(registry.load()["antigravity"])
        for words in ("cannot ask", "read-only", "read web pages", "refused", 'autonomy "auto"', "isolated folder"):
            self.assertIn(words, note)


if __name__ == "__main__":
    unittest.main()
