"""What an agent actually did, in full, for the panel's expandable rows.

Every adapter reports tool calls, results and edits through these helpers so no agent shows less than
another: a tool's whole input, a result up to the run's per-event cap, and an edit as a unified diff.
Standard library only.
"""

from __future__ import annotations

import difflib
import json

LIMIT = 3900  # under Run.add's 4000-character detail cap, with room for the cut marker


def clip(text: object, limit: int = LIMIT) -> str:
    s = text if isinstance(text, str) else json.dumps(text, default=str)
    return s if len(s) <= limit else s[:limit] + "\n… (cut)"


def args_detail(args: object, shown: str = "") -> str:
    """A tool call's whole input as readable lines. Empty when the one-line summary already says it all."""
    try:
        data = json.loads(args) if isinstance(args, str) else args
    except (TypeError, ValueError):
        data = args
    if not data:
        return ""
    if isinstance(data, dict):
        rows = [f"{k}: {v if isinstance(v, str) else json.dumps(v, default=str)}" for k, v in data.items()]
        text = "\n".join(rows)
        if len(data) == 1 and text.split(": ", 1)[-1].strip() == shown.strip():
            return ""
        return clip(text)
    text = data if isinstance(data, str) else json.dumps(data, default=str)
    return "" if text.strip() == shown.strip() else clip(text)


def unified(path: str, old: str | None, new: str | None) -> str:
    """A unified diff of one file. A missing `old` is a new file; a missing `new` a deletion."""
    a = (old or "").splitlines()
    b = (new or "").splitlines()
    body = list(difflib.unified_diff(a, b, f"a/{path}", f"b/{path}", lineterm="", n=2))
    return "\n".join(body) if body else f"{path}: no textual change"


# (old, new) argument names that agents use for a replacement edit, compared case-insensitively
PAIRS = (("old_str", "new_str"), ("old_string", "new_string"), ("oldtext", "newtext"), ("old_text", "new_text"),
         ("targetcontent", "replacementcontent"), ("search", "replace"), ("find", "replace"), ("old", "new"),
         ("oldcontent", "newcontent"), ("oldstring", "newstring"), ("before", "after"), ("target", "replacement"))
# argument names that hold the whole new content of a file
WHOLE = ("content", "file_text", "filetext", "text", "codecontent", "new_content", "newcontent", "contents")
PATHS = ("path", "file_path", "filepath", "targetfile", "absolutepath", "file", "filename")


def edit_detail(args: object) -> str:
    """The change an edit tool call made, from its arguments: a diff for a replacement, the new text for a write."""
    try:
        data = json.loads(args) if isinstance(args, str) else args
    except (TypeError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    low = {str(k).lower(): v for k, v in data.items()}
    path = next((str(low[k]) for k in PATHS if low.get(k)), "file")
    for old_key, new_key in PAIRS:
        if old_key in low and new_key in low:
            return clip(unified(path, str(low[old_key]), str(low[new_key])))
    for key in WHOLE:
        if isinstance(low.get(key), str) and low[key]:
            return clip(unified(path, None, low[key]))
    patch = low.get("patch") or low.get("diff") or low.get("input")
    if isinstance(patch, str) and patch.strip():
        return clip(patch)
    return ""


def diff_blocks(content: object) -> str:
    """ACP tool-call content: every `diff` block ({path, oldText, newText}) as one unified diff."""
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "diff" and block.get("path"):
            parts.append(unified(str(block["path"]), block.get("oldText"), block.get("newText")))
    return clip("\n".join(parts)) if parts else ""
