"""Settings and secrets.

Locally: environment variables win (REED_API_KEY, ADZUNA_APP_ID, ...).
In Lambda: values come from SSM Parameter Store under PARAM_PREFIX.
A value still set to the Terraform placeholder CHANGE_ME counts as missing,
so that source is simply skipped.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

PLACEHOLDER = "CHANGE_ME"
PREFIX = os.environ.get("PARAM_PREFIX", "/job-radar")

DEFAULT_SEARCHES = {
    "keywords": ["DevOps Engineer", "Platform Engineer", "Site Reliability Engineer", "Cloud Engineer", "AWS Engineer"],
    "exclude_words": ["trainee", "no experience", "career change", "graduate scheme"],
    "locations": [
        {"name": "Manchester", "radius_miles": 40},
        {"name": "London", "radius_miles": 25},
        {"name": "Birmingham", "radius_miles": 25},
    ],
    "include_remote": True,
    "min_salary": 45000,
    "min_day_rate": 400,
    "watch_companies": [],
    "adzuna_enabled": False,
}


@lru_cache(maxsize=None)
def _ssm():
    import boto3  # available in Lambda; locally only needed without env vars
    return boto3.client("ssm")


def _from_ssm(name: str, decrypt: bool) -> str | None:
    try:
        return _ssm().get_parameter(Name=f"{PREFIX}/{name}", WithDecryption=decrypt)["Parameter"]["Value"]
    except Exception:
        return None


def secret(name: str) -> str | None:
    """API key by parameter name, e.g. 'reed_api_key'. None if unset or placeholder."""
    value = os.environ.get(name.upper())
    if value is None and not os.environ.get("JOBRADAR_LOCAL_ONLY"):
        value = _from_ssm(name, decrypt=True)
    if not value or value.strip() == PLACEHOLDER:
        return None
    return value.strip()


def searches() -> dict:
    raw = os.environ.get("JOBRADAR_SEARCHES")
    if raw is None and not os.environ.get("JOBRADAR_LOCAL_ONLY"):
        raw = _from_ssm("searches", decrypt=False)
    merged = dict(DEFAULT_SEARCHES)
    if raw:
        merged.update(json.loads(raw))
    return merged
