"""Daily run: fetch -> (dedupe -> score -> digest arrive in Phases 4-5)."""
import json
import logging

from .fetch import fetch_all

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    jobs, stats = fetch_all()
    summary = {
        "msg": "job-radar daily run",
        "total_kept": len(jobs),
        "raw_by_source": dict(stats["raw"]),
        "kept_by_source": dict(stats["kept"]),
        "skipped_sources": stats["skipped_sources"],
        "errors": stats["errors"],
    }
    log.info(json.dumps(summary))
    return summary
