"""Model lists stay current: refreshed when old, on request (each Claude Code session start), and
re-asked once when a run names a model the cached list does not have."""
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modstage import registry  # noqa: E402

MUSE_ROWS = {"models": [
    {"modelId": "muse-wonder-1.0", "isDefault": False},
    {"modelId": "muse-wonder-1.0-contributor", "isDefault": True,
     "description": "Your content, including inter-session messages, may be used for product improvement."},
    {"modelId": "muse-spark-1.3"}, {"modelId": "muse-spark-1.3-contributor"},
    {"modelId": "muse-spark-1.2"}, {"modelId": "muse-spark-1.2-contributor"},
]}


class MuseGroupingTest(unittest.TestCase):
    def test_contributor_ids_fold_into_their_model(self):
        models, default = registry.muse_catalog(MUSE_ROWS)
        self.assertEqual([m["id"] for m in models], ["muse-wonder-1.0", "muse-spark-1.3", "muse-spark-1.2"])
        self.assertEqual(models[0]["variant"], "muse-wonder-1.0-contributor")
        self.assertEqual(default, "muse-wonder-1.0-contributor")

    def test_a_contributor_id_with_no_plain_twin_stays_listed(self):
        models, _ = registry.muse_catalog({"models": [{"modelId": "muse-x-contributor"}]})
        self.assertEqual([m["id"] for m in models], ["muse-x-contributor"])

    def test_known_ids_include_variants(self):
        models, _ = registry.muse_catalog(MUSE_ROWS)
        self.assertIn("muse-spark-1.2-contributor", registry.known_ids(models))


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.catalog = (["muse-spark-1.3"], "muse-spark-1.3")
        registry._models.clear()
        registry._inflight.clear()

        def fake_fetch(agent_id):
            self.calls.append(agent_id)
            ids, default = self.catalog
            registry._store(agent_id, [{"id": i, "label": i} for i in ids], default)

        patches = [mock.patch.object(registry, "_fetch_models", side_effect=fake_fetch),
                   mock.patch.object(registry, "_configured_default", return_value=""),
                   mock.patch.object(registry, "load", return_value={"muse": {"id": "muse", "command": ["muse"]}}),
                   mock.patch.object(registry.shutil, "which", return_value="/bin/muse")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _settle(self):
        for t in list(registry._inflight.values()):
            t.join(2)

    def test_forced_refresh_refetches_fresh_lists(self):
        registry.refresh_models()
        self._settle()
        registry.refresh_models(force=True)
        self._settle()
        self.assertEqual(self.calls, ["muse", "muse"])

    def test_fresh_lists_are_not_refetched(self):
        registry.refresh_models()
        self._settle()
        registry.refresh_models()
        self._settle()
        self.assertEqual(self.calls, ["muse"])

    def test_old_lists_are_refetched(self):
        registry.refresh_models()
        self._settle()
        registry._models["muse"]["fetched_at"] = time.time() - registry.MODELS_TTL - 1
        registry.refresh_models()
        self._settle()
        self.assertEqual(self.calls, ["muse", "muse"])

    def test_unknown_model_asks_again_once_then_refuses(self):
        registry.refresh_models()
        self._settle()
        self.catalog = (["muse-wonder-1.0", "muse-spark-1.3"], "")
        registry.check_model("muse", "muse-wonder-1.0")  # new since the cache: re-asked, accepted
        self.catalog = (["muse-wonder-1.0"], "")
        with self.assertRaisesRegex(ValueError, "muse-wonder-1.0"):
            registry.check_model("muse", "muse-gone-9")

    def test_model_check_skips_agents_that_list_nothing(self):
        self.catalog = ([], "")
        registry.check_model("muse", "anything")

    def test_long_lists_are_checked_whole_but_shown_capped(self):
        self.catalog = ([f"m{i}" for i in range(40)], "")
        registry._fetch_models("muse")
        registry.check_model("muse", "m39")  # past the shown cap, still known
        self.assertEqual(len(registry._listing("muse")["models"]), registry.MAX_MODELS)
        with self.assertRaises(ValueError):
            registry.check_model("muse", "m99")


class DefaultTest(unittest.TestCase):
    def test_every_agents_own_config_names_its_default(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            h = Path(home)
            (h / ".gemini" / "antigravity-cli").mkdir(parents=True)
            (h / ".gemini" / "antigravity-cli" / "settings.json").write_text(json.dumps({"model": "Gemini 4 Argon (Medium)"}))
            (h / ".qwen").mkdir()
            (h / ".qwen" / "settings.json").write_text(json.dumps({"model": {"name": "qwen/qwen3-coder"}}))
            (h / ".config" / "opencode").mkdir(parents=True)
            (h / ".config" / "opencode" / "opencode.json").write_text(json.dumps({"model": "opencode/big-pickle"}))
            (h / ".codex").mkdir()
            (h / ".codex" / "config.toml").write_text('model = "gpt-6.1-sol"\n')
            with mock.patch.object(registry.Path, "home", return_value=h):
                agy = [{"id": "gemini-4-argon-medium", "label": "Gemini 4 Argon (Medium)"}]
                self.assertEqual(registry._configured_default("antigravity", agy), "gemini-4-argon-medium")
                self.assertEqual(registry._configured_default("qwen"), "qwen/qwen3-coder")
                self.assertEqual(registry._configured_default("opencode"), "opencode/big-pickle")
                self.assertEqual(registry._configured_default("codex"), "gpt-6.1-sol")
                self.assertEqual(registry._configured_default("grok"), "")  # grok's own list marks it


    def test_configured_default_beats_the_catalog(self):
        registry._models.clear()
        with mock.patch.object(registry, "_configured_default", return_value="muse-wonder-1.0"):
            registry._store("muse", [{"id": "muse-wonder-1.0", "label": "x"}], "muse-wonder-1.0-contributor")
        self.assertEqual(registry._models["muse"]["default_model"], "muse-wonder-1.0")


if __name__ == "__main__":
    unittest.main()
