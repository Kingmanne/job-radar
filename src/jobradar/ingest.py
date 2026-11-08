"""Turns a job-alert email (stored in S3 by SES) into job items.

Placeholder so the infrastructure deploys in one go; the per-board parsers
arrive in Phase 6.
"""
import json
import logging
import urllib.parse

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        log.info(json.dumps({"msg": "alert email received", "bucket": bucket, "key": key}))
    return {"status": "ok"}
