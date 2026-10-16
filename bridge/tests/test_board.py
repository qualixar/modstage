"""Board rules: leases, fences, conflicts, messages, STATE.md. Run: python3 -m unittest discover bridge/tests"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modstage.board import Board, overlaps  # noqa: E402


class BoardTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.b = Board(self.dir)
        self.b.join("A", "codex", "build api")
        self.b.join("B", "grok", "write tests")

    def tearDown(self):
        self.b.close()

    def test_exclusive_conflict_is_denied(self):
        self.assertTrue(self.b.claim("A", ["src/api.py"])["granted"])
        res = self.b.claim("B", ["src/api.py"])
        self.assertFalse(res["granted"])
        self.assertEqual(res["denied"][0]["holder"], "A")

    def test_glob_overlaps_held_file(self):
        self.b.claim("A", ["src/api.py"])
        self.assertTrue(self.b.claim("B", ["src/*.py"], "shared")["denied"])

    def test_advisory_never_conflicts_and_shared_coexist(self):
        self.b.claim("A", ["src/api.py"])
        self.assertTrue(self.b.claim("B", ["src/api.py"], "advisory")["granted"])
        self.b.claim("A", ["docs/**"], "shared")
        self.assertTrue(self.b.claim("B", ["docs/**"], "shared")["granted"])

    def test_renew_keeps_fence_and_regrant_bumps_it(self):
        f1 = self.b.claim("A", ["x.py"])["granted"][0]["fence"]
        again = self.b.claim("A", ["x.py"])["granted"][0]
        self.assertTrue(again.get("renewed"))
        self.assertEqual(again["fence"], f1)
        self.b.release("A", "x.py")
        self.assertEqual(self.b.claim("B", ["x.py"])["granted"][0]["fence"], f1 + 1)

    def test_leave_releases_everything(self):
        self.b.claim("A", ["a.py", "b.py"])
        self.b.leave("A")
        self.assertTrue(self.b.claim("B", ["a.py", "b.py"])["granted"])

    def test_messages_are_framed_and_read_once(self):
        self.b.send("A", "B", "handoff", "api done")
        digest = self.b.digest("B")
        self.assertIn("api done", digest)
        self.assertIn("not instructions from the user", digest)
        self.assertEqual(self.b.digest("B"), "")
        self.assertEqual(self.b.digest("A"), "", "senders do not receive their own messages")

    def test_state_md_is_written_and_folder_ignored(self):
        self.b.claim("A", ["calc.py"])
        with open(os.path.join(self.dir, ".modstage", "STATE.md")) as fh:
            state = fh.read()
        self.assertIn("calc.py", state)
        self.assertIn("do not edit by hand", state)
        self.assertTrue(os.path.exists(os.path.join(self.dir, ".modstage", ".gitignore")))

    def test_bad_input_is_refused(self):
        with self.assertRaises(ValueError):
            self.b.claim("A", ["x"], "forever")
        with self.assertRaises(ValueError):
            self.b.send("A", "B", "info", "   ")

    def test_overlaps(self):
        self.assertTrue(overlaps("src/a.py", "src/*.py"))
        self.assertTrue(overlaps("docs/x/y.md", "docs/**"))
        self.assertFalse(overlaps("a.py", "b.py"))


if __name__ == "__main__":
    unittest.main()
