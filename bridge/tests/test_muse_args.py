import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modstage.muse import _stage_tools  # noqa: E402


class FakeRun:
    id = "abcd1234"
    board_token = "secret-run-token"


class MuseArgsTest(unittest.TestCase):
    def test_tools_go_in_as_one_host_setting_with_env_references(self):
        flag, value = _stage_tools(FakeRun())
        self.assertEqual(flag, "-c")
        key, _, raw = value.partition("=")
        self.assertEqual(key, "mcpServers.modstage")
        entry = json.loads(raw)
        self.assertEqual(entry["mode"], "optional")
        self.assertEqual(entry["args"][0], "-c")  # the safe launcher (no module shadowing from the repo)
        self.assertEqual(entry["args"][-1], "modstage.mcp_stdio")
        # Muse refuses literal env values; each must be a whole ${VAR} reference.
        for name, ref in entry["env"].items():
            self.assertEqual(ref, "${" + name + "}")
        # The run token itself never appears on the command line.
        self.assertNotIn("secret-run-token", value)


if __name__ == "__main__":
    unittest.main()
