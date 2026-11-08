"""Daily run: fetch -> dedupe -> filter -> score -> digest.

Placeholder so the infrastructure deploys in one go. Each step is filled in
during Phases 1 to 5 of the build plan.
"""
import json
import logging
import os

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    log.info(json.dumps({"msg": "job-radar daily run started", "table": os.environ.get("TABLE_NAME")}))
    # Phase 1-2: fetch from Reed, Adzuna, CV-Library, Himalayas, Remotive, Remote OK, HN, watchlist
    # Phase 4:   dedupe in DynamoDB, UK-eligibility filter, score against CV skills
    # Phase 5:   query the pending-by-score index and send the SES digest
    return {"status": "ok", "jobs_new": 0}
