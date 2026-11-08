"""Remote OK: https://remoteok.com/api (latest ~100 jobs, all categories).

One call a day, filtered locally. The first element is their legal notice.
Terms: link back to the Remote OK job URL and credit Remote OK.
Salaries are USD per year.
"""
from __future__ import annotations

from ..eligibility import classify
from ..http import get_json
from ..models import Job
from ..money import DEFAULT_FX, to_gbp
from ..text import strip_html

URL = "https://remoteok.com/api"


def normalise(r: dict, fx: dict | None = None) -> Job:
    loc = (r.get("location") or "").strip()
    desc = strip_html(r.get("description"))
    elig, why = classify(loc, desc, True)
    return Job(
        source="remoteok", source_id=str(r["id"]),
        title=(r.get("position") or "").strip(), company=(r.get("company") or "").strip(),
        location=f"Remote: {loc}" if loc else "Remote", url=r.get("url") or "",
        description=desc,
        salary_min=to_gbp(r.get("salary_min") or None, "USD", fx),
        salary_max=to_gbp(r.get("salary_max") or None, "USD", fx),
        currency="GBP", remote=True, posted=(r.get("date") or "")[:10] or None,
        search="remoteok", eligibility=elig, eligibility_reason=why,
        extra={"tags": r.get("tags") or [], "via": "Remote OK"},
    )


def fetch(fx: dict | None = DEFAULT_FX, _get=get_json) -> list[Job]:
    data = _get(URL)
    return [normalise(r, fx) for r in data if isinstance(r, dict) and r.get("id") and r.get("position")]
