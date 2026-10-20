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


def _verbose(*ids):
    """`opencode models --verbose` output: each id, then a JSON line with its display name."""
    return "\n".join(f'{i}\n{json.dumps({"name": i.split("/", 1)[1].replace("-", " ").title()})}' for i in ids)


class OpenCodePickerTest(unittest.TestCase):
    """The panel's OpenCode picker: providers the user has, grouped, newest first, none pushed out by a cap."""

    def setUp(self):
        import os
        import tempfile
        from unittest import mock
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "data" / "opencode").mkdir(parents=True)
        (root / "config" / "opencode").mkdir(parents=True)
        # the credential values here must never be read, logged or returned: only the names matter
        (root / "data" / "opencode" / "auth.json").write_text(json.dumps(
            {"anthropic": {"type": "api", "key": "sk-test-NEVER-READ"}, "opencode": {"type": "api", "key": "sk-zen"}}))
        (root / "config" / "opencode" / "opencode.jsonc").write_text(
            '{\n  // default\n  "model": "anthropic/claude-haiku-5-5",\n'
            '  "provider": {"anthropic": {"options": {"baseURL": "https://api.anthropic.com/v1"},},},\n}\n')
        patcher = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "data"), "XDG_CONFIG_HOME": str(root / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.root = root

    def fake_listing(self):
        zen = [f"opencode/zen-model-{i}" for i in range(20)] + ["opencode/claude-sonnet-5-5"]
        anthropic = ["anthropic/claude-3-haiku", "anthropic/claude-opus-5-5", "anthropic/claude-fable-5-1",
                     "anthropic/claude-haiku-5-5", "anthropic/claude-sonnet-5-5", "anthropic/claude-sonnet-4-20250514"]
        noise = [f"openrouter/vendor/m{i}" for i in range(60)] + [f"omniroute/m{i}" for i in range(30)]
        return parse_models("opencode_verbose", _verbose(*zen, *anthropic, *noise))[0]

    def test_anthropic_survives_when_zen_is_listed_first(self):
        from modstage import registry
        shaped = registry.shape_opencode(self.fake_listing(), "anthropic/claude-haiku-5-5", registry.opencode_providers())
        shown = [m["id"] for m in registry.capped(shaped)]
        self.assertEqual(shown[0], "anthropic/claude-haiku-5-5")
        self.assertEqual(shown[:4], ["anthropic/claude-haiku-5-5", "anthropic/claude-opus-5-5",
                                     "anthropic/claude-sonnet-5-5", "anthropic/claude-fable-5-1"])
        self.assertLess(shown.index("anthropic/claude-fable-5-1"), shown.index("anthropic/claude-3-haiku"))

    def test_only_providers_the_user_has(self):
        from modstage import registry
        self.assertEqual(registry.opencode_providers(), {"anthropic", "opencode"})
        shaped = registry.shape_opencode(self.fake_listing(), "anthropic/claude-haiku-5-5", registry.opencode_providers())
        self.assertEqual({m["provider"] for m in shaped}, {"anthropic", "opencode"})  # no openrouter, no omniroute

    def test_cap_is_per_provider_and_the_check_still_knows_every_model(self):
        from modstage import registry
        shaped = registry.shape_opencode(self.fake_listing(), "anthropic/claude-haiku-5-5", registry.opencode_providers())
        shown = registry.capped(shaped)
        for name in ("anthropic", "opencode"):
            self.assertLessEqual(sum(1 for m in shown if m["provider"] == name), registry.PER_PROVIDER)
        self.assertIn("anthropic/claude-3-haiku", registry.known_ids(shaped))  # capped out of the panel, still accepted

    def test_ids_keep_their_provider_prefix_and_labels_name_the_route(self):
        from modstage import registry
        shaped = registry.shape_opencode(self.fake_listing(), "anthropic/claude-haiku-5-5", registry.opencode_providers())
        first = shaped[0]
        self.assertEqual(first["id"], "anthropic/claude-haiku-5-5")
        self.assertTrue(first["label"].endswith("anthropic"))

    def test_no_known_providers_means_no_filter(self):
        from modstage import registry
        listing = self.fake_listing()
        self.assertEqual(len(registry.shape_opencode(listing, "", set())), len(listing))

    def test_default_model_comes_from_jsonc_with_urls_and_trailing_commas(self):
        from modstage import registry
        self.assertEqual(registry._configured_default("opencode"), "anthropic/claude-haiku-5-5")

    def test_list_is_fetched_again_when_a_provider_is_added(self):
        import os
        import time
        from modstage import registry
        registry._store("opencode", self.fake_listing(), "")
        self.assertFalse(registry._stale("opencode"))
        auth = self.root / "data" / "opencode" / "auth.json"
        auth.write_text(json.dumps({"anthropic": {}, "opencode": {}, "xai": {}}))
        os.utime(auth, ns=(time.time_ns(), time.time_ns() + 5_000_000_000))
        self.assertTrue(registry._stale("opencode"))


class HermesAgentTest(unittest.TestCase):
    def test_hermes_runs_over_acp_and_takes_a_model(self):
        from modstage import registry
        spec = registry.load()["hermes"]
        self.assertEqual(registry.argv(spec, None), ["hermes", "acp"])
        self.assertEqual(spec["protocol"], "acp")
        self.assertIn("hermes-agent.nousresearch.com", registry.install_hint(spec))

    def test_default_model_and_approval_note_come_from_its_own_config(self):
        import os
        import tempfile
        from unittest import mock
        from modstage import registry
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / "config.yaml").write_text("model:\n  default: claude-sonnet-5  # chosen\n  provider: anthropic\n"
                                                    "approvals:\n  mode: 'off'\n")
            with mock.patch.dict(os.environ, {"HERMES_HOME": home}):
                self.assertEqual(registry._configured_default("hermes"), "claude-sonnet-5")
                self.assertIn("approvals are off", registry._approval_note(registry.load()["hermes"]))
                (Path(home) / "config.yaml").write_text("approvals:\n  mode: smart\n")
                self.assertEqual(registry._approval_note(registry.load()["hermes"]), "")


if __name__ == "__main__":
    unittest.main()
