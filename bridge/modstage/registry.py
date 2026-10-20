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
     "color": "#4C9BFF", "steer": "native", "model_args": []},
    {"id": "muse", "name": "Muse", "protocol": "muse-msp", "command": ["muse", "serve"],
     "color": "#A77BFF", "steer": "native", "model_args": ["--model", "{model}"]},
    {"id": "grok", "name": "Grok", "protocol": "acp", "command": ["grok", "agent", "stdio"],
     "color": "#F5B93A", "steer": "queue", "model_args": ["-m", "{model}"], "model_args_before": 2,
     "effort_args": ["--effort", "{effort}"], "efforts": ["low", "medium", "high"]},
    {"id": "antigravity", "name": "Antigravity", "protocol": "stream-json",
     "command": ["agy", "--input-format", "stream-json", "--output-format", "stream-json", "--print="],
     "auto_args": ["--dangerously-skip-permissions"], "approvals": "cli", "ask_readonly": "agy-project",
     "color": "#2EC4B6", "steer": "queue", "model_args": ["--model", "{model}"], "model_args_before": 1},
    {"id": "kimi", "name": "Kimi", "protocol": "acp", "command": ["kimi", "acp"],
     "color": "#FF6B9D", "steer": "queue", "model_args": ["-m", "{model}"], "model_args_before": 1},
    {"id": "qwen", "name": "Qwen Code", "protocol": "acp", "command": ["qwen", "--acp"],
     "color": "#6FCF5B", "steer": "queue", "model_args": ["--model", "{model}"]},
    {"id": "opencode", "name": "OpenCode", "protocol": "acp", "command": ["opencode", "acp"],
     "color": "#8E9AAF", "steer": "queue", "model_args": [], "model_via": "acp-config"},
    {"id": "hermes", "name": "Hermes", "protocol": "acp", "command": ["hermes", "acp"],
     "color": "#E4572E", "steer": "queue", "model_args": [], "model_via": "acp-config"},
]

# How to get each CLI when it is missing: shown in the panel, by stage_agents and in the "not installed" error.
# Each install URL or package was checked live on 18 Oct 2026 (scripts fetched; npm names resolved).
INSTALL = {
    "codex": "npm install -g @openai/codex",
    "muse": "curl -fsSL https://dev.meta.ai/install.sh | bash",
    "grok": "curl -fsSL https://x.ai/cli/install.sh | bash",
    "antigravity": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
    "kimi": "see https://github.com/MoonshotAI/kimi-cli",
    "qwen": "npm install -g @qwen-code/qwen-code",
    "opencode": "npm install -g opencode-ai",
    "hermes": "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash (Windows: iex (irm https://hermes-agent.nousresearch.com/install.ps1))",
}
for _spec in BUILTIN:
    _spec["install"] = INSTALL[_spec["id"]]


def install_hint(spec: dict) -> str:
    """One line telling a person how to install this agent's CLI (empty when unknown)."""
    return spec.get("install") or ""


def not_installed(spec: dict) -> str:
    """The sentence shown when an agent's CLI is not on this machine."""
    how = install_hint(spec)
    return (f"{spec.get('name', spec['id'])} is not installed ({spec['command'][0]} not found on PATH). "
            + (f"Install it: {how}. Then try again." if how else f"Install it and make sure `{spec['command'][0]}` is on PATH, then try again."))


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


def argv(spec: dict, model: str | None, effort: str | None = None) -> list[str]:
    cmd = list(spec["command"])
    extra: list[str] = []
    if model and spec.get("model_args"):
        extra += [a.replace("{model}", model) for a in spec["model_args"]]
    if effort and spec.get("effort_args"):
        extra += [a.replace("{effort}", effort) for a in spec["effort_args"]]
    if extra:
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
    if spec["id"] == "hermes":
        cfg = _hermes_home() / "config.yaml"
        try:
            block = _yaml_block(cfg.read_text(), "approvals")
        except OSError:
            return ""
        if block.get("mode") in ("off", "yolo", "never"):
            return f"approvals are off in {cfg} (approvals.mode: {block['mode']}); ModStage cannot ask you first"
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
    "opencode": (["opencode", "models", "--verbose"], "opencode_verbose"),
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
                entry = {"id": m["slug"], "label": m.get("display_name") or m["slug"]}
                levels = [str(x.get("effort")) for x in m.get("supported_reasoning_levels") or [] if x.get("effort")]
                if levels:
                    entry["efforts"] = levels
                    entry["default_effort"] = str(m.get("default_reasoning_level") or "")
                models.append(entry)
    elif kind == "opencode_verbose":  # "provider/model\n{json}" blocks: the id, and the display name when it has one
        import re
        for block in re.split(r"\n(?=[a-z0-9_.-]+/[A-Za-z0-9_.:-]+\n)", text):
            head, _, body = block.partition("\n")
            try:
                info = json.loads(body)
            except ValueError:
                continue
            # Its models list `variants` (effort levels), but `opencode acp` advertises no effort setting (checked live
            # 18 Oct 2026: its session offers only `model` and `mode`), so none are offered: ModStage cannot apply one.
            models.append({"id": head.strip(), "label": info.get("name") or head.strip()})
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


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _yaml_block(text: str, name: str) -> dict[str, str]:
    """The simple `key: value` lines under a top-level `name:` block of a YAML file. Stdlib only: ModStage
    needs two or three scalar settings, not a YAML parser."""
    out: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            inside = line.split("#")[0].strip() == f"{name}:"
            continue
        if inside and ":" in line:
            key, _, value = line.strip().partition(":")
            out[key.strip()] = value.split(" #")[0].strip().strip("'\"")
    return out


# ---- OpenCode: which providers the user really has, and a list worth showing ----

PER_PROVIDER = 8  # models shown per provider in the panel; the whole filtered list is still accepted by check_model


def _opencode_dirs() -> tuple[Path, Path]:
    """(data dir, config dir) the way OpenCode itself places them: XDG when set, else ~/.local/share and ~/.config."""
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "opencode"
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "opencode"
    return data, config


def _strip_jsonc(text: str) -> str:
    """JSON with // and /* */ comments and trailing commas (OpenCode's opencode.jsonc) as plain JSON.
    Comment markers inside strings, like the // of a URL, are left alone."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(c)
        i += 1
    import re
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _opencode_config() -> dict:
    """OpenCode's own config: $OPENCODE_CONFIG when set, else the first of opencode.json, opencode.jsonc, config.json."""
    paths = [Path(os.environ["OPENCODE_CONFIG"])] if os.environ.get("OPENCODE_CONFIG") else []
    paths += [_opencode_dirs()[1] / name for name in ("opencode.json", "opencode.jsonc", "config.json")]
    for path in paths:
        try:
            data = json.loads(_strip_jsonc(path.read_text()))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def opencode_providers() -> set[str]:
    """Providers the user has set up: the NAMES in OpenCode's auth file (never the credentials), plus the provider of
    the configured model and any provider the config has a block for. Empty when OpenCode shows none of this."""
    names: set[str] = set()
    try:
        auth = json.loads((_opencode_dirs()[0] / "auth.json").read_text())
        names |= {str(k) for k in auth} if isinstance(auth, dict) else set()
    except (OSError, ValueError):
        pass
    cfg = _opencode_config()
    for key in ("model", "small_model"):
        if "/" in str(cfg.get(key) or ""):
            names.add(str(cfg[key]).split("/", 1)[0])
    if isinstance(cfg.get("provider"), dict):
        names |= {str(k) for k in cfg["provider"]}
    return names


def _version_key(model_id: str) -> tuple[int, ...]:
    """Newest first: the numbers in a model id (claude-sonnet-5-5 -> 5, 5) negated and padded; date stamps are ignored."""
    import re
    nums = [int(x) for x in re.findall(r"\d+", model_id.split("/", 1)[-1]) if len(x) <= 3][:4]
    return tuple(-n for n in nums) + (0,) * (4 - len(nums))


def shape_opencode(models: list[dict], default: str, providers: set[str]) -> list[dict]:
    """Make OpenCode's listing usable. `opencode models` prints every catalog model, in provider order, so a cap on its
    first lines hides most providers. Keep the providers the user has set up (all of them when none is known), put the
    default model's provider first and the default model first in it, the rest of each provider newest first, and
    name the provider on each entry so the route is clear."""
    keep = [m for m in models if not providers or m["id"].split("/", 1)[0] in providers] if providers else list(models)
    keep = keep or list(models)
    first = default.split("/", 1)[0] if "/" in default else ""
    names = sorted({m["id"].split("/", 1)[0] for m in keep}, key=lambda p: (p != first, p))
    out = []
    for name in names:
        group = sorted((m for m in keep if m["id"].split("/", 1)[0] == name),
                       key=lambda m: (m["id"] != default, _version_key(m["id"]), m["label"].lower(), m["id"]))
        out += [{**m, "provider": name, "label": f"{m['label']} · {name}" if len(names) > 1 else m["label"]} for m in group]
    return out


def capped(models: list[dict]) -> list[dict]:
    """The models the panel offers: PER_PROVIDER from each provider when the list is grouped, else the first MAX_MODELS."""
    if not any(m.get("provider") for m in models):
        return models[:MAX_MODELS]
    seen: dict[str, int] = {}
    out = []
    for m in models:
        n = seen.get(m["provider"], 0)
        seen[m["provider"]] = n + 1
        if n < PER_PROVIDER:
            out.append(m)
    return out


def _source_stamp(agent_id: str) -> tuple:
    """Modification times of the files a list depends on, so a list is fetched again when they change
    (a provider added in OpenCode shows up without restarting the bridge)."""
    if agent_id != "opencode":
        return ()
    data, config = _opencode_dirs()
    files = [data / "auth.json"] + [config / n for n in ("opencode.json", "opencode.jsonc", "config.json")]
    stamp = []
    for f in files:
        try:
            stamp.append(f.stat().st_mtime_ns)
        except OSError:
            stamp.append(0)
    return tuple(stamp)


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
            return str(_opencode_config().get("model") or "")
        if agent_id == "hermes":
            return _yaml_block((_hermes_home() / "config.yaml").read_text(), "model").get("default", "")
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
        if m.get("variants"):
            entry["efforts"] = [str(v) for v in m["variants"]]
            entry["default_effort"] = str(m.get("defaultReasoningEffort") or "")
        if mid + CONTRIBUTOR in ids:
            entry["variant"] = mid + CONTRIBUTOR
        models.append(entry)
    default = next((m["modelId"] for m in rows if m.get("isDefault")), "")
    return models, default


def configured_effort(agent_id: str, model: str = "") -> str:
    """The thinking effort the CLI uses when none is asked for, where its own config says so."""
    home = Path.home()
    try:
        if agent_id == "codex":
            for line in (home / ".codex" / "config.toml").read_text().splitlines():
                if line.strip().startswith("model_reasoning_effort"):
                    return line.split("=", 1)[1].strip().strip('"')
        if agent_id == "muse":
            per = _read_json(home / ".config" / "muse" / "settings.json").get("model_reasoning_efforts") or {}
            return str(per.get(model) or "")
        if agent_id == "grok":
            for line in (Path(os.environ.get("GROK_HOME", home / ".grok")) / "config.toml").read_text().splitlines():
                if line.strip().startswith("default_reasoning_effort"):
                    return line.split("=", 1)[1].strip().strip('"')
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    return ""


def efforts_for(agent_id: str, model: str | None) -> tuple[list[str], str]:
    """(effort levels this model takes, the one it uses by default). The agent's own list when its CLI
    has one level set for every model (Grok); else the model's own entry in its catalog."""
    spec = load().get(agent_id) or {}
    cached = _models.get(agent_id) or {}
    model = model or cached.get("default_model") or ""
    entry = next((m for m in cached.get("models") or [] if model in (m.get("id"), m.get("variant"))), {})
    levels = list(entry.get("efforts") or spec.get("efforts") or [])
    default = configured_effort(agent_id, model) or entry.get("default_effort") or ""
    return levels, default


def check_effort(agent_id: str, model: str | None, effort: str | None) -> None:
    """Refuse an effort the agent cannot take, with what it does offer, instead of starting a run that ignores it."""
    if not effort:
        return
    levels, _ = efforts_for(agent_id, model)
    if not levels:
        hint = (" Its effort is part of the model name: pick the High, Medium or Low model." if agent_id == "antigravity" else "")
        raise ValueError(f"{agent_id} has no thinking-effort setting ModStage can apply.{hint}")
    if effort not in levels:
        raise ValueError(f"{agent_id} does not offer effort '{effort}' for {model or 'its default model'}. It offers: {', '.join(levels)}")


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
        chosen = _configured_default(agent_id, models) or default
        if agent_id == "opencode" and models:
            models = shape_opencode(models, chosen, opencode_providers())
        _models[agent_id] = {"models": models, "default_model": chosen, "fetched_at": time.time(),
                             "stamp": _source_stamp(agent_id)}


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
    return (not cached or time.time() - cached.get("fetched_at", 0) > MODELS_TTL
            or cached.get("stamp", ()) != _source_stamp(agent_id))


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
    spec = load().get(agent_id) or {}
    if not cached:
        return {"models": [], "default_model": _configured_default(agent_id), "efforts": spec.get("efforts") or [],
                "default_effort": configured_effort(agent_id)}
    default_model = cached["default_model"]
    return {"models": capped(cached["models"]), "default_model": default_model, "efforts": spec.get("efforts") or [],
            "default_effort": efforts_for(agent_id, default_model)[1]}


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
                       "install": install_hint(spec),
                       "takes_model": bool(spec.get("model_args")) or spec["protocol"] == "codex-app-server"
                       or bool(spec.get("model_via")),
                       **_listing(spec["id"])})
    refresh_models()  # lists older than MODELS_TTL are fetched again in the background
    return {"agents": report, "config": str(HOME / "agents.json")}
