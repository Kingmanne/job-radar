"""One common shape for a job, whichever board it came from."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field


@dataclass
class Job:
    source: str              # "reed", "adzuna", ...
    source_id: str           # the board's own id
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_period: str = "year"   # "year" or "day"
    currency: str = "GBP"
    remote: bool = False
    posted: str | None = None     # ISO date, YYYY-MM-DD
    search: str = ""              # which saved search found it
    eligibility: str = "eligible"  # UK applicants: "eligible", "unclear" or "not_eligible"
    eligibility_reason: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def pk(self) -> str:
        """DynamoDB key: unique per board."""
        return f"{self.source}#{self.source_id}"

    @property
    def fingerprint(self) -> str:
        """Same job posted on several boards gets the same fingerprint."""
        norm = lambda s: " ".join("".join(c.lower() if c.isalnum() else " " for c in s).split())
        return hashlib.sha1(f"{norm(self.company)}|{norm(self.title)}".encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pk"] = self.pk
        d["fingerprint"] = self.fingerprint
        return d
