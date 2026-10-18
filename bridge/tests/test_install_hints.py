"""A missing agent CLI says how to install it, in the setup check and in the start error."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modstage import registry, server  # noqa: E402


class InstallHintTest(unittest.TestCase):
    def test_every_builtin_agent_has_an_install_line(self):
        for spec in registry.BUILTIN:
            self.assertTrue(spec.get("install"), spec["id"])

    def test_setup_check_carries_the_line_for_a_missing_cli(self):
        with mock.patch.object(registry.shutil, "which", return_value=None), mock.patch.object(registry, "refresh_models"):
            agents = {a["id"]: a for a in registry.doctor()["agents"]}
        self.assertFalse(agents["grok"]["installed"])
        self.assertIn("https://x.ai/cli/install.sh", agents["grok"]["install"])
        self.assertEqual(agents["qwen"]["install"], "npm install -g @qwen-code/qwen-code")

    def test_starting_a_missing_agent_names_the_install_step(self):
        with mock.patch.object(server.shutil, "which", return_value=None):
            with self.assertRaises(ValueError) as caught:
                server.start_run({"engine": "muse", "prompt": "hi"}, "owner")
        self.assertIn("Muse is not installed", str(caught.exception))
        self.assertIn("curl -fsSL https://dev.meta.ai/install.sh | bash", str(caught.exception))

    def test_a_user_defined_agent_without_a_line_still_gets_a_clear_sentence(self):
        text = registry.not_installed({"id": "x", "name": "X", "command": ["xcli"]})
        self.assertIn("`xcli` is on PATH", text)


if __name__ == "__main__":
    unittest.main()
