"""Daily run: fetch -> score -> save new jobs to DynamoDB (digest email arrives in Phase 5).

Local preview against the real table, writing nothing:
    TABLE_NAME=job-radar-jobs PYTHONPATH=src python -m jobradar.daily --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os

from . import settings
from .fetch import fetch_all, summary
from .scoring import score
from .sources import reed
from .store import DynamoBackend, save

log = logging.getLogger()
log.setLevel(logging.INFO)


def run(dry_run: bool = False, backend=None) -> tuple[dict, list]:
    jobs, stats = fetch_all()
    backend = backend or DynamoBackend()

    # Full ads for Reed jobs we haven't seen before (search only gives a snippet).
    known = backend.get_many([j.pk for j in jobs])
    new_reed = [j for j in jobs if j.source == "reed" and j.pk not in known]
    enriched = 0
    reed_key = settings.secret("reed_api_key") if new_reed else None
    if reed_key:
        enriched = reed.enrich(new_reed, reed_key)

    scored = [(j, *score(j)) for j in jobs]
    saved = save(scored, backend, ttl_days=int(os.environ.get("JOB_TTL_DAYS", "30")), dry_run=dry_run)
    result = {
        "msg": "job-radar daily run", "dry_run": dry_run, **summary(jobs, stats),
        "reed_details_fetched": enriched,
        "new": saved["new"], "already_seen": saved["already_seen"],
        "cross_board_duplicates": saved["cross_board_duplicates"],
        "pending_for_digest": None if dry_run else backend.count_pending(),
        "top_new": [f"{sc:3d}  {j.title[:50]} | {j.company[:25]} | {j.location[:25]}"
                    for j, sc, _ in saved["new_jobs"][:10]],
    }
    return result, saved["new_jobs"]


def handler(event, context):
    result, _ = run(dry_run=bool((event or {}).get("dry_run")))
    log.info(json.dumps(result))
    return result


def main() -> None:
    p = argparse.ArgumentParser(description="Run the daily pipeline locally.")
    p.add_argument("--dry-run", action="store_true", help="read DynamoDB but write nothing")
    p.add_argument("--limit", type=int, default=30)
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    os.environ.setdefault("TABLE_NAME", "job-radar-jobs")

    result, new_jobs = run(dry_run=args.dry_run)
    print(f"{'score':>5}  {'title':46}  {'company':24}  {'location':24}  why")
    for job, sc, reasons in new_jobs[:args.limit]:
        flag = "?" if job.eligibility == "unclear" else " "
        print(f"{sc:5d}{flag} {job.title[:46]:46}  {job.company[:24]:24}  {job.location[:24]:24}  "
              f"{'; '.join(reasons)[:70]}")
    result.pop("top_new")
    print("\n" + json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
