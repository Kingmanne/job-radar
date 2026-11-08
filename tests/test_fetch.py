from jobradar import fetch as fetch_mod
from jobradar.sources import reed

CFG = {
    "keywords": ["DevOps Engineer", "Platform Engineer"],
    "exclude_words": ["trainee", "no experience"],
    "locations": [{"name": "Manchester", "radius_miles": 40}],
    "min_salary": 45000, "min_day_rate": 400, "adzuna_enabled": False,
    "include_remote": False, "watch_companies": [],
}


def test_fetch_all_filters_and_dedupes(monkeypatch, load):
    monkeypatch.setenv("REED_API_KEY", "KEY")
    payload = load("reed_search.json")
    monkeypatch.setattr(fetch_mod.reed, "fetch",
                        lambda key, kw, loc, r: [reed.normalise(x, kw) for x in payload["results"]])

    jobs, stats = fetch_mod.fetch_all(CFG)
    assert sorted(j.pk for j in jobs) == ["reed#1001", "reed#1002", "reed#1005"]
    assert stats["raw"]["reed"] == 10          # 5 per keyword x 2 keywords
    assert stats["kept"]["reed"] == 3          # duplicates from keyword 2 dropped
    assert "adzuna (disabled or no key)" in stats["skipped_sources"]


def test_fetch_all_skips_reed_without_key():
    jobs, stats = fetch_mod.fetch_all(CFG)
    assert jobs == []
    assert "reed (no key)" in stats["skipped_sources"]


def test_source_error_does_not_stop_run(monkeypatch):
    monkeypatch.setenv("REED_API_KEY", "KEY")

    def boom(*a, **k):
        raise fetch_mod.SourceError("HTTP 401 from www.reed.co.uk")

    monkeypatch.setattr(fetch_mod.reed, "fetch", boom)
    jobs, stats = fetch_mod.fetch_all(CFG)
    assert jobs == []
    assert len(stats["errors"]) == 2
