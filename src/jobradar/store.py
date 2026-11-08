"""DynamoDB storage: remember every job so each one is "new" only once.

Items in the jobs table:
  pk="reed#123"   the job itself. New jobs get digest_pending="1", which
                  puts them in the sparse GSI "pending-by-score" for Phase 5.
  pk="fp#ab12.."  fingerprint marker (company + title) pointing at the first
                  job seen with it, so the same ad on another board, or a
                  repost under a new id, is recognised as a duplicate.
Both expire (TTL) job_ttl_days after they were last seen.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal

from .models import Job

PENDING = "1"
INDEX = "pending-by-score"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _num(v):
    return None if v is None else Decimal(str(round(v, 2)))


def to_item(job: Job, score: int, reasons: list[str], ttl_days: int) -> dict:
    now = _now()
    item = {
        "pk": job.pk, "source": job.source, "source_id": job.source_id,
        "title": job.title, "company": job.company, "location": job.location, "url": job.url,
        "description": job.description[:1500], "salary_period": job.salary_period, "currency": job.currency,
        "remote": job.remote, "posted": job.posted, "search": job.search,
        "eligibility": job.eligibility, "eligibility_reason": job.eligibility_reason,
        "fingerprint": job.fingerprint, "score": score, "score_reasons": reasons,
        "salary_min": _num(job.salary_min), "salary_max": _num(job.salary_max),
        "extra": json.dumps(job.extra, default=str)[:2000],
        "first_seen": now, "last_seen": now,
        "expires_at": int(time.time()) + ttl_days * 86400,
        "digest_pending": PENDING,
    }
    return {k: v for k, v in item.items() if v is not None and v != ""}


class DynamoBackend:
    def __init__(self, table_name: str | None = None):
        import boto3
        self.resource = boto3.resource("dynamodb")
        self.table = self.resource.Table(table_name or os.environ["TABLE_NAME"])

    def get_many(self, pks: list[str]) -> dict[str, dict]:
        found: dict[str, dict] = {}
        name = self.table.name
        for i in range(0, len(pks), 100):
            keys = [{"pk": pk} for pk in pks[i:i + 100]]
            request = {name: {"Keys": keys, "ProjectionExpression": "pk, job_pk"}}
            for _ in range(5):                       # retry unprocessed keys
                resp = self.resource.batch_get_item(RequestItems=request)
                for item in resp["Responses"].get(name, []):
                    found[item["pk"]] = item
                request = resp.get("UnprocessedKeys") or {}
                if not request:
                    break
                time.sleep(0.5)
        return found

    def put_many(self, items: list[dict]) -> None:
        with self.table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

    def touch(self, pk: str, ttl_days: int) -> None:
        self.table.update_item(
            Key={"pk": pk},
            UpdateExpression="SET last_seen = :now, expires_at = :exp",
            ExpressionAttributeValues={":now": _now(), ":exp": int(time.time()) + ttl_days * 86400},
        )

    def list_pending(self) -> list[dict]:
        from boto3.dynamodb.conditions import Key
        items, kwargs = [], {"IndexName": INDEX, "ScanIndexForward": False,
                             "KeyConditionExpression": Key("digest_pending").eq(PENDING)}
        while True:
            resp = self.table.query(**kwargs)
            items.extend(resp["Items"])
            if "LastEvaluatedKey" not in resp:
                return items
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def mark_sent(self, pks: list[str]) -> None:
        for pk in pks:
            self.table.update_item(Key={"pk": pk}, UpdateExpression="REMOVE digest_pending SET emailed_at = :t",
                                   ExpressionAttributeValues={":t": _now()})

    def count_pending(self) -> int:
        from boto3.dynamodb.conditions import Key
        resp = self.table.query(IndexName=INDEX, KeyConditionExpression=Key("digest_pending").eq(PENDING),
                                Select="COUNT")
        return resp["Count"]


class MemoryBackend:
    """Same interface, kept in a dict. Used by tests."""
    def __init__(self):
        self.items: dict[str, dict] = {}

    def get_many(self, pks):
        return {pk: self.items[pk] for pk in pks if pk in self.items}

    def put_many(self, items):
        for item in items:
            self.items[item["pk"]] = dict(item)

    def touch(self, pk, ttl_days):
        self.items[pk]["last_seen"] = _now()

    def count_pending(self):
        return sum(1 for i in self.items.values() if i.get("digest_pending") == PENDING)

    def list_pending(self):
        items = [i for i in self.items.values() if i.get("digest_pending") == PENDING]
        return sorted(items, key=lambda i: i["score"], reverse=True)

    def mark_sent(self, pks):
        for pk in pks:
            self.items[pk].pop("digest_pending", None)
            self.items[pk]["emailed_at"] = _now()


def save(scored: list[tuple[Job, int, list[str]]], backend, ttl_days: int = 30,
         dry_run: bool = False) -> dict:
    """Store new jobs, refresh known ones, skip cross-board duplicates.

    `scored` is [(job, score, reasons)]. Returns counts plus the new jobs
    (highest score first) so the caller can log or email them.
    """
    scored = sorted(scored, key=lambda t: t[1], reverse=True)
    pks = [j.pk for j, _, _ in scored]
    fps = sorted({f"fp#{j.fingerprint}" for j, _, _ in scored})
    existing = backend.get_many(pks + fps)

    new_items, fp_items, new_jobs, known, dupes = [], {}, [], [], []
    claimed: dict[str, str] = {k: v.get("job_pk", "") for k, v in existing.items() if k.startswith("fp#")}
    expires = int(time.time()) + ttl_days * 86400

    for job, sc, reasons in scored:
        fp = f"fp#{job.fingerprint}"
        if job.pk in existing:
            known.append(job.pk)
            if claimed.get(fp) in (None, "", job.pk):
                fp_items[fp] = {"pk": fp, "job_pk": job.pk, "expires_at": expires}
            continue
        owner = claimed.get(fp)
        if owner and owner != job.pk:
            dupes.append((job.pk, owner))
            continue
        claimed[fp] = job.pk
        fp_items[fp] = {"pk": fp, "job_pk": job.pk, "expires_at": expires}
        new_items.append(to_item(job, sc, reasons, ttl_days))
        new_jobs.append((job, sc, reasons))

    if not dry_run:
        backend.put_many(new_items + list(fp_items.values()))
        for pk in known:
            backend.touch(pk, ttl_days)

    return {"new": len(new_jobs), "already_seen": len(known), "cross_board_duplicates": len(dupes),
            "new_jobs": new_jobs, "duplicate_pairs": dupes}
