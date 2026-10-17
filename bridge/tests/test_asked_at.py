import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("MODSTAGE_HOME", tempfile.mkdtemp())
os.environ["MODSTAGE_SLM_MESH"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modstage.run import Run  # noqa: E402

SPEC = {"id": "fake", "name": "Fake", "protocol": "acp", "command": ["true"]}


class AskedAtTest(unittest.TestCase):
    """The mod refuses a chat decision unless the user spoke after the approval was raised, so every
    pending approval must carry the time the bridge raised it."""

    def test_pending_approval_carries_the_time_it_was_raised(self):
        run = Run(SPEC, "task", tempfile.mkdtemp(), None, None)
        before = time.time()
        run.request_approval("command", "run `curl x`", "network", lambda choice: None)
        after = time.time()
        item = run.summary()["pending"][0] if hasattr(run, "summary") else list(run.pending.values())[0]
        self.assertTrue(before <= item["asked_at"] <= after)
        run.decide(item["id"], "deny")

    def test_each_approval_has_its_own_time(self):
        run = Run(SPEC, "task", tempfile.mkdtemp(), None, None)
        run.request_approval("command", "first", "", lambda c: None)
        time.sleep(0.01)
        run.request_approval("command", "second", "", lambda c: None)
        first, second = sorted(run.pending.values(), key=lambda i: i["asked_at"])
        self.assertLess(first["asked_at"], second["asked_at"])
        for aid in list(run.pending):
            run.decide(aid, "deny")


if __name__ == "__main__":
    unittest.main()
