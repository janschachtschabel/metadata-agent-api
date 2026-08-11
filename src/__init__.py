"""Metadata Agent API."""

import sys
from typing import Any


def ensure_utf8_output(*streams: Any) -> None:
    """
    Make the output streams able to carry the emoji this package prints.

    Windows consoles default to a legacy code page (cp1252) that cannot encode
    them, so a plain `print` raises UnicodeEncodeError — in the middle of a
    half-finished upload. Streams that cannot be reconfigured (pytest's capture,
    for one) are left alone; on Linux and Vercel stdout is UTF-8 already and
    this changes nothing.
    """
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


ensure_utf8_output(sys.stdout, sys.stderr)
