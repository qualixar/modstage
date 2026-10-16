"""Phase 3 P1: Claude Code as a peer on a folder's board."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import make_run  # noqa: E402
from modstage import board_api, claude_peer  # noqa: E402
from modstage.board import board_for  # noqa: E402
from modstage.run import RUNS  # noqa: E402

SESSION = "5e55a1d0-0000-4000-8000-00000000c1a0"


class ClaudePeerTest(unittest.TestCase):
    def setUp(self):
        RUNS.clear()
        self.run = make_run("codex")
        self.cwd = self.run.cwd
        self.woken = []

    def tearDown(self):
        RUNS.clear()

    def claude(self, op, **body):
        return claude_peer.perform(op, {"session": SESSION, "cwd": self.cwd, **body}, self.woken.append)

    def test_claude_appears_on_the_board_agents_read(self):
        self.claude("board_read")
        roster = board_api.perform("board_read", self.run, {}, self.woken.append)["agents"]
        self.assertIn("claude-5e55a1d0", [a["run_id"] for a in roster])

    def test_agent_message_to_claude_waits_in_its_inbox_and_starts_no_turn(self):
        self.claude("board_read")
        board_api.perform("send", self.run, {"to": "claude-5e55a1d0", "body": "api.py is done"}, self.woken.append)
        peek = self.claude("inbox", peek=True)["messages"]
        self.assertEqual([m["body"] for m in peek], ["api.py is done"])
        self.assertEqual(len(self.claude("inbox")["messages"]), 1)  # read once
        self.assertEqual(self.claude("inbox")["messages"], [])  # then marked read
        self.assertEqual(self.woken, [])

    def test_claude_message_reaches_the_agent(self):
        self.claude("send", to=self.run.id, body="please also update README")
        mail = board_api.perform("inbox", self.run, {}, self.woken.append)["messages"]
        self.assertEqual(mail[0]["from"], "claude-5e55a1d0")
        self.assertIn("inbox", [e["kind"] for e in self.run.events])

    def test_claude_edit_is_stopped_by_an_agents_claim_and_not_by_its_own(self):
        board_api.perform("claim", self.run, {"paths": ["api.py"]}, self.woken.append)
        held = claude_peer.edit_conflicts(SESSION, f"{self.cwd}/api.py")
        self.assertEqual(held[0]["holder"], self.run.id)
        self.assertEqual(claude_peer.edit_conflicts(SESSION, f"{self.cwd}/README.md"), [])
        granted = self.claude("claim", paths=["README.md"])["granted"]
        self.assertEqual(len(granted), 1)
        self.assertEqual(claude_peer.edit_conflicts(SESSION, f"{self.cwd}/README.md"), [])
        # and the agent now sees Claude's claim
        self.assertTrue(board_for(self.cwd).holders(self.run.id, ["README.md"]))

    def test_files_outside_any_board_are_never_blocked(self):
        self.assertEqual(claude_peer.edit_conflicts(SESSION, tempfile.mkdtemp() + "/x.py"), [])

    def test_unknown_operation_is_refused(self):
        with self.assertRaises(ValueError):
            self.claude("handoff", to="all", summary="x")


if __name__ == "__main__":
    unittest.main()
