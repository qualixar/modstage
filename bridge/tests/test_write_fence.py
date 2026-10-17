"""Write-time fencing: a stale writer is rejected at the write, not just at claim or approval time.

The scenario a developer proposed on X: pause A, let its lease expire, let B edit the file, resume A.
A's stale write must be rejected even though A was allowed to edit earlier. Run: python3 -m unittest discover bridge/tests
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import REPLIES, FakeRpc, spec  # noqa: E402
from modstage import acp, codex, server  # noqa: E402
from modstage.board import board_for  # noqa: E402
from modstage.claims import BOARD  # noqa: E402
from modstage.run import RUNS, Run  # noqa: E402


def expire(board, run_id: str) -> None:
    """Let a run's leases lapse, as they do when it sits idle past its ttl."""
    board._x("UPDATE claims SET expires_at=? WHERE holder=? AND released_at IS NULL", (time.time() - 1, run_id))


class Folder(unittest.TestCase):
    """Two runs of one engine in one folder, each with its adapter on a fake transport."""

    agent = "codex"

    def setUp(self):
        RUNS.clear()
        FakeRpc.replies = REPLIES
        module = {"codex": codex, "grok": acp}[self.agent]
        patch = mock.patch.object(module, "StdioRpc", FakeRpc)
        patch.start()
        self.addCleanup(patch.stop)
        self.cwd = tempfile.mkdtemp()
        self.target = Path(self.cwd) / "app.py"
        self.target.write_text("original\n")
        self.a = self.make("ask")
        self.b = self.make("ask")
        self.board = board_for(self.cwd)

    def make(self, autonomy: str):
        run = Run(spec(self.agent), "task", self.cwd, None, None, autonomy)
        RUNS[run.id] = run
        cls = codex.CodexAdapter if self.agent == "codex" else acp.AcpAdapter
        run.adapter = cls(run)
        run.set(status="running")
        BOARD.register(run)
        return run

    def tearDown(self):
        RUNS.clear()


class CodexWriteFence(Folder):
    def patch_request(self, run, rid: int, item_id: str, path: str = "app.py") -> None:
        run.adapter._notify({"method": "item/started", "params": {"item": {
            "type": "fileChange", "id": item_id, "changes": [{"path": path}]}}})
        run.adapter._request({"id": rid, "method": "item/fileChange/requestApproval",
                              "params": {"itemId": item_id, "threadId": "t", "turnId": "u", "startedAtMs": 1}})

    def decision(self, run) -> str:
        return run.adapter.rpc.answers[-1][1]["decision"]

    def test_stale_codex_write_is_rejected_even_after_allow_session(self):
        # A holds app.py (fence 1) and the user allows its edit "for this run"
        self.assertEqual(self.board.claim(self.a.id, ["app.py"])["granted"][0]["fence"], 1)
        self.patch_request(self.a, 1, "i1")
        self.a.decide(next(iter(self.a.pending)), "allow_session")
        self.assertEqual(self.decision(self.a), "accept", "allow-for-run is not honoured for edits: each one is re-checked")
        self.assertTrue(self.board.check_write(self.a.id, "app.py")["ok"])

        # A is paused; its lease expires; B takes the file (fence 2) and edits it
        self.a.set(status="idle")
        expire(self.board, self.a.id)
        got = self.board.claim(self.b.id, ["app.py"])["granted"][0]
        self.assertEqual(got["fence"], 2)
        self.target.write_text("B was here\n")

        # A resumes with the permission it was given earlier and asks to write; the user says yes again
        self.a.set(status="running")
        self.patch_request(self.a, 2, "i2")
        self.a.decide(next(iter(self.a.pending)), "allow")

        self.assertEqual(self.decision(self.a), "decline", "the stale write is refused at the write")
        self.assertEqual(self.target.read_text(), "B was here\n")
        self.assertTrue(any(e["kind"] == "conflict" and "write blocked" in e["text"] for e in self.a.events))
        self.assertTrue(any(e["kind"] == "conflict" and "was blocked" in e["text"] for e in self.b.events))

    def test_autonomous_codex_run_is_fenced_too(self):
        # no live holder, so nothing reaches the person and the auto run is answered at once: the fence still says no
        auto = self.make("auto")
        self.board.claim(auto.id, ["app.py"])
        expire(self.board, auto.id)
        self.board.claim(self.b.id, ["app.py"])
        self.board.release(self.b.id, "app.py")
        self.patch_request(auto, 1, "i1")
        self.assertEqual(self.decision(auto), "decline")
        self.assertFalse(auto.pending)

    def test_conflict_with_a_live_holder_goes_to_the_person_and_the_fence_still_wins(self):
        auto = self.make("auto")
        self.board.claim(self.b.id, ["app.py"])
        self.patch_request(auto, 1, "i1")
        self.assertTrue(auto.pending, "an action on a held file always comes to a person, even for auto runs")
        auto.decide(next(iter(auto.pending)), "allow_session")
        self.assertEqual(self.decision(auto), "decline")

    def test_fresh_path_is_allowed_and_claimed(self):
        self.patch_request(self.a, 1, "i1", "new.py")
        self.a.decide(next(iter(self.a.pending)), "allow")
        self.assertEqual(self.decision(self.a), "accept")
        held = [c for c in self.board.read()["claims"] if c["path"] == "new.py"]
        self.assertEqual((held[0]["holder"], held[0]["fence"]), (self.a.id, 1))

    def test_auto_runs_ask_codex_to_send_every_edit_through_the_bridge(self):
        for autonomy, policy in (("auto", "untrusted"), ("ask", "on-request")):
            run = self.make(autonomy)
            run.adapter.start()
            params = next(p for m, p in run.adapter.rpc.calls if m == "thread/start")
            self.assertEqual(params["approvalPolicy"], policy)

    def test_legacy_apply_patch_is_fenced(self):
        self.board.claim(self.b.id, ["app.py"])
        self.a.adapter._request({"id": 5, "method": "applyPatchApproval", "params": {"fileChanges": {"app.py": {}}}})
        self.a.decide(next(iter(self.a.pending)), "allow")
        self.assertEqual(self.decision(self.a), "denied")


class AcpWriteFence(Folder):
    agent = "grok"

    def write(self, run, rid: int, path: str, content: str):
        run.adapter._request({"id": rid, "method": "fs/write_text_file",
                              "params": {"sessionId": "s", "path": path, "content": content}})
        return run.adapter.rpc.answers[-1]

    def test_stale_acp_write_is_rejected_and_file_keeps_b_content(self):
        path = str(self.target)
        self.assertEqual(self.board.claim(self.a.id, ["app.py"])["granted"][0]["fence"], 1)
        self.assertIsNone(self.write(self.a, 1, path, "A first\n")[2], "A's own current lease may write")

        self.a.set(status="idle")  # paused
        expire(self.board, self.a.id)
        self.assertEqual(self.board.claim(self.b.id, ["app.py"])["granted"][0]["fence"], 2)
        self.assertIsNone(self.write(self.b, 2, path, "B was here\n")[2])

        self.a.set(status="running")  # A resumes and writes
        _, result, error = self.write(self.a, 3, path, "A stale\n")
        self.assertIsNone(result)
        self.assertIn("rejected by the ModStage board", error)
        self.assertEqual(self.target.read_text(), "B was here\n")
        self.assertTrue(any(e["kind"] == "conflict" and "write blocked" in e["text"] for e in self.a.events))
        self.assertTrue(any(e["kind"] == "conflict" and "was blocked" in e["text"] for e in self.b.events))

    def test_fresh_path_is_allowed_and_claimed(self):
        fresh = str(Path(self.cwd) / "sub" / "new.py")
        self.assertIsNone(self.write(self.a, 1, fresh, "hello\n")[2])
        self.assertEqual(Path(fresh).read_text(), "hello\n")
        held = [c for c in self.board.read()["claims"] if c["path"] == "sub/new.py"]
        self.assertEqual((held[0]["holder"], held[0]["fence"]), (self.a.id, 1))

    def test_same_holder_keeps_its_fence(self):
        path = str(self.target)
        self.board.claim(self.a.id, ["app.py"])
        self.write(self.a, 1, path, "one\n")
        self.write(self.a, 2, path, "two\n")
        self.assertEqual(self.target.read_text(), "two\n")
        self.assertEqual([c["fence"] for c in self.board.read()["claims"] if c["path"] == "app.py"], [1])

    def test_paths_stay_inside_the_run_folder(self):
        outside = Path(tempfile.mkdtemp()) / "x.txt"
        self.assertIn("outside", self.write(self.a, 1, str(outside), "no")[2])
        self.assertFalse(outside.exists())
        link = Path(self.cwd) / "link"
        link.symlink_to(outside.parent)
        self.assertIn("outside", self.write(self.a, 2, str(link / "x.txt"), "no")[2])
        self.assertFalse(outside.exists())
        self.assertIn("outside", self.write(self.a, 3, "relative.txt", "no")[2])

    def test_read_text_file_is_served_inside_the_folder_only(self):
        self.target.write_text("l1\nl2\nl3\n")
        self.a.adapter._request({"id": 1, "method": "fs/read_text_file",
                                 "params": {"sessionId": "s", "path": str(self.target), "line": 2, "limit": 1}})
        self.assertEqual(self.a.adapter.rpc.answers[-1][1], {"content": "l2\n"})
        self.a.adapter._request({"id": 2, "method": "fs/read_text_file", "params": {"path": "/etc/hosts"}})
        self.assertIn("outside", self.a.adapter.rpc.answers[-1][2])

    def test_acp_advertises_file_access_to_the_agent(self):
        self.a.adapter.start()
        init = next(p for m, p in self.a.adapter.rpc.calls if m == "initialize")
        self.assertEqual(init["clientCapabilities"]["fs"], {"readTextFile": True, "writeTextFile": True})


class BoardWriteRules(unittest.TestCase):
    def setUp(self):
        self.cwd = tempfile.mkdtemp()
        self.b = board_for(self.cwd)
        self.b.join("A", "codex", "a")
        self.b.join("B", "grok", "b")

    def test_overtaken_run_is_rejected_even_when_the_new_holder_released(self):
        self.b.claim("A", ["f.py"])
        expire(self.b, "A")
        self.b.claim("B", ["f.py"])
        self.b.release("B", "f.py")
        res = self.b.check_write("A", "f.py")
        self.assertFalse(res["ok"])
        self.assertIn("claim the file again", res["reason"])
        self.assertTrue(self.b.claim("A", ["f.py"])["granted"])  # an explicit re-claim refreshes it (fence 3)
        self.assertEqual(self.b.check_write("A", "f.py")["fence"], 3)

    def test_expired_lease_nobody_took_is_reclaimed_with_a_new_fence(self):
        self.b.claim("A", ["f.py"])
        expire(self.b, "A")
        res = self.b.check_write("A", "f.py")
        self.assertEqual((res["ok"], res["fence"]), (True, 2))

    def test_glob_claim_covers_files_under_it(self):
        self.b.claim("A", ["src/**"])
        self.assertTrue(self.b.check_write("A", "src/deep/x.py")["ok"])
        self.assertFalse(self.b.check_write("B", "src/deep/x.py")["ok"])


class LeasesAreNotRenewedForIdleRuns(unittest.TestCase):
    def test_only_working_runs_are_renewed(self):
        RUNS.clear()
        cwd = tempfile.mkdtemp()
        runs = {}
        for name, status in (("working", "running"), ("idle", "idle"), ("paused", "interrupted")):
            run = Run(spec("codex"), "t", cwd, None, None)
            RUNS[run.id] = run
            run.status = status
            BOARD.register(run)
            board_for(cwd).claim(run.id, [f"{name}.py"], ttl_s=60)
            runs[name] = run
        before = {c["path"]: c["expires_at"] for c in board_for(cwd).read()["claims"]}
        time.sleep(0.05)
        server._renew_working()
        after = {c["path"]: c["expires_at"] for c in board_for(cwd).read()["claims"]}
        self.assertGreater(after["working.py"], before["working.py"])
        self.assertEqual(after["idle.py"], before["idle.py"])
        self.assertEqual(after["paused.py"], before["paused.py"])
        RUNS.clear()


if __name__ == "__main__":
    unittest.main()
