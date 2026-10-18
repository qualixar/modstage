"""Every agent has its own colour, and the bridge's registry and the panel's palette (hooks/ui/palette.ts) agree."""
import re
import unittest
from pathlib import Path

from modstage import registry

PALETTE = Path(__file__).resolve().parents[2] / "hooks" / "ui" / "palette.ts"


def _rgb(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


class PaletteTests(unittest.TestCase):
    def test_no_two_builtin_agents_share_a_colour(self):
        colours = {a["id"]: a["color"] for a in registry.BUILTIN}
        self.assertEqual(len(set(colours.values())), len(colours), colours)
        ids = sorted(colours)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                ra, rb = _rgb(colours[a]), _rgb(colours[b])
                dist = sum((x - y) ** 2 for x, y in zip(ra, rb)) ** 0.5
                self.assertGreater(dist, 55, f"{a} and {b} look alike: {colours[a]} {colours[b]}")

    @unittest.skipUnless(PALETTE.exists(), "panel sources are not next to the bridge")
    def test_registry_matches_the_panel_palette(self):
        text = PALETTE.read_text()
        panel = dict(re.findall(r"^\s*(\w+): '(#[0-9A-Fa-f]{6})'", text.split("export const ENGINE")[1].split("}")[0], re.M))
        for a in registry.BUILTIN:
            self.assertEqual(panel.get(a["id"], "").lower(), a["color"].lower(), a["id"])


if __name__ == "__main__":
    unittest.main()
