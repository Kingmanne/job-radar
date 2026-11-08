"""Hacker News "Ask HN: Who is hiring?" via the Algolia HN API.

Finds the latest monthly thread, reads its top-level comments and turns
the usual first line "Company | Role | Location | REMOTE | ..." into a Job.
Posts without a matching role in that first line are skipped.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from ..eligibility import classify
from ..filters import TITLE_WORDS
from ..http import get_json
from ..models import Job
from ..text import strip_html

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"

# A segment that is really location / contract info, not the job title.
NOT_ROLE = re.compile(r"\b(remote|onsite|on-site|hybrid|full[- ]?time|part[- ]?time|contract|visa|"
                      r"\$|£|€|\d+k)\b", re.I)
ROLE_NOUN = re.compile(r"\b(engineers?|sre|architects?|lead|leads|specialists?|administrators?|admins?|"
                       r"devops|devsecops|manager)\b", re.I)


def latest_thread_id(_get=get_json) -> int | None:
    data = _get(SEARCH_URL, params={"tags": "story,author_whoishiring", "hitsPerPage": 10})
    for hit in data.get("hits") or []:
        if (hit.get("title") or "").lower().startswith("ask hn: who is hiring"):
            return int(hit["objectID"])
    return None


def parse_comment(c: dict) -> Job | None:
    raw = c.get("text") or ""
    if not raw or c.get("author") is None:
        return None
    first = html.unescape(re.split(r"<p>|\n", raw, maxsplit=1)[0])
    first = re.sub(r"<[^>]+>", "", first).strip()
    parts = [p.strip() for p in first.split("|") if p.strip()]
    if len(parts) < 2:
        return None
    if re.match(r"^(seeking|hiring|looking for)\b", parts[0], re.I) and len(parts) > 2:
        parts = parts[1:]                     # "SEEKING FREELANCER | Company | ..."
    candidates = [p for p in parts[1:] if not NOT_ROLE.search(p)]
    role = next((p for p in candidates if any(w in p.lower() for w in TITLE_WORDS) and ROLE_NOUN.search(p)), None)
    if not role:
        return None
    others = [p for p in parts[1:] if p is not role]
    location = " | ".join(others)
    remote = "remote" in first.lower()
    desc = strip_html(raw)
    elig, why = classify(location, desc, remote)
    created = c.get("created_at_i")
    return Job(
        source="hn", source_id=str(c["id"]), title=role[:120], company=parts[0][:80],
        location=location[:120], url=f"https://news.ycombinator.com/item?id={c['id']}",
        description=desc, remote=remote,
        posted=datetime.fromtimestamp(created, timezone.utc).date().isoformat() if created else None,
        search="hn who is hiring", eligibility=elig, eligibility_reason=why, extra={"via": "Hacker News"},
    )


def fetch(_get=get_json) -> list[Job]:
    thread = latest_thread_id(_get)
    if thread is None:
        return []
    item = _get(ITEM_URL.format(id=thread))
    jobs = (parse_comment(c) for c in item.get("children") or [])
    return [j for j in jobs if j]
