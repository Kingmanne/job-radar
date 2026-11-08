from jobradar.sources import adzuna, reed


def test_reed_normalise_annual(load):
    job = reed.normalise(load("reed_search.json")["results"][0], "s")
    assert job.pk == "reed#1001"
    assert job.company == "Acme Cloud Ltd"
    assert job.salary_period == "year"
    assert job.posted == "2026-11-05"
    assert job.extra["applications"] == 12


def test_reed_detects_day_rate_and_remote(load):
    job = reed.normalise(load("reed_search.json")["results"][1])
    assert job.salary_period == "day"
    assert job.remote is True


def test_reed_fetch_stops_on_short_page(load):
    calls = []

    def fake_get(url, params=None, basic_user=None, **_):
        calls.append((params, basic_user))
        return load("reed_search.json")

    jobs = reed.fetch("KEY", "DevOps Engineer", "Manchester", 40, max_pages=3, _get=fake_get)
    assert len(jobs) == 5
    assert len(calls) == 1                     # 5 < 100, so no second page
    assert calls[0][1] == "KEY"                # key sent as Basic-auth user
    assert calls[0][0]["distanceFromLocation"] == 40


def test_adzuna_normalise_and_km(load):
    seen = {}

    def fake_get(url, params=None, **_):
        seen.update(params)
        return load("adzuna_search.json")

    jobs, mean = adzuna.fetch("abcd1234", "k" * 32, "Cloud Engineer", "London", 25, _get=fake_get)
    assert mean == 77123.4
    assert seen["distance"] == 40              # 25 miles ~ 40 km
    assert jobs[0].pk == "adzuna#4900001"
    assert jobs[0].posted == "2026-11-06"


def test_adzuna_credential_check():
    assert adzuna.credentials_look_valid("abcd1234", "k" * 32)
    assert not adzuna.credentials_look_valid("k" * 32, "k" * 32)   # key pasted twice


def test_reed_enrich_replaces_snippet(load):
    jobs = [reed.normalise(r) for r in load("reed_search.json")["results"][:2]]
    calls = []

    def fake_get(url, basic_user=None, **_):
        calls.append(url)
        if url.endswith("/1002"):
            raise reed.SourceError("HTTP 404")
        return {"jobDescription": "<p>Full ad: AWS, EKS, Terraform, Argo CD and a lot more detail here.</p>",
                "jobUrl": "https://www.reed.co.uk/jobs/full/1001"}

    n = reed.enrich(jobs, "KEY", pause=0, _get=fake_get)
    assert n == 1 and len(calls) == 2
    assert jobs[0].description.startswith("Full ad") and jobs[0].url.endswith("/1001")
    assert jobs[1].description == "Outside IR35. EKS and Argo CD."    # failure keeps the snippet
