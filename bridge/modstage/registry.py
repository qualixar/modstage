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
import time
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


# ---- models: asked of each CLI itself, in the background, and asked again when old ----

MAX_MODELS = 16
MODELS_TTL = 600  # seconds a list is trusted; plans and catalogs change while the bridge stays up
# agent id -> (command, parser). Agents with no list command offer their default plus any id typed.
MODEL_SOURCES: dict[str, tuple[list[str], str]] = {
    "codex": (["codex", "debug", "models"], "codex_json"),
    "grok": (["grok", "models"], "bullets"),
    "antigravity": (["agy", "models"], "tabbed"),
    "opencode": (["opencode", "models"], "lines"),
}
_models: dict[str, dict] = {}
_models_lock = threading.Lock()
_inflight: dict[str, threading.Thread] = {}
CONTRIBUTOR = "-contributor"


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
    return models, default


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text())
    return data if isinstance(data, dict) else {}


def _configured_default(agent_id: str, models: list[dict] | None = None) -> str:
    """The model the CLI uses when none is given, where its own config says so. Antigravity's settings
    name a display label ("Gemini 4 Argon (Medium)"); it is matched to the listed id."""
    home = Path.home()
    try:
        if agent_id == "codex":
            for line in (home / ".codex" / "config.toml").read_text().splitlines():
                if line.strip().startswith("model ") or line.strip().startswith("model="):
                    return line.split("=", 1)[1].strip().strip('"')
        if agent_id == "muse":
            return str(_read_json(home / ".config" / "muse" / "settings.json").get("model") or "")
        if agent_id == "antigravity":
            label = str(_read_json(home / ".gemini" / "antigravity-cli" / "settings.json").get("model") or "")
            return next((m["id"] for m in models or [] if label and m.get("label") == label), "")
        if agent_id == "qwen":
            model = _read_json(home / ".qwen" / "settings.json").get("model")
            return str((model or {}).get("name") or "") if isinstance(model, dict) else str(model or "")
        if agent_id == "opencode":
            for name in ("opencode.json", "config.json"):
                cfg = home / ".config" / "opencode" / name
                if cfg.exists():
                    return str(_read_json(cfg).get("model") or "")
    except (OSError, ValueError, IndexError):
        pass
    return ""


def muse_catalog(result: dict) -> tuple[list[dict], str]:
    """(models, default) from Muse's MSP `model/list` result (muse schema: ModelCatalogEntry rows).
    Muse lists each model twice: plain and "-contributor" (the same model; your content may be used
    for product improvement). The contributor id folds into its model as `variant`."""
    rows = [m for m in (result.get("models") or []) if m.get("modelId")]
    ids = {m["modelId"] for m in rows}
    models = []
    for m in rows:
        mid = m["modelId"]
        if mid.endswith(CONTRIBUTOR) and mid[: -len(CONTRIBUTOR)] in ids:
            continue
        entry = {"id": mid, "label": m.get("displayLabel") or mid}
        if mid + CONTRIBUTOR in ids:
            entry["variant"] = mid + CONTRIBUTOR
        models.append(entry)
    default = next((m["modelId"] for m in rows if m.get("isDefault")), "")
    return models, default


def known_ids(models: list[dict]) -> set[str]:
    """Every id a listed model answers to, variants included."""
    return {m["id"] for m in models} | {m["variant"] for m in models if m.get("variant")}


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


def _store(agent_id: str, models: list[dict], default: str) -> None:
    """Cache a fresh list. The CLI's own config names the model it really uses, so it wins over a catalog."""
    with _models_lock:
        _models[agent_id] = {"models": models, "default_model": _configured_default(agent_id, models) or default,
                             "fetched_at": time.time()}


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
    _store(agent_id, models, default)


def _stale(agent_id: str) -> bool:
    cached = _models.get(agent_id)
    return not cached or time.time() - cached.get("fetched_at", 0) > MODELS_TTL


def _background_fetch(agent_id: str) -> None:
    with _models_lock:
        running = _inflight.get(agent_id)
        if running and running.is_alive():
            return
        thread = threading.Thread(target=_fetch_models, args=(agent_id,), daemon=True)
        _inflight[agent_id] = thread
    thread.start()


def refresh_models(force: bool = False) -> None:
    """Ask installed CLIs for their models in the background: all of them when forced (each Claude Code
    session start), otherwise only lists older than MODELS_TTL. Readers keep the old list meanwhile."""
    for spec in load().values():
        if shutil.which(spec["command"][0]) and (force or _stale(spec["id"])):
            _background_fetch(spec["id"])


def prefetch_models() -> None:
    """At bridge start: fetch every list."""
    refresh_models(force=True)


def check_model(agent_id: str, model: str | None) -> None:
    """Refuse a model the agent's CLI does not list. A miss asks the CLI again first (the catalog may
    have changed since the cache). Skipped when the CLI listed nothing (it takes any id)."""
    if not model:
        return
    for attempt in (0, 1):
        cached = _models.get(agent_id) or {}
        models = cached.get("models") or []
        if not models or model in known_ids(models):
            return
        if attempt == 0:
            _fetch_models(agent_id)
    offered = ", ".join(sorted(known_ids(models)))
    raise ValueError(f"{agent_id} does not offer model '{model}' now. It offers: {offered}")


def _listing(agent_id: str) -> dict:
    cached = _models.get(agent_id)
    if not cached:
        return {"models": [], "default_model": _configured_default(agent_id)}
    return {"models": cached["models"][:MAX_MODELS], "default_model": cached["default_model"]}


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
                       **_listing(spec["id"])})
    refresh_models()  # lists older than MODELS_TTL are fetched again in the background
    return {"agents": report, "config": str(HOME / "agents.json")}
