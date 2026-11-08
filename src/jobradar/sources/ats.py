"""Company careers feeds (public, official job-board APIs).

watch_companies entries look like "greenhouse:monzo", "lever:acme",
"lever-eu:acme", "ashby:synthesia", optionally with a display name:
"greenhouse:monzo:Monzo". The slug is the bit in the company's job-board URL,
e.g. boards.greenhouse.io/monzo, jobs.lever.co/acme, jobs.ashbyhq.com/synthesia.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..eligibility import classify
from ..http import get_json
from ..models import Job
from ..money import DEFAULT_FX, normalise_period, to_gbp
from ..text import strip_html

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}",
    "lever-eu": "https://api.eu.lever.co/v0/postings/{slug}",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


def parse_entry(entry) -> tuple[str, str, str]:
    if isinstance(entry, dict):
        ats, slug, name = entry["ats"], entry["slug"], entry.get("name")
    else:
        bits = str(entry).split(":", 2)
        if len(bits) < 2:
            raise ValueError(f"watch_companies entry {entry!r} should look like 'greenhouse:monzo'")
        ats, slug, name = bits[0], bits[1], (bits[2] if len(bits) > 2 else None)
    ats = ats.strip().lower()
    if ats not in URLS:
        raise ValueError(f"unknown ATS {ats!r} (use {', '.join(URLS)})")
    return ats, slug.strip(), (name or slug.replace("-", " ").title()).strip()


def _job(ats, slug, company, jid, title, location, url, desc, remote, posted, lo=None, hi=None,
         cur=None, interval=None, fx=None) -> Job:
    elig, why = classify(location, desc, remote)
    lo, kind = normalise_period(lo, interval)
    hi, _ = normalise_period(hi, interval)
    return Job(
        source=ats.split("-")[0], source_id=f"{slug}:{jid}", title=(title or "").strip(), company=company,
        location=location or ("Remote" if remote else ""), url=url or "", description=desc,
        salary_min=to_gbp(lo, cur, fx), salary_max=to_gbp(hi, cur, fx), salary_period=kind,
        remote=remote, posted=posted, search=f"company: {company}", eligibility=elig, eligibility_reason=why,
        extra={"via": f"{company} careers"},
    )


def _greenhouse(data, slug, company, fx):
    for r in data.get("jobs") or []:
        loc = (r.get("location") or {}).get("name") or ""
        yield _job("greenhouse", slug, company, r["id"], r.get("title"), loc, r.get("absolute_url"),
                   strip_html(r.get("content")), "remote" in loc.lower(),
                   (r.get("first_published") or r.get("updated_at") or "")[:10] or None, fx=fx)


def _lever(data, slug, company, fx, ats="lever"):
    for r in data if isinstance(data, list) else []:
        cats = r.get("categories") or {}
        loc = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        created = r.get("createdAt")
        sal = r.get("salaryRange") or {}
        interval = {"per-year-salary": "year", "per-month-salary": "month", "per-day-wage": "day",
                    "per-hour-wage": "hour"}.get(sal.get("interval"), "year")
        yield _job(ats, slug, company, r["id"], r.get("text"), loc, r.get("hostedUrl"),
                   (r.get("descriptionPlain") or "")[:6000],
                   r.get("workplaceType") == "remote" or "remote" in loc.lower(),
                   datetime.fromtimestamp(created / 1000, timezone.utc).date().isoformat() if created else None,
                   sal.get("min"), sal.get("max"), sal.get("currency"), interval, fx)


def _ashby(data, slug, company, fx):
    for r in data.get("jobs") or []:
        if r.get("isListed") is False:
            continue
        locs = [r.get("location") or ""] + [s.get("location", "") for s in r.get("secondaryLocations") or []]
        loc = ", ".join(l for l in locs if l)
        lo = hi = cur = None
        interval = "year"
        for comp in ((r.get("compensation") or {}).get("summaryComponents") or []):
            if comp.get("compensationType") == "Salary":
                lo, hi, cur = comp.get("minValue"), comp.get("maxValue"), comp.get("currencyCode")
                interval = {"1 YEAR": "year", "1 MONTH": "month", "1 DAY": "day", "1 HOUR": "hour"}.get(
                    comp.get("interval"), "year")
                break
        yield _job("ashby", slug, company, r["id"], r.get("title"), loc, r.get("jobUrl"),
                   (r.get("descriptionPlain") or "")[:6000], bool(r.get("isRemote")),
                   (r.get("publishedAt") or "")[:10] or None, lo, hi, cur, interval, fx)


def fetch(entry, fx: dict | None = DEFAULT_FX, _get=get_json) -> list[Job]:
    ats, slug, company = parse_entry(entry)
    url = URLS[ats].format(slug=slug)
    if ats == "greenhouse":
        return list(_greenhouse(_get(url, params={"content": "true"}), slug, company, fx))
    if ats.startswith("lever"):
        return list(_lever(_get(url, params={"mode": "json"}), slug, company, fx, ats))
    return list(_ashby(_get(url, params={"includeCompensation": "true"}), slug, company, fx))
