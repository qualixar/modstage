import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("MODSTAGE_HOME", tempfile.mkdtemp())
os.environ["MODSTAGE_SLM_MESH"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modstage import server  # noqa: E402
from modstage.run import RUNS, Run  # noqa: E402

SPEC = {"id": "fake", "name": "Fake", "protocol": "acp", "command": ["true"]}


class FakeAdapter:
    def __init__(self, run):
        self.run, self.started, self.closed, self.sent = run, False, False, []

    def start(self):
        self.started = True
        self.run.set(status="idle", activity="idle")

    def send(self, text):
        self.sent.append(text)
        return "sent"

    def close(self):
        self.closed = True


class ReviveAndCloseTest(unittest.TestCase):
    def setUp(self):
        self.cwd = tempfile.mkdtemp()
        self.run = Run(SPEC, "first task", self.cwd, None, None)
        RUNS[self.run.id] = self.run
        self.run.add("you", "first task")
        self.run.add("message", "did the first task")

    def tearDown(self):
        RUNS.pop(self.run.id, None)

    def test_message_to_ended_run_restarts_with_recap(self):
        old = FakeAdapter(self.run)
        self.run.adapter = old
        self.run.set(status="done", activity="closed")
        made = []
        with mock.patch.object(server, "_adapter", side_effect=lambda r: made.append(FakeAdapter(r)) or made[-1]), \
             mock.patch.object(server.threading, "Thread", side_effect=lambda target, daemon: mock.Mock(start=target)):
            note = server.revive(self.run, "now do the second")
        self.assertIn("restarted", note)
        self.assertTrue(old.closed)
        self.assertEqual(len(made), 1)
        self.assertIs(self.run.adapter, made[0])
        self.assertTrue(made[0].started)
        self.assertIn("did the first task", self.run.prompt)
        self.assertIn("now do the second", self.run.prompt)

    def test_close_forgets_run_and_tolerates_late_events(self):
        adapter = FakeAdapter(self.run)
        self.run.adapter = adapter
        self.run.set(status="idle", activity="idle")
        server.close_run(self.run)
        self.assertTrue(adapter.closed)
        self.assertNotIn(self.run.id, RUNS)
        self.assertIsNone(self.run.adapter)
        self.run.add("error", "late exit notice")  # must not raise on the closed log

    def test_ended_detects_exited_process(self):
        adapter = FakeAdapter(self.run)
        adapter.proc = mock.Mock(poll=lambda: 0)
        self.run.adapter = adapter
        self.run.set(status="interrupted", activity="interrupted")
        self.assertTrue(server._ended(self.run))


if __name__ == "__main__":
    unittest.main()
