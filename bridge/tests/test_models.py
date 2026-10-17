import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modstage.registry import parse_models  # noqa: E402


class ParseModelsTest(unittest.TestCase):
    def test_codex_json(self):
        out = json.dumps({"models": [{"slug": "gpt-6.1-sol", "display_name": "GPT-6.1-Sol"}, {"slug": "gpt-6-luna"}]})
        models, default = parse_models("codex_json", out)
        self.assertEqual([m["id"] for m in models], ["gpt-6.1-sol", "gpt-6-luna"])
        self.assertEqual(models[0]["label"], "GPT-6.1-Sol")
        self.assertEqual(default, "")

    def test_grok_bullets_mark_default(self):
        out = "You are logged in.\n\nAvailable models:\n  * grok-4.7 (default)\n  - grok-4.6\n"
        models, default = parse_models("bullets", out)
        self.assertEqual([m["id"] for m in models], ["grok-4.7", "grok-4.6"])
        self.assertEqual(default, "grok-4.7")

    def test_agy_tabbed_skips_banner(self):
        out = "Fetching available models...\ngemini-3.8-flash-high\tGemini 3.8 Flash (High)\n"
        models, _ = parse_models("tabbed", out)
        self.assertEqual(models, [{"id": "gemini-3.8-flash-high", "label": "Gemini 3.8 Flash (High)"}])

    def test_muse_model_list_marks_default(self):
        from modstage.registry import muse_catalog
        result = {"models": [{"modelId": "muse-wonder-1.0", "displayLabel": "Muse Wonder", "isDefault": False},
                             {"modelId": "muse-spark-1.3-contributor", "isDefault": True}],
                  "source": "providerCatalog", "providerId": "meta", "profileId": None}
        models, default = muse_catalog(result)
        self.assertEqual([m["id"] for m in models], ["muse-wonder-1.0", "muse-spark-1.3-contributor"])
        self.assertEqual(models[0]["label"], "Muse Wonder")
        self.assertEqual(default, "muse-spark-1.3-contributor")

    def test_kimi_models_come_from_its_config_aliases(self):
        from modstage.registry import kimi_catalog
        text = 'default_model = "stale-default"\n[models.free-router]\nmodel = "provider/free-router"\n' \
               '[models.stale-default]\nmodel = "provider/stale-default"\n'
        models, default = kimi_catalog(text)
        self.assertEqual([m["id"] for m in models], ["free-router", "stale-default"])
        self.assertEqual(models[0]["label"], "free-router (provider/free-router)")
        self.assertEqual(default, "stale-default")

    def test_opencode_offers_a_model_choice(self):
        from modstage import registry
        report = {a["id"]: a for a in registry.doctor()["agents"]}
        self.assertTrue(report["opencode"]["takes_model"])

    def test_parsed_list_is_whole(self):
        models, _ = parse_models("lines", "\n".join(f"p/m{i}" for i in range(40)))
        self.assertEqual(len(models), 40)  # the listing shown is capped (test_model_refresh), the check is not


if __name__ == "__main__":
    unittest.main()
