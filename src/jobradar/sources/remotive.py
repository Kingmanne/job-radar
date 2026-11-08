"""Remotive: https://github.com/remotive-com/remote-jobs-api

One call per run for the whole feed, filtered locally (they ask for no more
than ~4 calls a day). Jobs are 24h delayed. A category can be given, but the
slug must match theirs exactly or you get an unfiltered sample back.
Terms: link back to the Remotive URL and name Remotive as the source.
"""
from __future__ import annotations

from ..eligibility import classify
from ..http import get_json
from ..models import Job
from ..money import DEFAULT_FX, normalise_period, parse_salary_text, to_gbp
from ..text import strip_html

URL = "https://remotive.com/api/remote-jobs"


def normalise(r: dict, search: str = "", fx: dict | None = None) -> Job:
    lo, hi, cur, period = parse_salary_text(r.get("salary"))
    lo, kind = normalise_period(lo, period)
    hi, _ = normalise_period(hi, period)
    loc = r.get("candidate_required_location") or ""
    desc = strip_html(r.get("description"))
    elig, why = classify(loc, desc, True)
    return Job(
        source="remotive", source_id=str(r["id"]),
        title=(r.get("title") or "").strip(), company=(r.get("company_name") or "").strip(),
        location=f"Remote: {loc}" if loc else "Remote", url=r.get("url") or "",
        description=desc,
        salary_min=to_gbp(lo, cur, fx), salary_max=to_gbp(hi, cur, fx), salary_period=kind,
        currency="GBP", remote=True, posted=(r.get("publication_date") or "")[:10] or None,
        search=search, eligibility=elig, eligibility_reason=why,
        extra={"original_salary": r.get("salary"), "job_type": r.get("job_type"), "via": "Remotive"},
    )


def fetch(category: str | None = None, fx: dict | None = DEFAULT_FX, _get=get_json) -> list[Job]:
    data = _get(URL, params={"category": category} if category else None, timeout=60)
    return [normalise(r, f"remotive: {category or 'all'}", fx) for r in data.get("jobs") or []]
