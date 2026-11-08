"""Adzuna API: https://developer.adzuna.com

Auth: app_id + app_key query parameters. Distances are in km.
Paid plan needed beyond 25 test calls, so it is off unless
searches['adzuna_enabled'] is true AND both keys are set.
"""
from __future__ import annotations

from ..http import get_json
from ..models import Job

SEARCH_URL = "https://api.adzuna.com/v1/api/jobs/gb/search/{page}"
MILES_TO_KM = 1.609


def credentials_look_valid(app_id: str, app_key: str) -> bool:
    """App ID is 8 characters, key is 32: catches the two being swapped."""
    return len(app_id) == 8 and len(app_key) == 32


def normalise(r: dict, search: str = "") -> Job:
    title = (r.get("title") or "").strip()
    location = (r.get("location") or {}).get("display_name") or ""
    return Job(
        source="adzuna",
        source_id=str(r["id"]),
        title=title,
        company=((r.get("company") or {}).get("display_name") or "").strip(),
        location=location,
        url=r.get("redirect_url") or "",
        description=(r.get("description") or "").strip(),
        salary_min=r.get("salary_min"),
        salary_max=r.get("salary_max"),
        salary_period="year",
        remote="remote" in f"{location} {title}".lower(),
        posted=(r.get("created") or "")[:10] or None,
        search=search,
        extra={"contract_type": r.get("contract_type"), "contract_time": r.get("contract_time")},
    )


def fetch(app_id: str, app_key: str, keywords: str, location: str, radius_miles: int,
          max_days_old: int = 3, _get=get_json) -> tuple[list[Job], float | None]:
    """One call per search. Returns the jobs and Adzuna's mean salary for the search."""
    data = _get(SEARCH_URL.format(page=1), params={
        "app_id": app_id,
        "app_key": app_key,
        "what": keywords,
        "where": location,
        "distance": round(radius_miles * MILES_TO_KM),
        "max_days_old": max_days_old,
        "results_per_page": 50,
        "content-type": "application/json",
    })
    label = f"{keywords} / {location} {radius_miles}mi"
    return [normalise(r, label) for r in data.get("results") or []], data.get("mean")
