"""One version everywhere: the plugin manifest and what the bridge tells each agent it is."""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bridge"))

from modstage import __version__  # noqa: E402


class VersionTest(unittest.TestCase):
    def test_manifest_and_bridge_agree(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["version"], __version__)

    def test_no_hardcoded_versions_left_in_the_bridge(self):
        for path in (ROOT / "bridge" / "modstage").glob("*.py"):
            self.assertIsNone(re.search(r'"version": "\d+\.\d+\.\d+"', path.read_text()), path.name)

    def test_changelog_names_this_version(self):
        self.assertIn(f"## {__version__}", (ROOT / "CHANGELOG.md").read_text())


if __name__ == "__main__":
    unittest.main()
