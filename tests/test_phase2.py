import pytest

from jobradar import fetch as fetch_mod
from jobradar.eligibility import classify
from jobradar.money import parse_salary_text, to_gbp
from jobradar.sources import ats, himalayas, hn, remoteok, remotive
from jobradar.text import strip_html


@pytest.mark.parametrize("loc,desc,remote,expected", [
    ("United Kingdom", "", True, "eligible"),
    ("Remote (UK only)", "", True, "eligible"),
    ("USA or UK", "", True, "eligible"),
    ("Worldwide", "", True, "eligible"),
    ("Anywhere", "Must be based in the US", True, "not_eligible"),
    ("Europe", "", True, "unclear"),
    ("EMEA", "", True, "unclear"),
    ("Europe (excluding UK)", "", True, "not_eligible"),
    ("USA", "", True, "not_eligible"),
    ("Remote (US)", "", True, "not_eligible"),
    ("UTC+1 to UTC+3", "", True, "unclear"),
    ("UTC-5", "", True, "not_eligible"),
    ("", "We hire UK-based engineers", True, "eligible"),
    ("Remote", "", True, "unclear"),
    ("Berlin", "", False, "not_eligible"),
    ("Tallinn", "", False, "not_eligible"),
    ("Palo Alto", "", True, "not_eligible"),
    ("REMOTE (all time zones between UTC-8 and UTC+2)", "", True, "unclear"),
    ("UTC-8 to UTC-5", "", True, "not_eligible"),
    ("Austin, TX", "", True, "not_eligible"),
])
def test_classify(loc, desc, remote, expected):
    assert classify(loc, desc, remote)[0] == expected


def test_classify_himalayas_restrictions():
    assert classify(None, "", True, [])[0] == "eligible"
    assert classify(None, "", True, ["United Kingdom"])[0] == "eligible"
    assert classify(None, "", True, ["Germany", "France"])[0] == "not_eligible"


@pytest.mark.parametrize("text,expected", [
    ("$120k - $150k", (120000, 150000, "USD", "year")),
    ("€70,000-€85,000", (70000, 85000, "EUR", "year")),
    ("£500 per day", (500, 500, "GBP", "day")),
    ("$60/hour", (60, 60, "USD", "hour")),
    ("Competitive", (None, None, None, "year")),
    ("", (None, None, None, "year")),
])
def test_parse_salary_text(text, expected):
    assert parse_salary_text(text) == expected


def test_to_gbp():
    assert to_gbp(100000, "USD") == 78000
    assert to_gbp(50000, "GBP") == 50000
    assert to_gbp(100, "XYZ") is None
    assert to_gbp(None, "USD") is None


def test_strip_html_double_escaped():
    assert strip_html("&lt;p&gt;Kubernetes &amp;amp; AWS&lt;/p&gt;") == "Kubernetes & AWS"


def test_himalayas(load):
    jobs = himalayas.fetch("devops", max_pages=1, _get=lambda *a, **k: load("himalayas_search.json"))
    by = {j.source_id: j for j in jobs}
    assert by["h-1"].eligibility == "eligible" and by["h-1"].salary_max == 90000
    assert by["h-2"].eligibility == "eligible" and by["h-2"].salary_max == 117000   # USD -> GBP
    assert by["h-3"].eligibility == "not_eligible"
    assert by["h-1"].posted == "2025-11-08"


def test_remotive(load):
    jobs = {j.source_id: j for j in remotive.fetch(_get=lambda *a, **k: load("remotive.json"))}
    assert jobs["2001"].eligibility == "unclear"
    assert jobs["2001"].salary_max == round(85000 * 0.85)
    assert jobs["2002"].eligibility == "not_eligible"
    assert jobs["2003"].eligibility == "eligible" and jobs["2003"].salary_max is None


def test_remoteok_skips_legal_notice(load):
    jobs = remoteok.fetch(_get=lambda *a, **k: load("remoteok.json"))
    assert [j.source_id for j in jobs] == ["3001", "3002"]
    assert jobs[0].salary_max == 93600
    assert jobs[1].salary_max is None            # 0 means "not given"
    assert jobs[0].description == "Terraform"


def test_hn(load):
    def fake(url, params=None, **_):
        if "search_by_date" in url:
            return {"hits": [{"title": "Ask HN: Who wants to be hired? (November 2026)", "objectID": "8999"},
                             {"title": "Ask HN: Who is hiring? (November 2026)", "objectID": "9000"}]}
        assert url.endswith("/9000")
        return load("hn_item.json")
    jobs = {j.source_id: j for j in hn.fetch(_get=fake)}
    assert set(jobs) == {"9001", "9002"}          # React dev and deleted comment skipped
    assert jobs["9001"].company == "Acme Robotics"
    assert jobs["9001"].title == "Senior Platform Engineer"
    assert jobs["9001"].eligibility == "eligible"
    assert jobs["9002"].eligibility == "not_eligible"


def test_ats_entries():
    assert ats.parse_entry("greenhouse:monzo") == ("greenhouse", "monzo", "Monzo")
    assert ats.parse_entry("lever-eu:acme-co:ACME") == ("lever-eu", "acme-co", "ACME")
    with pytest.raises(ValueError):
        ats.parse_entry("workday:x")
    with pytest.raises(ValueError):
        ats.parse_entry("monzo")


def test_greenhouse(load):
    jobs = ats.fetch("greenhouse:monzo", _get=lambda *a, **k: load("greenhouse.json"))
    assert jobs[0].pk == "greenhouse#monzo:7001"
    assert jobs[0].eligibility == "eligible" and jobs[0].posted == "2026-11-04"
    assert jobs[1].eligibility == "not_eligible"   # Barcelona on-site


def test_ashby(load):
    jobs = ats.fetch("ashby:acme:Acme", _get=lambda *a, **k: load("ashby.json"))
    assert jobs[0].company == "Acme" and jobs[0].salary_max == 95000 and jobs[0].eligibility == "eligible"
    assert jobs[1].eligibility == "not_eligible"


def test_fetch_all_remote_only(monkeypatch, load):
    real_h, real_r, real_o = himalayas.fetch, remotive.fetch, remoteok.fetch
    monkeypatch.setattr(fetch_mod.himalayas, "fetch", lambda q, fx=None: real_h(
        q, max_pages=1, fx=fx, _get=lambda *a, **k: load("himalayas_search.json")))
    monkeypatch.setattr(fetch_mod.remotive, "fetch", lambda c, fx=None: real_r(
        c, fx=fx, _get=lambda *a, **k: load("remotive.json")))
    monkeypatch.setattr(fetch_mod.remoteok, "fetch", lambda fx=None: real_o(
        fx=fx, _get=lambda *a, **k: load("remoteok.json")))
    monkeypatch.setattr(fetch_mod.hn, "fetch", lambda: [])
    cfg = {"keywords": [], "locations": [], "exclude_words": [], "min_salary": 45000, "min_day_rate": 400,
           "himalayas_queries": ["devops", "platform"], "watch_companies": []}
    jobs, stats = fetch_mod.fetch_all(cfg)
    pks = sorted(j.pk for j in jobs)
    assert pks == ["himalayas#h-1", "himalayas#h-2", "remoteok#3001", "remotive#2001", "remotive#2003"]
    assert stats["dropped"]["not open to UK"] == 2      # h-3 (US), remotive 2002 (US)
    assert stats["dropped"]["duplicate"] == 3           # second Himalayas query returns the same 3
    assert stats["dropped"]["not relevant"] == 1        # frontend role
    assert stats["eligibility"]["unclear"] == 1


def test_hn_picks_role_not_location():
    c = {"id": 1, "author": "x", "created_at_i": 1762041600,
         "text": "Oscilar | REMOTE (US/Canada/UK/India) Full-time | Sr/Staff Platform Engineers | $150k"}
    job = hn.parse_comment(c)
    assert job.title == "Sr/Staff Platform Engineers"
    assert job.eligibility == "eligible"


def test_hn_seeking_prefix():
    c = {"id": 2, "author": "x", "created_at_i": 1762041600,
         "text": "SEEKING FREELANCER | Acme | DevOps Engineer | Remote - UK or EU"}
    job = hn.parse_comment(c)
    assert job.company == "Acme" and job.title == "DevOps Engineer"


def test_himalayas_location_label():
    assert himalayas._location([]) == "Remote: Worldwide"
    many = ["Albania", "Andorra", "Austria", "United Kingdom", "Spain"]
    assert himalayas._location(many) == "Remote: UK + 4 other countries"
