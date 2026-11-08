"""Himalayas remote jobs: https://himalayas.app/api

Search endpoint with country=United Kingdom returns jobs open to UK
applicants (including worldwide ones). Terms: keep results private,
link to the job / Himalayas, use applicationLink unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..eligibility import classify
from ..http import get_json
from ..models import Job
from ..money import DEFAULT_FX, normalise_period, to_gbp
from ..text import strip_html

SEARCH_URL = "https://himalayas.app/jobs/api/search"


def _location(restrictions: list[str]) -> str:
    if not restrictions:
        return "Remote: Worldwide"
    uk = [r for r in restrictions if r.lower() in ("united kingdom", "uk", "great britain")]
    if uk and len(restrictions) > 3:
        return f"Remote: UK + {len(restrictions) - 1} other countries"
    return "Remote: " + ", ".join(restrictions[:5])


def normalise(r: dict, search: str = "", fx: dict | None = None) -> Job:
    period = r.get("salaryPeriod") or "annual"
    lo, kind = normalise_period(r.get("minSalary"), period)
    hi, _ = normalise_period(r.get("maxSalary"), period)
    cur = r.get("currency") or "USD"
    desc = strip_html(r.get("description") or r.get("excerpt"))
    restrictions = r.get("locationRestrictions") or []
    elig, why = classify(None, desc, True, restrictions)
    pub = r.get("pubDate")
    return Job(
        source="himalayas",
        source_id=str(r.get("guid") or r.get("applicationLink")),
        title=(r.get("title") or "").strip(),
        company=(r.get("companyName") or "").strip(),
        location=_location(restrictions),
        url=r.get("applicationLink") or "",
        description=desc,
        salary_min=to_gbp(lo, cur, fx), salary_max=to_gbp(hi, cur, fx), salary_period=kind,
        currency="GBP", remote=True,
        posted=datetime.fromtimestamp(pub, timezone.utc).date().isoformat() if pub else None,
        search=search, eligibility=elig, eligibility_reason=why,
        extra={"original_salary": [r.get("minSalary"), r.get("maxSalary"), cur, period],
               "seniority": r.get("seniority"), "via": "Himalayas"},
    )


def fetch(query: str, max_pages: int = 2, fx: dict | None = DEFAULT_FX, _get=get_json) -> list[Job]:
    jobs: list[Job] = []
    for page in range(1, max_pages + 1):
        data = _get(SEARCH_URL, params={"q": query, "country": "United Kingdom", "sort": "recent", "page": page})
        batch = data.get("jobs") or []
        jobs.extend(normalise(r, f"himalayas: {query}", fx) for r in batch)
        if not batch:
            break
    return jobs
