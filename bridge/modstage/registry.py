"""The agent registry: which agents ModStage can run, and how.

Built-in entries cover agents verified to start this way. Anyone can plug in more by
adding entries to $MODSTAGE_HOME/agents.json (default ~/.modstage/agents.json):

    {"agents": [
      {"id": "deepseek", "name": "DeepSeek via OpenCode", "protocol": "acp",
       "command": ["opencode", "acp"], "color": "#4D6BFE",
       "model_args": ["--model", "{model}"]}
    ]}

protocol: "acp" (Agent Client Protocol over stdio; most agents), "codex-app-server", "muse-msp",
or "stream-json" (a print mode that reads one NDJSON message per turn, like Antigravity's agy).
A user entry with the same id replaces the built-in one; "disabled": true hides one.
"""

from __future__ import annotations

from . import __version__

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

HOME = Path(os.environ.get("MODSTAGE_HOME", Path.home() / ".modstage"))

# steer: "native" = a message joins the running turn; "queue" = it runs after the turn ends.
BUILTIN: list[dict] = [
    {"id": "codex", "name": "Codex", "protocol": "codex-app-server", "command": ["codex", "app-server"],
     "color": "#7AA2F7", "steer": "native", "model_args": []},
    {"id": "muse", "name": "Muse", "protocol": "muse-msp", "command": ["muse", "serve"],
     "color": "#C792EA", "steer": "native", "model_args": ["--model", "{model}"]},
    {"id": "grok", "name": "Grok", "protocol": "acp", "command": ["grok", "agent", "stdio"],
     "color": "#E0AF68", "steer": "queue", "model_args": ["-m", "{model}"], "model_args_before": 2},
    {"id": "antigravity", "name": "Antigravity", "protocol": "stream-json",
     "command": ["agy", "--input-format", "stream-json", "--output-format", "stream-json", "--print="],
     "auto_args": ["--dangerously-skip-permissions"], "approvals": "cli", "ask_readonly": "agy-project",
     "color": "#8AB4F8", "steer": "queue", "model_args": ["--model", "{model}"], "model_args_before": 1},
    {"id": "kimi", "name": "Kimi", "protocol": "acp", "command": ["kimi", "acp"],
     "color": "#F5C2E7", "steer": "queue", "model_args": ["-m", "{model}"], "model_args_before": 1},
    {"id": "qwen", "name": "Qwen Code", "protocol": "acp", "command": ["qwen", "--acp"],
     "color": "#9ECE6A", "steer": "queue", "model_args": ["--model", "{model}"]},
    {"id": "opencode", "name": "OpenCode", "protocol": "acp", "command": ["opencode", "acp"],
     "color": "#FAB387", "steer": "queue", "model_args": [], "model_via": "acp-config"},
]


def load() -> dict[str, dict]:
    agents = {a["id"]: dict(a) for a in BUILTIN}
    path = HOME / "agents.json"
    if path.exists():
        try:
            extra = json.loads(path.read_text()).get("agents", [])
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc
        for entry in extra:
            if not isinstance(entry, dict) or "id" not in entry:
                continue
            if entry.get("disabled"):
                agents.pop(entry["id"], None)
                continue
            merged = {**agents.get(entry["id"], {"steer": "queue", "color": "#CDD6F4", "model_args": []}), **entry}
            if merged.get("protocol") not in ("acp", "codex-app-server", "muse-msp", "stream-json") or not merged.get("command"):
                continue
            agents[entry["id"]] = merged
    return agents


def argv(spec: dict, model: str | None) -> list[str]:
    cmd = list(spec["command"])
    if model and spec.get("model_args"):
        extra = [a.replace("{model}", model) for a in spec["model_args"]]
        at = spec.get("model_args_before")
        cmd = cmd[:at] + extra + cmd[at:] if isinstance(at, int) else cmd + extra
    return cmd


def _approval_note(spec: dict) -> str:
    """Agents decide for themselves when to ask. Say so when one's own config never asks,
    because then the Needs-you inbox cannot catch its actions."""
    if spec["id"] == "grok":
        cfg = Path(os.environ.get("GROK_HOME", Path.home() / ".grok")) / "config.toml"
        try:
            text = cfg.read_text()
        except OSError:
            return ""
        if "always-approve" in text or "bypassPermissions" in text:
            return f"auto-approves every action ({cfg}: permission_mode); ModStage cannot ask you first"
    if spec.get("approvals") == "cli":
        return AGY_NOTE if spec.get("ask_readonly") == "agy-project" else (
            "headless agy cannot ask for permission: in ask mode it refuses anything that needs it, and the panel "
            "shows what it refused. Auto mode allows everything (its skip-permissions flag)")
    return ""


AGY_NOTE = ("headless agy cannot ask for permission. Ask mode is read-only: it may read web pages, search the web "
            "and read files in its folder; writes, shell commands and files outside its folder are refused and end "
            "the turn blocked. To let it do those, restart with autonomy \"auto\", ideally in an isolated folder")
AGY_RESTART = ("To let it proceed, start a new run with autonomy \"auto\", ideally in an isolated folder "
               "(auto allows everything)")


# ---- models: asked of each CLI itself, once, in the background ----

MAX_MODELS = 16
# agent id -> (command, parser). Agents with no list command offer their default plus any id typed.
MODEL_SOURCES: dict[str, tuple[list[str], str]] = {
    "codex": (["codex", "debug", "models"], "codex_json"),
    "grok": (["grok", "models"], "bullets"),
    "antigravity": (["agy", "models"], "tabbed"),
    "opencode": (["opencode", "models"], "lines"),
}
_models: dict[str, dict] = {}
_models_lock = threading.Lock()


def parse_models(kind: str, text: str) -> tuple[list[dict], str]:
    """(models as [{id, label}], default id or "") from a CLI's model listing."""
    models: list[dict] = []
    default = ""
    if kind == "codex_json":
        data = json.loads(text)
        for m in data.get("models", []):
            if m.get("slug"):
                models.append({"id": m["slug"], "label": m.get("display_name") or m["slug"]})
    elif kind == "bullets":  # "  * grok-4.7 (default)" / "  - grok-4.6"
        for line in text.splitlines():
            s = line.strip()
            if s[:2] in ("* ", "- "):
                mid = s[2:].split()[0]
                models.append({"id": mid, "label": mid})
                if s.startswith("* ") or "(default)" in s:
                    default = mid
    elif kind == "tabbed":  # "gemini-3.8-flash-high\tGemini 3.8 Flash (High)"
        for line in text.splitlines():
            if "\t" in line:
                mid, label = line.split("\t", 1)
                models.append({"id": mid.strip(), "label": label.strip()})
    else:
        for line in text.splitlines():
            s = line.strip()
            if s and " " not in s:
                models.append({"id": s, "label": s})
    return models[:MAX_MODELS], default


def _configured_default(agent_id: str) -> str:
    """The model the CLI uses when none is given, where its own config says so."""
    try:
        if agent_id == "codex":
            for line in (Path.home() / ".codex" / "config.toml").read_text().splitlines():
                if line.strip().startswith("model ") or line.strip().startswith("model="):
                    return line.split("=", 1)[1].strip().strip('"')
        if agent_id == "muse":
            cfg = Path.home() / ".config" / "muse" / "settings.json"
            return json.loads(cfg.read_text()).get("model", "")
    except (OSError, ValueError, IndexError):
        pass
    return ""


def muse_catalog(result: dict) -> tuple[list[dict], str]:
    """(models, default) from Muse's MSP `model/list` result (muse schema: ModelCatalogEntry rows)."""
    rows = result.get("models") or []
    models = [{"id": m["modelId"], "label": m.get("displayLabel") or m["modelId"]} for m in rows if m.get("modelId")]
    default = next((m["modelId"] for m in rows if m.get("isDefault")), "")
    return models[:MAX_MODELS], default


def _muse_models() -> tuple[list[dict], str]:
    """Muse has no list command; its session host answers `model/list` with no session and no tokens."""
    from .stdio_rpc import StdioRpc
    rpc = StdioRpc(["muse", "serve"], str(Path.home()), on_notify=lambda m: None, on_request=lambda m: None,
                   on_exit=lambda c: None, on_stderr=lambda line: None, jsonrpc=True)
    try:
        rpc.call("initialize", {"clientInfo": {"name": "modstage", "version": __version__}}, timeout=30)
        rpc.notify("initialized")
        return muse_catalog(rpc.call("model/list", {}, timeout=30))
    finally:
        rpc.close()


def kimi_catalog(text: str) -> tuple[list[dict], str]:
    """(models, default) from Kimi's own config.toml: the [models.<alias>] tables and default_model.
    `kimi -m <alias>` takes the alias."""
    import tomllib
    data = tomllib.loads(text)
    models = [{"id": alias, "label": f"{alias} ({cfg.get('model', '')})" if cfg.get("model") else alias}
              for alias, cfg in (data.get("models") or {}).items() if isinstance(cfg, dict)]
    return models[:MAX_MODELS], str(data.get("default_model") or "")


def _fetch_models(agent_id: str) -> None:
    models, default = [], ""
    source = MODEL_SOURCES.get(agent_id)
    if agent_id == "kimi":
        try:
            models, default = kimi_catalog((Path.home() / ".kimi" / "config.toml").read_text())
        except (OSError, ValueError):
            pass
    elif agent_id == "muse" and shutil.which("muse"):
        try:
            models, default = _muse_models()
        except Exception:
            pass
    elif source and shutil.which(source[0][0]):
        try:
            out = subprocess.run(source[0], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
            models, default = parse_models(source[1], out.stdout)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
    with _models_lock:
        _models[agent_id] = {"models": models, "default_model": default or _configured_default(agent_id)}


def prefetch_models() -> None:
    """Ask every installed CLI for its models in parallel; the setup check reads the cache."""
    for spec in load().values():
        if shutil.which(spec["command"][0]):
            threading.Thread(target=_fetch_models, args=(spec["id"],), daemon=True).start()


def doctor() -> dict:
    """What is installed and runnable: shown by the setup check."""
    report = []
    for spec in load().values():
        exe = shutil.which(spec["command"][0])
        version = ""
        if exe:
            try:
                out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=4)
                version = (out.stdout or out.stderr).strip().splitlines()[0][:60] if (out.stdout or out.stderr) else ""
            except (subprocess.TimeoutExpired, OSError):
                version = "installed"
        report.append({"id": spec["id"], "name": spec.get("name", spec["id"]), "color": spec.get("color"),
                       "protocol": spec["protocol"], "steer": spec.get("steer", "queue"),
                       "installed": bool(exe), "path": exe or "", "version": version,
                       "command": " ".join(spec["command"]), "note": _approval_note(spec),
                       "takes_model": bool(spec.get("model_args")) or spec["protocol"] == "codex-app-server"
                       or bool(spec.get("model_via")),
                       **_models.get(spec["id"], {"models": [], "default_model": _configured_default(spec["id"])})})
    return {"agents": report, "config": str(HOME / "agents.json")}
