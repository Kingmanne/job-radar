"""Daily run: fetch -> (dedupe -> score -> digest arrive in Phases 4-5)."""
import json
import logging

from .fetch import fetch_all, summary

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    jobs, stats = fetch_all()
    result = {"msg": "job-radar daily run", **summary(jobs, stats)}
    log.info(json.dumps(result))
    return result
