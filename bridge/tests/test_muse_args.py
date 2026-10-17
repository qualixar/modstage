import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modstage.coordination import agent_env  # noqa: E402
from modstage.muse import _stage_tools  # noqa: E402


class FakeRun:
    id = "abcd1234"
    board_token = "secret-run-token"
    engine = "muse"


def _entry(run) -> dict:
    return json.loads(_stage_tools(run)[1].partition("=")[2])


class MuseArgsTest(unittest.TestCase):
    def test_tools_go_in_as_one_host_setting_with_env_references(self):
        flag, value = _stage_tools(FakeRun())
        self.assertEqual(flag, "-c")
        key, _, raw = value.partition("=")
        self.assertEqual(key, "mcpServers.modstage")
        entry = json.loads(raw)
        self.assertEqual(entry["mode"], "optional")
        self.assertIn("-c", entry["args"][:2])  # the safe launcher (no module shadowing from the repo), after -P
        self.assertEqual(entry["args"][-1], "modstage.mcp_stdio")
        # Muse refuses literal env values; each must be a whole ${VAR} reference.
        for name, ref in entry["env"].items():
            self.assertEqual(ref, "${" + name + "}")
        # The run token itself never appears on the command line.
        self.assertNotIn("secret-run-token", value)

    def test_every_reference_names_a_variable_muse_is_given(self):
        # Muse 1.4.10 refuses to start ("secret leaves need ... naming a set variable") when a ${VAR}
        # names something missing from its own environment; ModStage gives it agent_env only.
        given = agent_env(FakeRun())
        for name in _entry(FakeRun())["env"]:
            self.assertIn(name, given)

    def test_shadowing_protection_stays_without_env(self):
        args = _entry(FakeRun())["args"]
        if sys.version_info >= (3, 11):
            self.assertEqual(args[0], "-P")  # = PYTHONSAFEPATH, without an env entry
        self.assertIn("-c", args)

    @unittest.skipUnless(__import__("shutil").which("muse"), "muse not installed")
    def test_real_muse_accepts_the_setting(self):
        import os
        import subprocess
        out = subprocess.run(["muse", "serve", *_stage_tools(FakeRun())], input="", capture_output=True, text=True,
                             timeout=60, env={**os.environ, **agent_env(FakeRun())})
        self.assertNotIn("refusing run", out.stderr)
        self.assertEqual(out.returncode, 0, out.stderr[-300:])


if __name__ == "__main__":
    unittest.main()
