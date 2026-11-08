"""Run every enabled source for every saved search, then apply the cheap filters.

Local dry run (no AWS needed if the keys are in env vars):
    PYTHONPATH=src python -m jobradar.fetch --dry-run
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
from .sources import adzuna, reed

log = logging.getLogger(__name__)


def fetch_all(cfg: dict | None = None) -> tuple[list[Job], dict]:
    cfg = cfg or settings.searches()
    stats: dict = {"raw": Counter(), "kept": Counter(), "errors": [], "skipped_sources": [], "market_mean": {}}
    found: dict[str, Job] = {}

    reed_key = settings.secret("reed_api_key")
    adz_id, adz_key = settings.secret("adzuna_app_id"), settings.secret("adzuna_app_key")
    use_adzuna = bool(cfg.get("adzuna_enabled") and adz_id and adz_key)
    if use_adzuna and not adzuna.credentials_look_valid(adz_id, adz_key):
        stats["errors"].append("adzuna: credentials look wrong (App ID should be 8 chars, key 32)")
        use_adzuna = False
    if not reed_key:
        stats["skipped_sources"].append("reed (no key)")
    if not use_adzuna:
        stats["skipped_sources"].append("adzuna (disabled or no key)")

    for loc in cfg["locations"]:
        for kw in cfg["keywords"]:
            batches: list[tuple[str, list[Job]]] = []
            if reed_key:
                try:
                    batches.append(("reed", reed.fetch(reed_key, kw, loc["name"], loc["radius_miles"])))
                except SourceError as e:
                    stats["errors"].append(f"reed {kw}/{loc['name']}: {e}")
            if use_adzuna:
                try:
                    jobs, mean = adzuna.fetch(adz_id, adz_key, kw, loc["name"], loc["radius_miles"])
                    batches.append(("adzuna", jobs))
                    if mean:
                        stats["market_mean"][f"{kw} / {loc['name']}"] = round(mean)
                except SourceError as e:
                    stats["errors"].append(f"adzuna {kw}/{loc['name']}: {e}")

            for source, jobs in batches:
                stats["raw"][source] += len(jobs)
                for job in jobs:
                    if job.pk in found:
                        continue  # same job matched two searches
                    if not is_relevant(job, cfg["exclude_words"], cfg.get("exclude_titles")):
                        continue
                    if not meets_pay(job, cfg["min_salary"], cfg["min_day_rate"]):
                        continue
                    found[job.pk] = job
                    stats["kept"][source] += 1

    return list(found.values()), stats


def _print_table(jobs: list[Job], limit: int) -> None:
    def pay(j: Job) -> str:
        v = j.salary_max or j.salary_min
        if not v:
            return "n/a"
        return f"£{v:,.0f}/day" if j.salary_period == "day" else f"£{v/1000:.0f}k"
    for j in sorted(jobs, key=lambda j: j.posted or "", reverse=True)[:limit]:
        print(f"{j.source:7} {j.posted or '':10}  {pay(j):>10}  {j.title[:48]:48}  {j.company[:28]:28}  {j.location[:20]}")


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch jobs from all enabled sources.")
    p.add_argument("--dry-run", action="store_true", help="print results, write nothing")
    p.add_argument("--limit", type=int, default=40)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    jobs, stats = fetch_all()
    _print_table(jobs, args.limit)
    print("\n" + json.dumps({
        "raw_by_source": stats["raw"], "kept_by_source": stats["kept"],
        "skipped_sources": stats["skipped_sources"], "errors": stats["errors"],
        "market_mean": stats["market_mean"], "total_kept": len(jobs),
    }, indent=2, default=dict))


if __name__ == "__main__":
    main()
