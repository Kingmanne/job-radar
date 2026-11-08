"""Run every enabled source, then apply the cheap filters.

Local dry run (no AWS needed if the keys are in env vars):
    PYTHONPATH=src python -m jobradar.fetch --dry-run
    PYTHONPATH=src python -m jobradar.fetch --dry-run --only himalayas,remotive
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import Counter

from . import settings
from .filters import is_relevant, meets_pay
from .http import SourceError
from .models import Job
from .money import DEFAULT_FX
from .sources import adzuna, ats, himalayas, hn, reed, remoteok, remotive

log = logging.getLogger(__name__)
ALL_SOURCES = ("reed", "adzuna", "himalayas", "remotive", "remoteok", "hn", "companies")


def _batches(cfg: dict, stats: dict, only: set[str]):
    """Yield (source, jobs) per call. A failing call is logged and skipped."""
    fx = {**DEFAULT_FX, **(cfg.get("fx_to_gbp") or {})}
    remote = cfg.get("remote_sources") or {}

    def run(source: str, label: str, fn):
        try:
            return source, fn()
        except (SourceError, ValueError, KeyError, TypeError) as e:
            stats["errors"].append(f"{label}: {e}")
            return source, []

    # UK boards
    reed_key = settings.secret("reed_api_key") if "reed" in only else None
    adz_id, adz_key = (settings.secret("adzuna_app_id"), settings.secret("adzuna_app_key")) if "adzuna" in only else (None, None)
    use_adzuna = bool(cfg.get("adzuna_enabled") and adz_id and adz_key)
    if use_adzuna and not adzuna.credentials_look_valid(adz_id, adz_key):
        stats["errors"].append("adzuna: credentials look wrong (App ID should be 8 chars, key 32)")
        use_adzuna = False
    if "reed" in only and not reed_key:
        stats["skipped_sources"].append("reed (no key)")
    if "adzuna" in only and not use_adzuna:
        stats["skipped_sources"].append("adzuna (disabled or no key)")

    for loc in cfg["locations"]:
        for kw in cfg["keywords"]:
            if reed_key:
                yield run("reed", f"reed {kw}/{loc['name']}",
                          lambda: reed.fetch(reed_key, kw, loc["name"], loc["radius_miles"]))
            if use_adzuna:
                def adz():
                    jobs, mean = adzuna.fetch(adz_id, adz_key, kw, loc["name"], loc["radius_miles"])
                    if mean:
                        stats["market_mean"][f"{kw} / {loc['name']}"] = round(mean)
                    return jobs
                yield run("adzuna", f"adzuna {kw}/{loc['name']}", adz)

    # Remote boards
    if cfg.get("include_remote", True):
        if remote.get("himalayas", True) and "himalayas" in only:
            for q in cfg.get("himalayas_queries") or []:
                yield run("himalayas", f"himalayas {q}", lambda: himalayas.fetch(q, fx=fx))
        if remote.get("remotive", True) and "remotive" in only:
            yield run("remotive", "remotive", lambda: remotive.fetch(cfg.get("remotive_category"), fx=fx))
        if remote.get("remoteok", True) and "remoteok" in only:
            yield run("remoteok", "remoteok", lambda: remoteok.fetch(fx=fx))
        if remote.get("hn", True) and "hn" in only:
            yield run("hn", "hn", hn.fetch)

    # Company careers pages
    if "companies" in only:
        for entry in cfg.get("watch_companies") or []:
            yield run("companies", f"company {entry}", lambda: ats.fetch(entry, fx=fx))


def fetch_all(cfg: dict | None = None, only: set[str] | None = None,
              keep_dropped: bool = False) -> tuple[list[Job], dict]:
    cfg = cfg or settings.searches()
    only = set(only or ALL_SOURCES)
    stats: dict = {"raw": Counter(), "kept": Counter(), "eligibility": Counter(), "dropped": Counter(),
                   "errors": [], "skipped_sources": [], "market_mean": {}, "dropped_jobs": []}
    found: dict[str, Job] = {}
    seen: set[str] = set()          # every pk looked at, kept or not

    for source, jobs in _batches(cfg, stats, only):
        stats["raw"][source] += len(jobs)
        for job in jobs:
            if job.pk in seen:
                stats["dropped"]["duplicate"] += 1
                continue
            seen.add(job.pk)
            if not is_relevant(job, cfg["exclude_words"], cfg.get("exclude_titles")):
                reason = "not relevant"
            elif job.eligibility == "not_eligible":
                reason = "not open to UK"
            elif not meets_pay(job, cfg["min_salary"], cfg["min_day_rate"]):
                reason = "pay too low"
            else:
                found[job.pk] = job
                stats["kept"][source] += 1
                stats["eligibility"][job.eligibility] += 1
                continue
            stats["dropped"][reason] += 1
            if keep_dropped and reason != "not relevant":     # irrelevant ones are just noise
                stats["dropped_jobs"].append((reason, job))

    return list(found.values()), stats


def summary(jobs: list[Job], stats: dict) -> dict:
    return {
        "total_kept": len(jobs),
        "raw_by_source": dict(stats["raw"]), "kept_by_source": dict(stats["kept"]),
        "eligibility": dict(stats["eligibility"]), "dropped": dict(stats["dropped"]),
        "skipped_sources": stats["skipped_sources"], "errors": stats["errors"],
        "market_mean": stats["market_mean"],
    }


def _print_table(jobs: list[Job], limit: int) -> None:
    def pay(j: Job) -> str:
        v = j.salary_max or j.salary_min
        if not v:
            return "n/a"
        return f"£{v:,.0f}/day" if j.salary_period == "day" else f"£{v/1000:.0f}k"
    mark = {"eligible": " ", "unclear": "?", "not_eligible": "x"}
    for j in sorted(jobs, key=lambda j: j.posted or "", reverse=True)[:limit]:
        print(f"{j.source:9} {mark[j.eligibility]} {j.posted or '':10} {pay(j):>9}  {j.title[:44]:44}  "
              f"{j.company[:24]:24}  {j.location[:28]}")


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch jobs from all enabled sources.")
    p.add_argument("--dry-run", action="store_true", help="print results, write nothing")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--only", help=f"comma-separated subset of: {', '.join(ALL_SOURCES)}")
    p.add_argument("--source", help="only print jobs from this source in the table")
    p.add_argument("--show-dropped", action="store_true",
                   help="also list jobs dropped for eligibility or pay, with the reason")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    only = set(args.only.split(",")) if args.only else None
    jobs, stats = fetch_all(only=only, keep_dropped=args.show_dropped)
    shown = [j for j in jobs if not args.source or j.source == args.source]
    _print_table(shown, args.limit)
    if args.show_dropped:
        print("\nDropped:")
        for reason, j in stats["dropped_jobs"]:
            if not args.source or j.source == args.source:
                print(f"  {j.source:9} {reason:15} {j.title[:40]:40}  {j.company[:20]:20}  "
                      f"{j.location[:24]:24}  {j.eligibility_reason[:50]}")
    print("\n(? = check the ad: remote region may not include the UK)\n")
    print(json.dumps(summary(jobs, stats), indent=2))


if __name__ == "__main__":
    main()
