"""Small HTTP helper: JSON GET with timeout, polite User-Agent and retries."""
from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)
USER_AGENT = "job-radar/1.0 (+https://mustaphaseriki.dev)"


class SourceError(Exception):
    """A source failed; the run carries on with the other sources."""


def get_json(url: str, params: dict | None = None, basic_user: str | None = None,
             timeout: int = 20, retries: int = 3) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if basic_user is not None:
        token = base64.b64encode(f"{basic_user}:".encode()).decode()
        headers["Authorization"] = f"Basic {token}"

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 429 and 5xx are worth retrying; 4xx (bad key, bad request) are not.
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                wait = 2 ** attempt
                log.warning("HTTP %s, retrying in %ss", e.code, wait)
                time.sleep(wait)
                continue
            raise SourceError(f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise SourceError(f"network error: {e}") from None
    raise SourceError("unreachable")
