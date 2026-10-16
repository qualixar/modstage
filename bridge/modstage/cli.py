"""modstage-cli: the coordination board from a shell, for agents without MCP tools.

  modstage-cli status                       who is working on what, and active claims
  modstage-cli claim <path|glob>... [--shared|--advisory] [--ttl N] [--reason TEXT]
  modstage-cli release <claim-id|path|all>
  modstage-cli check <path>...
  modstage-cli send <run-id|all> <text...> [--kind info|request|question|handoff] [--wake]
  modstage-cli inbox
  modstage-cli doing <working|idle|blocked|needs_human|done> <text...>

Identity is MODSTAGE_RUN_TOKEN, which the bridge sets for every agent it starts.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("MODSTAGE_URL", "http://127.0.0.1:47321")
TOKEN = os.environ.get("MODSTAGE_RUN_TOKEN", "")


def call(op: str, body: dict) -> dict:
    req = urllib.request.Request(f"{URL}/board/{op}", data=json.dumps(body).encode(), method="POST",
                                 headers={"X-ModStage-Run-Token": TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return {"error": json.loads(exc.read()).get("error", str(exc))}
        except ValueError:
            return {"error": str(exc)}
    except OSError as exc:
        return {"error": f"bridge unreachable: {exc}"}


def flag(args: list[str], name: str, default=None, takes_value: bool = True):
    if name not in args:
        return args, default
    i = args.index(name)
    if not takes_value:
        return args[:i] + args[i + 1:], True
    value = args[i + 1] if i + 1 < len(args) else default
    return args[:i] + args[i + 2:], value


def main(argv: list[str]) -> int:
    if not TOKEN:
        print("modstage-cli: MODSTAGE_RUN_TOKEN is not set (only agents started by ModStage can use it)")
        return 2
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "status":
        out = call("board_read", {})
    elif cmd == "claim":
        args, shared = flag(args, "--shared", False, False)
        args, advisory = flag(args, "--advisory", False, False)
        args, ttl = flag(args, "--ttl", 300)
        args, reason = flag(args, "--reason", "")
        out = call("claim", {"paths": args, "mode": "advisory" if advisory else "shared" if shared else "exclusive",
                             "ttl_s": float(ttl), "reason": reason})
    elif cmd == "release":
        out = call("release", {"claim_id": args[0] if args else "all"})
    elif cmd == "check":
        out = call("check_paths", {"paths": args})
    elif cmd == "send":
        args, kind = flag(args, "--kind", "info")
        args, wake = flag(args, "--wake", False, False)
        if len(args) < 2:
            print("usage: modstage-cli send <run-id|all> <text...>")
            return 2
        out = call("send", {"to": args[0], "body": " ".join(args[1:]), "kind": kind, "wake": bool(wake)})
    elif cmd == "inbox":
        out = call("inbox", {})
    elif cmd == "doing":
        if len(args) < 2:
            print("usage: modstage-cli doing <state> <text...>")
            return 2
        out = call("board_post", {"state": args[0], "doing": " ".join(args[1:])})
    else:
        print(f"modstage-cli: unknown command {cmd}\n{__doc__}")
        return 2
    print(json.dumps(out, indent=1))
    return 1 if "error" in out or out.get("denied") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
