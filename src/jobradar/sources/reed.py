"""Reed.co.uk Jobseeker API: https://www.reed.co.uk/developers/jobseeker

Auth: HTTP Basic, the API key is the username, empty password.
Distances are in miles. Up to 100 results per call.
"""
from __future__ import annotations

from datetime import datetime

from ..http import get_json
from ..models import Job

SEARCH_URL = "https://www.reed.co.uk/api/1.0/search"
PAGE_SIZE = 100


def _iso(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def normalise(r: dict, search: str = "") -> Job:
    lo, hi = r.get("minimumSalary"), r.get("maximumSalary")
    # Reed mixes annual and daily figures; a top figure under 2,000 is a day rate.
    period = "day" if (hi or lo or 0) and (hi or lo) < 2000 else "year"
    location = r.get("locationName") or ""
    return Job(
        source="reed",
        source_id=str(r["jobId"]),
        title=(r.get("jobTitle") or "").strip(),
        company=(r.get("employerName") or "").strip(),
        location=location,
        url=r.get("jobUrl") or f"https://www.reed.co.uk/jobs/{r['jobId']}",
        description=(r.get("jobDescription") or "").strip(),
        salary_min=lo,
        salary_max=hi,
        salary_period=period,
        currency=r.get("currency") or "GBP",
        remote="remote" in f"{location} {r.get('jobTitle', '')}".lower(),
        posted=_iso(r.get("date")),
        search=search,
        extra={"applications": r.get("applications")},
    )


def fetch(api_key: str, keywords: str, location: str, radius_miles: int,
          max_pages: int = 2, _get=get_json) -> list[Job]:
    jobs: list[Job] = []
    label = f"{keywords} / {location} {radius_miles}mi"
    for page in range(max_pages):
        data = _get(SEARCH_URL, params={
            "keywords": keywords,
            "locationName": location,
            "distanceFromLocation": radius_miles,
            "resultsToTake": PAGE_SIZE,
            "resultsToSkip": page * PAGE_SIZE,
        }, basic_user=api_key)
        results = data.get("results") or []
        jobs.extend(normalise(r, label) for r in results)
        if len(results) < PAGE_SIZE:
            break
    return jobs
