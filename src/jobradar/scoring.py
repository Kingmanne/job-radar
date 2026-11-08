"""Score a job 0-100 against Mustapha's CV and search preferences.

Parts (max points):
  title      30  how close the job title is to the target roles
  skills     35  CV skills found in the title + description (AWS, EKS, Terraform, ...)
  location   15  Manchester area or UK-remote best, London/Birmingham next
  pay        10  known pay vs targets (unknown pay gets a middle score)
  seniority  10  mid-level and senior fit best; junior lower; lead/principal/staff low
Penalties: needs SC/DV clearance, Windows/VMware-centred, Azure/GCP-only, stale ad.

Every rule that fires adds a short reason, shown in the digest as "why".
Weights live here so they're easy to tune; edit and redeploy.
"""
from __future__ import annotations

import re
from datetime import date

from .models import Job

TITLE_POINTS = [  # first match wins, so most specific first
    (r"\bdevsecops\b", 26, "DevSecOps title"),
    (r"\bdev ?ops\b", 30, "DevOps title"),
    (r"\bplatform engineer", 30, "Platform Engineer title"),
    (r"\bsite reliability\b|\bsre\b", 28, "SRE title"),
    (r"\baws\b", 27, "AWS in title"),
    (r"\bcloud (platform |infrastructure |devops )?engineer", 27, "Cloud Engineer title"),
    (r"\bkubernetes\b", 25, "Kubernetes in title"),
    (r"\bplatform\b", 18, "platform role"),
    (r"\binfrastructure engineer", 15, "Infrastructure Engineer title"),
    (r"\bcloud\b", 14, "cloud role"),
    (r"\barchitect\b", 10, "architect role"),
]

# (pattern, points, label). Matched once each across title + description.
SKILLS = [
    (r"\baws\b|amazon web services", 6, "AWS"),
    (r"\beks\b|\bkubernetes\b|\bk8s\b", 6, "Kubernetes/EKS"),
    (r"\bterraform\b", 6, "Terraform"),
    (r"\bargo ?cd\b|\bgitops\b|\bflux\b", 4, "Argo CD/GitOps"),
    (r"github actions", 4, "GitHub Actions"),
    (r"\bhelm\b", 3, "Helm"),
    (r"\bprometheus\b|\bgrafana\b", 3, "Prometheus/Grafana"),
    (r"\bdocker\b|\bcontainers?\b", 3, "Docker"),
    (r"\bpython\b", 3, "Python"),
    (r"ci/cd|\bcicd\b|continuous (integration|delivery|deployment)|\bpipelines?\b", 3, "CI/CD"),
    (r"\blambda\b|\bserverless\b", 2, "Lambda/serverless"),
    (r"codebuild|codepipeline|codedeploy", 2, "AWS CodeSuite"),
    (r"\bx-ray\b|\bxray\b|cloudwatch|observability", 2, "observability"),
    (r"\bwaf\b|transit gateway|direct connect|\bvpc\b", 2, "AWS networking"),
    (r"\blinux\b|\bbash\b", 2, "Linux/Bash"),
]
SKILLS_MAX = 35

MANCHESTER = re.compile(r"\b(manchester|salford|stockport|trafford|oldham|bolton|bury|rochdale|wigan|tameside|"
                        r"warrington|birchwood|altrincham|wilmslow|macclesfield|cheshire|lancashire|"
                        r"knutsford|runcorn|ashton|preston|liverpool)\b|^(m|ol|sk|wa|bl|wn)\d", re.I)
LONDON = re.compile(r"\blondon\b|^(e|ec|n|nw|se|sw|w|wc)\d", re.I)
BIRMINGHAM = re.compile(r"\bbirmingham\b|\bsolihull\b|\bcoventry\b|^b\d", re.I)

CLEARANCE = re.compile(r"\b(sc|dv)[- ]?(clear(ed|ance)|security clearance)\b|\bactive (sc|dv)\b|"
                       r"\bcurrent (sc|dv)\b|\b(sc|dv) cleared\b|\bnppv\b|\bctc clearance\b", re.I)
WINDOWS = re.compile(r"\b(windows server|active directory|vmware|vsphere|citrix|intune|sccm|hyper-v|"
                     r"exchange online|office 365|m365)\b", re.I)
AZURE = re.compile(r"\bazure\b", re.I)
GCP = re.compile(r"\bgcp\b|google cloud", re.I)
AWS = re.compile(r"\baws\b|amazon web services", re.I)

LEAD = re.compile(r"\b(lead|principal|staff|head of|director|manager|vp)\b", re.I)
SENIOR = re.compile(r"\b(senior|sr\.?|snr)\b", re.I)
JUNIOR = re.compile(r"\b(junior|jnr|graduate|entry[- ]level|associate)\b", re.I)


def score(job: Job, today: date | None = None) -> tuple[int, list[str]]:
    title = job.title
    text = f"{job.title}\n{job.description}"
    reasons: list[str] = []
    total = 0

    # Title
    for pattern, pts, label in TITLE_POINTS:
        if re.search(pattern, title, re.I):
            total += pts
            reasons.append(label)
            break

    # Skills
    found = [(pts, label) for pattern, pts, label in SKILLS if re.search(pattern, text, re.I)]
    total += min(SKILLS_MAX, sum(p for p, _ in found))
    if found:
        reasons.append("skills: " + ", ".join(label for _, label in found[:6]))

    # Location
    loc = job.location or ""
    if job.remote and job.eligibility == "eligible":
        pts, why = 15, "remote, open to UK"
    elif MANCHESTER.search(loc):
        pts, why = 15, "Manchester area"
    elif job.remote:
        pts, why = 6, "remote, check UK eligibility"
    elif LONDON.search(loc):
        pts, why = 8, "London"
    elif BIRMINGHAM.search(loc):
        pts, why = 8, "Birmingham"
    else:
        pts, why = 5, f"UK: {loc[:30]}" if loc else "location unknown"
    total += pts
    reasons.append(why)

    # Pay
    best = job.salary_max or job.salary_min
    if best is None:
        total += 5
    else:
        day = job.salary_period == "day"
        if best >= (500 if day else 65000):
            total += 10
            reasons.append("pays well")
        elif best >= (450 if day else 55000):
            total += 7
        else:
            total += 4

    # Seniority (target: mid-level and senior)
    if LEAD.search(title):
        total += 3
        reasons.append("lead/principal level")
    elif JUNIOR.search(title):
        total += 5
        reasons.append("junior level")
    else:
        total += 10                # mid-level or senior

    # Penalties
    if CLEARANCE.search(text):
        total -= 25
        reasons.append("needs SC/DV clearance")
    if len(WINDOWS.findall(text)) >= 2:
        total -= 10
        reasons.append("Windows/VMware-centred")
    if not AWS.search(text):
        if AZURE.search(text):
            total -= 6
            reasons.append("Azure, no AWS")
        elif GCP.search(text):
            total -= 4
            reasons.append("GCP, no AWS")
    if job.posted:
        try:
            age = ((today or date.today()) - date.fromisoformat(job.posted)).days
            if age > 21:
                total -= 5
                reasons.append(f"posted {age} days ago")
        except ValueError:
            pass

    return max(0, min(100, total)), reasons
