from datetime import date

from jobradar import daily
from jobradar.models import Job
from jobradar.scoring import score
from jobradar.store import MemoryBackend, save

TODAY = date(2026, 11, 8)


def job(title="DevOps Engineer", company="Acme Ltd", location="Manchester", desc="", source="reed",
        sid="1", remote=False, eligibility="eligible", salary=None, period="year", posted="2026-11-07"):
    return Job(source, sid, title, company, location, f"https://x/{sid}", desc, salary_max=salary,
               salary_period=period, remote=remote, posted=posted, eligibility=eligibility)


CV_DESC = "AWS, EKS, Terraform, Argo CD, GitHub Actions, Helm, Prometheus, Docker, Python, CI/CD pipelines"


def test_strong_match_scores_high():
    sc, why = score(job(desc=CV_DESC, salary=70000), TODAY)
    assert sc >= 90
    assert "DevOps title" in why and "Manchester area" in why


def test_mid_and_senior_score_the_same():
    mid, _ = score(job(desc=CV_DESC), TODAY)
    senior, _ = score(job(title="Senior DevOps Engineer", desc=CV_DESC), TODAY)
    lead, _ = score(job(title="Lead DevOps Engineer", desc=CV_DESC), TODAY)
    junior, _ = score(job(title="Junior DevOps Engineer", desc=CV_DESC), TODAY)
    assert mid == senior > junior > lead


def test_generic_windows_infra_scores_low():
    good, _ = score(job(desc=CV_DESC), TODAY)
    windows, why = score(job(title="Infrastructure Engineer", location="Stoke-on-Trent",
                             desc="Windows Server, Active Directory, VMware vSphere"), TODAY)
    assert windows < 35 < good
    assert "Windows/VMware-centred" in why


def test_clearance_penalty():
    sc, why = score(job(desc=CV_DESC + ". Must hold active SC clearance."), TODAY)
    assert "needs SC/DV clearance" in why and sc <= 75


def test_location_and_remote():
    manc, _ = score(job(location="M40 8HH"), TODAY)
    ldn, _ = score(job(location="London"), TODAY)
    remote_uk, _ = score(job(location="Remote: United Kingdom", remote=True), TODAY)
    remote_unclear, _ = score(job(location="Remote: Europe", remote=True, eligibility="unclear"), TODAY)
    assert manc == remote_uk > ldn > remote_unclear - 3


def test_azure_only_and_stale():
    _, why = score(job(title="Azure DevOps Engineer", desc="Azure, Bicep", posted="2026-10-01"), TODAY)
    assert "Azure, no AWS" in why and any("days ago" in w for w in why)


def test_save_new_then_seen():
    backend = MemoryBackend()
    jobs = [(job(sid="1"), 80, []), (job(title="SRE", sid="2"), 70, [])]
    first = save(jobs, backend)
    assert first["new"] == 2 and backend.count_pending() == 2
    assert backend.items["reed#1"]["digest_pending"] == "1"
    second = save(jobs, backend)
    assert second["new"] == 0 and second["already_seen"] == 2


def test_cross_board_and_repost_duplicates():
    backend = MemoryBackend()
    reed = job(company="Acme Cloud Ltd", sid="1")
    repost = job(company="Acme Cloud Ltd", sid="99")                          # same ad, new Reed id
    adzuna = job(company="ACME Cloud Limited", source="adzuna", sid="555")      # same ad, other board
    result = save([(reed, 80, []), (repost, 80, []), (adzuna, 75, [])], backend)
    assert result["new"] == 1 and result["cross_board_duplicates"] == 2
    tomorrow = save([(job(company="Acme Cloud", source="himalayas", sid="h1"), 90, [])], backend)
    assert tomorrow["new"] == 0 and tomorrow["cross_board_duplicates"] == 1


def test_dry_run_writes_nothing():
    backend = MemoryBackend()
    result = save([(job(), 80, [])], backend, dry_run=True)
    assert result["new"] == 1 and backend.items == {}


def test_item_has_no_floats():
    backend = MemoryBackend()
    save([(job(salary=65000.5), 80, ["x"])], backend)
    item = backend.items["reed#1"]
    assert not any(isinstance(v, float) for v in item.values())
    assert item["fingerprint"] and item["expires_at"] > 0


def test_daily_run_end_to_end(monkeypatch):
    monkeypatch.setattr(daily, "fetch_all", lambda: ([job(desc=CV_DESC), job(title="SRE", sid="2")],
                                                     {"raw": {}, "kept": {}, "eligibility": {}, "dropped": {},
                                                      "errors": [], "skipped_sources": [], "market_mean": {}}))
    backend = MemoryBackend()
    result, new = daily.run(backend=backend)
    assert result["new"] == 2 and result["pending_for_digest"] == 2
    assert new[0][1] >= new[1][1]                   # highest score first
    again, _ = daily.run(backend=backend)
    assert again["new"] == 0 and again["already_seen"] == 2
