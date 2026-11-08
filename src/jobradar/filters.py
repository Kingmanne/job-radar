"""Cheap filters applied straight after fetching (scoring comes later)."""
from __future__ import annotations

from .models import Job

# A title must mention at least one of these to be relevant.
TITLE_WORDS = ["devops", "dev ops", "platform", "sre", "site reliability", "cloud",
               "infrastructure", "aws", "kubernetes", "devsecops", "release engineer"]


# A title containing any of these is a different job family, even if it says "cloud" or "platform".
TITLE_EXCLUDE = ["power platform", "data engineer", "full stack", "fullstack", "frontend",
                 "front end", "developer", "data scientist", "sales", "recruiter", "1st line",
                 "2nd line", "helpdesk", "service desk"]


def is_relevant(job: Job, exclude_words: list[str], exclude_titles: list[str] | None = None) -> bool:
    title = job.title.lower()
    text = f"{title} {job.description.lower()}"
    if any(w.lower() in text for w in exclude_words):
        return False
    if any(w.lower() in title for w in (TITLE_EXCLUDE if exclude_titles is None else exclude_titles)):
        return False
    return any(w in title for w in TITLE_WORDS)


def meets_pay(job: Job, min_salary: float, min_day_rate: float) -> bool:
    """Unknown pay passes (many good ads hide salary); known low pay doesn't."""
    best = job.salary_max or job.salary_min
    if best is None:
        return True
    floor = min_day_rate if job.salary_period == "day" else min_salary
    return best >= floor
