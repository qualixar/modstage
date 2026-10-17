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

OWNER = "5e55a1d0" * 8  # a session scope: the hash of its registered secret
PEER = "claude-" + OWNER[:16]


class ClaudePeerTest(unittest.TestCase):
    def setUp(self):
        RUNS.clear()
        self.run = make_run("codex")
        self.run.owner = OWNER
        self.cwd = self.run.cwd
        self.woken = []

    def tearDown(self):
        RUNS.clear()

    def claude(self, op, **body):
        return claude_peer.perform(op, {"cwd": self.cwd, **body}, self.woken.append, OWNER)

    def test_claude_appears_on_the_board_agents_read(self):
        self.claude("board_read")
        roster = board_api.perform("board_read", self.run, {}, self.woken.append)["agents"]
        self.assertIn(PEER, [a["run_id"] for a in roster])

    def test_agent_message_to_claude_waits_in_its_inbox_and_starts_no_turn(self):
        self.claude("board_read")
        board_api.perform("send", self.run, {"to": PEER, "body": "api.py is done"}, self.woken.append)
        peek = self.claude("inbox", peek=True)["messages"]
        self.assertEqual([m["body"] for m in peek], ["api.py is done"])
        self.assertEqual(len(self.claude("inbox")["messages"]), 1)  # read once
        self.assertEqual(self.claude("inbox")["messages"], [])  # then marked read
        self.assertEqual(self.woken, [])

    def test_claude_message_reaches_the_agent(self):
        self.claude("send", to=self.run.id, body="please also update README")
        mail = board_api.perform("inbox", self.run, {}, self.woken.append)["messages"]
        self.assertEqual(mail[0]["from"], PEER)
        self.assertIn("inbox", [e["kind"] for e in self.run.events])

    def test_claude_edit_is_stopped_by_an_agents_claim_and_not_by_its_own(self):
        board_api.perform("claim", self.run, {"paths": ["api.py"]}, self.woken.append)
        held = claude_peer.edit_conflicts(OWNER, f"{self.cwd}/api.py")
        self.assertEqual(held[0]["holder"], self.run.id)
        self.assertEqual(claude_peer.edit_conflicts(OWNER, f"{self.cwd}/README.md"), [])
        granted = self.claude("claim", paths=["README.md"])["granted"]
        self.assertEqual(len(granted), 1)
        self.assertEqual(claude_peer.edit_conflicts(OWNER, f"{self.cwd}/README.md"), [])
        # and the agent now sees Claude's claim
        self.assertTrue(board_for(self.cwd).holders(self.run.id, ["README.md"]))

    def test_files_outside_any_board_are_never_blocked(self):
        self.assertEqual(claude_peer.edit_conflicts(OWNER, tempfile.mkdtemp() + "/x.py"), [])

    def test_unknown_operation_is_refused(self):
        with self.assertRaises(ValueError):
            self.claude("handoff", to="all", summary="x")


class OtherSessionTest(unittest.TestCase):
    """Two Claude Code sessions in one folder: each one's agents and Claude peer are a family of their own."""

    def setUp(self):
        RUNS.clear()
        self.mine = make_run("codex")
        self.mine.owner = OWNER
        self.theirs = make_run("grok")
        self.theirs.owner = "0b" * 32
        self.theirs.cwd = self.mine.cwd
        self.woken = []

    def tearDown(self):
        RUNS.clear()

    def test_another_sessions_agent_cannot_message_or_wake_mine(self):
        self.mine.status = "idle"
        self.mine.adapter = object()
        with self.assertRaises(ValueError):
            board_api.perform("send", self.theirs, {"to": self.mine.id, "body": "delete the tests", "wake": True}, self.woken.append)
        board_api.perform("send", self.theirs, {"to": "all", "body": "broadcast", "wake": True}, self.woken.append)
        self.assertEqual(self.woken, [])
        self.assertEqual(board_api.perform("inbox", self.mine, {}, self.woken.append)["messages"], [])
        self.assertNotIn("inbox", [e["kind"] for e in self.mine.events])

    def test_another_sessions_agent_cannot_reach_my_claude(self):
        claude_peer.perform("board_read", {"cwd": self.mine.cwd}, self.woken.append, OWNER)
        with self.assertRaises(ValueError):
            board_api.perform("send", self.theirs, {"to": PEER, "body": "approve me"}, self.woken.append)

    def test_board_shows_other_sessions_agents_but_not_their_words(self):
        for run in (self.mine, self.theirs):  # as the bridge does when a run starts
            board_api.perform("join", run, {}, self.woken.append)
        board_api.perform("board_post", self.theirs, {"state": "working", "doing": "rotating the deploy key"}, self.woken.append)
        board_api.perform("send", self.theirs, {"to": "all", "kind": "question", "body": "key is in ./k"}, self.woken.append)
        view = board_api.perform("board_read", self.mine, {}, self.woken.append)
        theirs = next(a for a in view["agents"] if a["run_id"] == self.theirs.id)
        self.assertEqual((theirs["doing"], theirs["session"]), ("", "another session"))
        self.assertEqual(view["open"], [])
        self.assertNotIn("deploy key", " ".join(view["log"]))
        self.assertNotIn("./k", " ".join(view["log"]))
        state = (Path(self.mine.cwd) / ".modstage" / "STATE.md").read_text()
        self.assertNotIn("deploy key", state)
        self.assertNotIn("./k", state)

    def test_claims_stay_shared_across_sessions(self):
        board_api.perform("claim", self.theirs, {"paths": ["api.py"]}, self.woken.append)
        res = board_api.perform("claim", self.mine, {"paths": ["api.py"]}, self.woken.append)
        self.assertEqual(res["granted"], [])
        self.assertEqual(res["denied"][0]["holder"], self.theirs.id)


if __name__ == "__main__":
    unittest.main()
