import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modstage import registry  # noqa: E402


CODEX_LIST = json.dumps({"models": [
    {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "default_reasoning_level": "low",
     "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}, {"effort": "xhigh"}, {"effort": "max"}, {"effort": "ultra"}]},
    {"slug": "no-levels", "display_name": "Plain"}]})

OPENCODE_VERBOSE = (
    'opencode/claude-fable-5\n{"id": "claude-fable-5", "variants": {"low": {}, "medium": {}, "high": {}}}\n'
    'opencode/big-pickle\n{"id": "big-pickle", "variants": {}}\n')


class CatalogTest(unittest.TestCase):
    def test_codex_models_keep_the_levels_they_support(self):
        models, _ = registry.parse_models("codex_json", CODEX_LIST)
        sol = next(m for m in models if m["id"] == "gpt-6.1-sol")
        self.assertEqual(sol["efforts"], ["low", "medium", "high", "xhigh", "max", "ultra"])
        self.assertEqual(sol["default_effort"], "low")
        self.assertNotIn("efforts", next(m for m in models if m["id"] == "no-levels"))

    def test_muse_models_keep_their_variants_as_levels(self):
        rows = {"models": [{"modelId": "muse-spark-1.3", "displayLabel": "spark", "isDefault": True,
                            "variants": ["minimal", "low", "medium", "high", "xhigh", "max"], "defaultReasoningEffort": "high"}]}
        models, _ = registry.muse_catalog(rows)
        self.assertEqual(models[0]["efforts"][-1], "max")
        self.assertEqual(models[0]["default_effort"], "high")

    def test_opencode_models_are_listed_but_offer_no_effort_it_cannot_apply(self):
        # `opencode acp` advertises only `model` and `mode` (live, 18 Oct 2026), so its `variants` are not offered
        models, _ = registry.parse_models("opencode_verbose", OPENCODE_VERBOSE)
        self.assertEqual([m["id"] for m in models], ["opencode/claude-fable-5", "opencode/big-pickle"])
        self.assertTrue(all("efforts" not in m for m in models))


class StartTest(unittest.TestCase):
    def test_grok_gets_its_flag_next_to_the_model_flag(self):
        spec = registry.load()["grok"]
        self.assertEqual(registry.argv(spec, "grok-4.7", "low"), ["grok", "agent", "-m", "grok-4.7", "--effort", "low", "stdio"])
        self.assertEqual(registry.argv(spec, None, "low"), ["grok", "agent", "--effort", "low", "stdio"])
        self.assertEqual(registry.argv(spec, "grok-4.7"), ["grok", "agent", "-m", "grok-4.7", "stdio"])

    def test_an_agent_with_no_effort_flag_is_unchanged(self):
        self.assertEqual(registry.argv(registry.load()["muse"], "m", "high"), ["muse", "serve", "--model", "m"])


class CheckTest(unittest.TestCase):
    def setUp(self):
        registry._models["codex"] = {"models": registry.parse_models("codex_json", CODEX_LIST)[0], "default_model": "gpt-6.1-sol", "fetched_at": 9e12}
        self.addCleanup(registry._models.pop, "codex", None)

    def test_a_listed_level_passes_and_an_unlisted_one_says_what_is_offered(self):
        registry.check_effort("codex", "gpt-6.1-sol", "ultra")
        registry.check_effort("codex", None, "high")      # the default model's levels
        registry.check_effort("codex", "gpt-6.1-sol", "")  # none asked for
        with self.assertRaises(ValueError) as e:
            registry.check_effort("codex", "gpt-6.1-sol", "turbo")
        self.assertIn("low, medium, high, xhigh, max, ultra", str(e.exception))

    def test_a_model_with_no_levels_is_refused_instead_of_ignored(self):
        with self.assertRaises(ValueError) as e:
            registry.check_effort("codex", "no-levels", "high")
        self.assertIn("no thinking-effort setting", str(e.exception))

    def test_antigravity_points_at_its_model_names(self):
        with self.assertRaises(ValueError) as e:
            registry.check_effort("antigravity", None, "high")
        self.assertIn("High, Medium or Low model", str(e.exception))


class DefaultTest(unittest.TestCase):
    def test_each_clis_own_config_names_its_default_effort(self):
        home = Path(tempfile.mkdtemp())
        (home / ".codex").mkdir()
        (home / ".codex" / "config.toml").write_text('model = "gpt-6.1-sol"\nmodel_reasoning_effort = "medium"\n')
        (home / ".grok").mkdir()
        (home / ".grok" / "config.toml").write_text('[models]\ndefault_reasoning_effort = "high"\n')
        (home / ".config" / "muse").mkdir(parents=True)
        (home / ".config" / "muse" / "settings.json").write_text(json.dumps({"model_reasoning_efforts": {"muse-spark-1.3": "low"}}))
        with mock.patch.object(Path, "home", return_value=home):
            self.assertEqual(registry.configured_effort("codex"), "medium")
            self.assertEqual(registry.configured_effort("grok"), "high")
            self.assertEqual(registry.configured_effort("muse", "muse-spark-1.3"), "low")
            self.assertEqual(registry.configured_effort("muse", "other"), "")


if __name__ == "__main__":
    unittest.main()
