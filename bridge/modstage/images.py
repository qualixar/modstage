"""Images handed to a run: read once, in each protocol's own shape."""

from __future__ import annotations

import base64


def b64(image: dict) -> str:
    with open(image["path"], "rb") as f:
        return base64.b64encode(f.read()).decode()


class NoImages(ValueError):
    """This CLI has no image input ModStage can use; say so instead of dropping the image."""
