"""The parity contract: one check per (agent, control), run against protocol fakes.

Every cell of docs/PARITY-MATRIX.md comes from here. A cell is one of:
  works     the check passes
  degraded  the check passes, but the CLI only allows a weaker form; `why` says what
  gap       a known defect: the check is an expected failure until it is fixed, so fixing it
            turns the cell into an "unexpected success" and the suite fails until the table says works
  n/a       the CLI offers no such channel; the check asserts ModStage says so honestly

Regenerate the matrix with:  python3 bridge/tests/parity_matrix.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

from fakes import BRIDGE_AGENTS, Harness, make_run
from modstage import registry, server

NATIVE_STEER = {"codex", "muse"}
QUEUE_STEER = {"grok", "antigravity", "kimi", "qwen", "opencode"}

CONTROLS = ["start", "model", "stream", "long_turn", "approval", "steer", "queued", "interrupt", "resume", "close", "images"]
TITLES = {
    "start": "1 Start", "model": "1b Pick a model", "stream": "2 Stream text + tools", "long_turn": "2b Long turn looks alive",
    "approval": "3 Approval round trip", "steer": "4 Steer mid-turn", "queued": "4b Queued-message feedback",
    "interrupt": "5 Interrupt", "resume": "6 Resume after exit", "close": "7 Close", "images": "8 Images",
}


# ---- checks: each takes (t: TestCase, agent) and builds its own harness ----

def _with(agent, body, **kw):
    h = Harness(agent, **kw)
    try:
        return body(h)
    finally:
        h.stop()


def check_start(t, agent):
    def body(h):
        h.started()
        t.assertEqual(h.run.status, "running")
        if h.protocol == "codex-app-server":
            t.assertEqual(h.rpc.methods()[:3], ["initialize", "thread/start", "turn/start"])
        elif h.protocol == "muse-msp":
            t.assertEqual(h.rpc.methods()[:3], ["initialize", "session/start", "turn/start"])
        elif h.protocol == "acp":
            t.assertEqual(h.rpc.methods()[:2], ["initialize", "session/new"])
            t.assertEqual(len(h.held), 1, "the first prompt was not sent")
        else:
            sent = h.proc.lines()
            t.assertEqual(sent[0]["event"], "user")
            t.assertIn("say hi", sent[0]["message"]["content"])
    _with(agent, body)


def check_model(t, agent):
    def body(h):
        h.started()
        if h.protocol == "codex-app-server":
            params = dict(h.rpc.calls)["thread/start"]
            t.assertEqual(params.get("model"), "m-pick")
        else:
            sent_by_rpc = [p for m, p in (h.rpc.calls if h.rpc else [])
                           if m in ("session/set_model", "session/set_config_option")]
            t.assertTrue("m-pick" in h.argv_used() or any("m-pick" in (p.get("modelId"), p.get("value")) for p in sent_by_rpc),
                         f"model not passed: argv {h.argv_used()}")
    _with(agent, body, model="m-pick")


def check_stream(t, agent):
    def body(h):
        h.started()
        h.tool("ls -la")
        h.say("hello there")
        t.assertIn("hello", h.run.partial or h.run.final_text, "partial text not streamed")
        h.end_turn()
        kinds = h.kinds()
        t.assertIn("tool", kinds)
        t.assertIn("message", kinds)
        t.assertEqual(h.run.final_text, "hello there")
        t.assertEqual(h.run.status, "idle")
    _with(agent, body)


def check_long_turn(t, agent):
    """A report with no text (thinking, a step) must show the turn is alive: fresh activity, not the last tool."""
    def body(h):
        h.started()
        h.tool("pytest")
        h.run.last_activity -= 120  # two quiet minutes
        before = h.run.last_activity
        h.think("checking the diff")
        t.assertGreater(h.run.last_activity, before, "a thinking report did not count as activity")
        t.assertNotIn("pytest", h.run.activity, f"activity still shows the finished tool: {h.run.activity!r}")
    _with(agent, body)


def check_approval(t, agent):
    def body(h):
        h.started()
        h.ask("pip install x")
        if h.protocol == "stream-json":
            # no prompt channel: the denial must be visible and the run must not look like a clean finish
            t.assertIn("cannot ask", h.run.approval_note)
            t.assertIn("denied", h.kinds(), "the CLI's auto-denial was not shown")
            t.assertNotEqual(h.run.activity, "idle", "a blocked turn looks like a clean finish")
            return
        pending = list(h.run.pending.values())
        t.assertEqual(len(pending), 1, "the request did not reach the Needs-you inbox")
        t.assertIn("pip install x", pending[0]["title"])
        t.assertTrue(h.run.decide(pending[0]["id"], "allow"))
        got = h.answered()
        if h.protocol == "codex-app-server":
            t.assertEqual(got, {"decision": "accept"})
        elif h.protocol == "acp":
            t.assertEqual(got, {"outcome": {"outcome": "selected", "optionId": "o-once"}})
        else:
            t.assertEqual(got["choiceId"], "c-ok")
    _with(agent, body)


def check_steer(t, agent):
    def body(h):
        h.started()
        note = h.adapter.send("also add a test")
        if agent in NATIVE_STEER:
            t.assertIn("turn/steer", h.rpc.methods())
            t.assertIn("steered", note)
        else:
            t.assertIn("queued", note)
    _with(agent, body)


def check_queued(t, agent):
    """A message sent mid-turn shows as '1 queued'; 'Interrupt and send now' ends the turn so it runs."""
    def body(h):
        h.started()
        h.adapter.send("also add a test")
        t.assertEqual(h.run.summary().get("queued"), 1, "the panel cannot show '1 queued'")
        with mock.patch.object(server, "_boot", lambda run: None):
            note = server.send_now(h.run)
        if h.protocol == "acp":
            t.assertIn("session/cancel", [m for m, _ in h.rpc.notes])
            h.end_turn()  # the cancelled turn returns
            t.assertEqual(h.run.summary().get("queued"), 0)
        else:
            t.assertIn("restarted", note)
            t.assertIn("also add a test", h.run.prompt)
            t.assertEqual(h.run.summary().get("queued"), 0)
    _with(agent, body)


def check_interrupt(t, agent):
    def body(h):
        h.started()
        h.adapter.interrupt()
        if h.protocol in ("codex-app-server", "muse-msp"):
            t.assertIn("turn/interrupt", h.rpc.methods())
        elif h.protocol == "acp":
            t.assertIn("session/cancel", [m for m, _ in h.rpc.notes])
        else:
            t.assertIsNotNone(h.proc.poll(), "the process was not stopped")
            t.assertEqual(h.run.status, "interrupted")
    _with(agent, body)


def check_resume(t, agent):
    """After the agent process ends, a message restarts it with a recap (server.revive)."""
    def body(h):
        h.started()
        h.say("first answer")
        h.end_turn()
        h.exit(0)
        t.assertTrue(server._ended(h.run), "a dead process was not detected")
        with mock.patch.object(server, "_boot", lambda run: None):
            note = server.revive(h.run, "carry on")
        t.assertIn("restarted", note)
        t.assertIn("first answer", h.run.prompt)
    _with(agent, body)


def check_close(t, agent):
    def body(h):
        h.started()
        h.adapter.close()
        t.assertIsNotNone(h.proc.poll(), "close left the process running")
    _with(agent, body)


def _image() -> dict:
    img = Path(tempfile.mkdtemp()) / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
    return server.images_from({"images": [str(img)]})[0]


def check_images(t, agent):
    """An image reaches the CLI in its own protocol shape, or is refused with a reason: never dropped."""
    def body(h):
        h.started()
        h.end_turn()
        pic = _image()
        if agent in NO_IMAGE_INPUT:
            with t.assertRaises(ValueError) as caught:
                h.adapter.send("what is in this?", images=[pic])
            t.assertIn("image", str(caught.exception))
            return
        h.adapter.send("what is in this?", images=[pic])
        if h.protocol == "codex-app-server":
            inputs = [p for m, p in h.rpc.calls if m == "turn/start"][-1]["input"]
            t.assertIn({"type": "localImage", "path": pic["path"]}, inputs)
        elif h.protocol == "muse-msp":
            inputs = [p for m, p in h.rpc.calls if m == "turn/start"][-1]["input"]
            t.assertTrue(any(i["type"] == "image" and i["mediaType"] == "image/png" and i["base64Data"] for i in inputs))
        else:
            h.end_turn()
            blocks = [p for m, p in h.rpc.calls if m == "session/prompt"][-1]["prompt"]
            t.assertTrue(any(b["type"] == "image" and b["mimeType"] == "image/png" and b["data"] for b in blocks))
    _with(agent, body)


NO_IMAGE_INPUT = {"grok", "antigravity"}


CHECKS = {c: globals()[f"check_{c}"] for c in CONTROLS}

# ---- the table: what each cell is today, and why ----

DEGRADED = {
    **{(a, "steer"): "CLI has no mid-turn input; the message queues until the turn ends" for a in QUEUE_STEER},
    ("grok", "approval"): "the round trip works, but Grok's own config (permission_mode = always-approve) means it "
                          "never asks; the launcher says so before Start",
    ("opencode", "model"): "`opencode acp` has no model flag: ModStage sets ACP's `model` config option after "
                           "session/new (verified live: session/set_config_option switched it)",
    ("antigravity", "long_turn"): "agy streams no thinking text, only step events: the panel shows 'thinking' and "
                                  "stays fresh, but cannot show what it is thinking",
    ("antigravity", "queued"): "'Interrupt and send now' restarts agy (it has no cancel) with a recap plus the queued message",
    ("antigravity", "interrupt"): "agy has no cancel: ModStage stops the process; the next message restarts it with a recap",
    **{(a, "resume"): "restarts a fresh process with a recap of the run, not the CLI's own session resume" for a in BRIDGE_AGENTS},
}
NA = {
    ("antigravity", "approval"): "headless agy cannot ask (it refuses and reports denied_actions); ModStage shows each "
                                 "refusal, marks the run blocked, and says so before Start",
    **{(a, "queued"): "steers natively; nothing queues" for a in NATIVE_STEER},
    ("grok", "images"): "Grok's ACP initialize says promptCapabilities.image = false: ModStage refuses with that reason",
    ("antigravity", "images"): "agy's print mode takes text only (no verified image input): ModStage refuses with a reason",
}
# n/a cells whose check asserts the honest label (the rest have nothing to run)
NA_CHECKED = {("antigravity", "approval"), ("grok", "images"), ("antigravity", "images")}

GAPS = {
}


def cell(agent: str, control: str) -> tuple[str, str]:
    key = (agent, control)
    if key in NA:
        return "n/a", NA[key]
    if key in GAPS:
        return "gap", GAPS[key]
    if key in DEGRADED:
        return "degraded", DEGRADED[key]
    return "works", ""


# ---- rows checked once for every agent (bridge and mod level) ----

SHARED = {
    "needs_you_visible": ("Needs-you card in view on a new approval; band jumps to it", "works",
                          "A: tests/panel.test.tsx (the scroll itself is not run by the test kit: see Notes)"),
    "decide_from_claude": ("Answer an approval from Claude chat (stage_decide)", "works", "B: tests/decide.test.ts"),
    "session_scope": ("Each Claude session sees and answers only the runs it started; the board stays per folder", "works",
                      "bridge/tests/test_session_scope.py, tests/decide.test.ts"),
    "free_text_refused": ("Free text refused while an approval is pending (bridge 409 + message box)", "works",
                          "C3: bridge/tests/conformance.py, tests/panel.test.tsx"),
    "waiting_on_user": ("stage_wait says waiting_on_user; until=turn_end keeps waiting while the user decides", "works", "C5"),
    "empty_turn_flagged": ("A turn where the CLI reports nothing is flagged, not shown as a clean finish (ACP agents)", "works",
                           "seen live: Kimi on a model its provider no longer serves"),
    "model_flag_ignored": ("A model the CLI's flag ignores (Kimi ACP) is set through ACP, and the panel names the real model",
                           "works", "seen live: kimi -m X acp started on its default model"),
    "cancel_error_is_not_a_failure": ("'Interrupt and send now' survives an agent that answers a cancel with an error (Kimi)",
                                      "works", "seen live on Kimi 16 Oct: session/prompt Internal error after cancel"),
    "claude_board_peer": ("Claude is a peer on the board: reads it, posts, claims; agents' messages reach it without starting a turn",
                          "works", "Phase 3 P1: bridge/tests/test_claude_peer.py, tests/board-peer.test.ts"),
    "claude_edits_respect_claims": ("Claude's own Edit/Write is stopped on a file an agent holds (fails open without a bridge)",
                                    "works", "Phase 3 P1: tests/board-peer.test.ts"),
    "grok_honest_label": ("Grok's auto-approve config is shown before Start", "works", ""),
}


def shared_empty_turn_flagged(t):
    """An ACP turn that reports nothing at all (a CLI failing on its model) is flagged, not shown as a clean finish."""
    h = Harness("kimi")
    try:
        h.started()
        h.end_turn()
        t.assertIn("warning", h.kinds())
        t.assertIn("empty turn", h.run.activity)
    finally:
        h.stop()


def shared_model_flag_ignored(t):
    """Kimi ignores `-m` in ACP mode and starts on its default: ModStage must set the model through ACP."""
    from fakes import FakeRpc
    saved = dict(FakeRpc.replies)
    try:
        h = Harness("kimi", model="glm51")
        FakeRpc.replies = {**saved, "session/new": {"sessionId": "k1", "models": {"currentModelId": "stale-default",
                                                     "availableModels": [{"modelId": "stale-default"}, {"modelId": "glm51"}]}}}
        h.started()
        sets = [p for m, p in h.rpc.calls if m == "session/set_model"]
        t.assertEqual(sets, [{"sessionId": "k1", "modelId": "glm51"}])
        t.assertEqual(h.run.model, "glm51")
    finally:
        FakeRpc.replies = saved
        h.stop()


def shared_cancel_error_is_not_a_failure(t):
    """Kimi answers a cancelled prompt with an error: after a cancel that is the cancelled turn, and the
    queued message still runs instead of the run being marked failed."""
    from fakes import FakeRpc
    h = Harness("kimi")
    try:
        h.started()
        h.adapter.send("queued one")
        h.adapter.interrupt()
        saved = dict(FakeRpc.replies)
        def boom(p):
            raise RuntimeError("session/prompt: Internal error")
        FakeRpc.replies = {**saved, "session/prompt": boom}
        h.end_turn()  # the cancelled prompt comes back as an error
        FakeRpc.replies = saved
        t.assertNotEqual(h.run.status, "error")
        t.assertEqual(h.run.status, "running")  # the queued prompt is next
        h.end_turn()
        t.assertNotEqual(h.run.status, "error")
    finally:
        h.stop()


def shared_free_text_refused(t):
    run = make_run("codex")
    run.request_approval("command", "run `pip install x`", "", lambda c: None)
    refusal = server.send_refusal(run)
    t.assertIn("Answer the approval", refusal)


def shared_waiting_on_user(t):
    run = make_run("codex")
    run.set(status="running", activity="thinking")
    run.request_approval("command", "run `pip install x`", "", lambda c: None)
    t.assertTrue(run.wait(0.1))
    t.assertTrue(run.detail(0).get("waiting_on_user"))


def shared_grok_honest_label(t):
    home = tempfile.mkdtemp()
    Path(home, "config.toml").write_text('permission_mode = "always-approve"\n')
    with mock.patch.dict(os.environ, {"GROK_HOME": home}):
        note = registry._approval_note(registry.load()["grok"])
    t.assertIn("auto-approves", note)


SHARED_CHECKS = {k: globals()[f"shared_{k}"] for k in SHARED if f"shared_{k}" in globals()}
