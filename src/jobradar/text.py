"""Turn HTML job descriptions into plain text."""
from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_BREAKS = re.compile(r"<\s*(br|/p|/li|/div|/h\d)\s*/?>", re.I)
_SPACES = re.compile(r"[ \t\r\f\v]+")


def strip_html(value: str | None, limit: int = 6000) -> str:
    if not value:
        return ""
    text = html.unescape(value)          # Greenhouse double-escapes its HTML
    text = _BREAKS.sub("\n", text)
    text = html.unescape(_TAG.sub(" ", text))
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)[:limit]
