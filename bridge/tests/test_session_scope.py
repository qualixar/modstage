"""Runs belong to the Claude Code session that started them; only that session sees and answers them."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import make_run  # noqa: E402
from modstage import server  # noqa: E402
from modstage.run import RUNS  # noqa: E402


class SessionScopeTest(unittest.TestCase):
    def setUp(self):
        RUNS.clear()
        self.a = make_run("codex")
        self.a.owner = "sess-A"
        self.b = make_run("grok")
        self.b.owner = "sess-B"
        self.answers = []
        self.a.request_approval("command", "run `pip install x`", "", self.answers.append)

    def tearDown(self):
        RUNS.clear()

    def test_each_session_sees_only_its_runs(self):
        self.assertEqual([r.id for r in server.mine("sess-A")], [self.a.id])
        self.assertEqual([r.id for r in server.mine("sess-B")], [self.b.id])
        self.assertEqual(len(server.mine(None)), 2)  # in-process callers only; HTTP always has a scope

    def test_another_session_cannot_answer(self):
        aid = next(iter(self.a.pending))
        code, body = server.decide(self.a, {"approval_id": aid, "choice": "allow"}, "sess-B")
        self.assertEqual(code, 403)
        self.assertEqual(self.answers, [])
        self.assertIn(aid, self.a.pending)

    def test_owner_answers_and_the_feed_says_who(self):
        aid = next(iter(self.a.pending))
        code, _ = server.decide(self.a, {"approval_id": aid, "choice": "allow", "by": "claude"}, "sess-A")
        self.assertEqual(code, 200)
        self.assertEqual(self.answers, ["allow"])
        last = self.a.events[-1]
        self.assertEqual(last["kind"], "approval")
        self.assertIn("decided by the user in Claude chat", last["detail"])

    def test_bad_choice_is_refused_not_read_as_deny(self):
        aid = next(iter(self.a.pending))
        code, body = server.decide(self.a, {"approval_id": aid, "choice": "yes"}, "sess-A")
        self.assertEqual(code, 400)
        self.assertIn(aid, self.a.pending)

    def test_decide_cancels_the_auto_deny_clock(self):
        aid = next(iter(self.a.pending))
        timer = self.a._timers[aid]
        server.decide(self.a, {"approval_id": aid, "choice": "deny"}, "sess-A")
        self.assertTrue(timer.finished.is_set())

    def test_an_approval_needs_the_owning_session_named(self):
        aid = next(iter(self.a.pending))
        code, _ = server.decide(self.a, {"approval_id": aid, "choice": "allow"}, "")  # a scope that owns nothing
        self.assertEqual(code, 403)
        self.assertEqual(self.answers, [])

    def test_message_while_waiting_is_refused(self):
        self.assertIn("Answer the approval above first", server.send_refusal(self.a))
        self.assertEqual(server.send_refusal(self.b), "")


class CapabilityTest(unittest.TestCase):
    """Ownership is a secret the session holds, not its id: registering a known session id again gives a
    new, empty scope, and an ownerless run belongs to no scope."""

    def setUp(self):
        RUNS.clear()
        server.SESSIONS.clear()

    def tearDown(self):
        RUNS.clear()
        server.SESSIONS.clear()

    def test_registering_the_same_session_id_gives_a_different_scope(self):
        a1 = server.owner_of(server.register_session("sess-A"))
        a2 = server.owner_of(server.register_session("sess-A"))
        self.assertNotEqual(a1, a2)
        run = make_run("codex")
        run.owner = a1
        self.assertEqual([r.id for r in server.mine(a1)], [run.id])
        self.assertEqual(server.mine(a2), [])
        self.assertTrue(server._not_yours(run, a2))

    def test_an_empty_session_cannot_register(self):
        with self.assertRaises(ValueError):
            server.register_session("")

    def test_an_ownerless_run_belongs_to_no_scope(self):
        loose = make_run("muse")
        loose.owner = ""
        scope = server.owner_of(server.register_session("sess-A"))
        self.assertEqual(server.mine(scope), [])
        self.assertTrue(server._not_yours(loose, scope))
        loose.request_approval("command", "run x", "", lambda c: None)
        aid = next(iter(loose.pending))
        self.assertEqual(server.decide(loose, {"approval_id": aid, "choice": "allow"}, scope)[0], 403)

    def test_summaries_do_not_carry_the_owner(self):
        run = make_run("codex")
        run.owner = "x" * 64
        self.assertNotIn("x" * 64, str(run.summary()))


if __name__ == "__main__":
    unittest.main()
