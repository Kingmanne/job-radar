from jobradar import settings
from jobradar.filters import is_relevant, meets_pay
from jobradar.sources import adzuna, reed

EXCLUDE = settings.DEFAULT_SEARCHES["exclude_words"]


def _reed(load, i):
    return reed.normalise(load("reed_search.json")["results"][i])


def test_relevance(load):
    assert is_relevant(_reed(load, 0), EXCLUDE)          # DevOps Engineer
    assert not is_relevant(_reed(load, 2), EXCLUDE)      # trainee
    assert not is_relevant(_reed(load, 3), EXCLUDE)      # sales assistant


def test_pay(load):
    assert meets_pay(_reed(load, 0), 45000, 400)         # £65k
    assert meets_pay(_reed(load, 1), 45000, 400)         # £550/day
    assert not meets_pay(_reed(load, 2), 45000, 400)     # £25k
    assert meets_pay(_reed(load, 4), 45000, 400)         # unknown pay passes


def test_same_job_on_two_boards_shares_fingerprint(load):
    r = _reed(load, 0)
    a = adzuna.normalise(load("adzuna_search.json")["results"][1])
    assert r.pk != a.pk
    assert r.fingerprint == a.fingerprint


def test_placeholder_counts_as_missing(monkeypatch):
    monkeypatch.setenv("REED_API_KEY", "CHANGE_ME")
    assert settings.secret("reed_api_key") is None
    monkeypatch.setenv("REED_API_KEY", " real-key ")
    assert settings.secret("reed_api_key") == "real-key"


def test_searches_override(monkeypatch):
    monkeypatch.setenv("JOBRADAR_SEARCHES", '{"min_salary": 60000}')
    cfg = settings.searches()
    assert cfg["min_salary"] == 60000
    assert cfg["keywords"]                               # defaults kept


def test_title_exclusions():
    from jobradar.models import Job
    mk = lambda t: Job("reed", "x", t, "c", "l", "u")
    assert not is_relevant(mk("Senior Power Platform Consultant"), EXCLUDE)
    assert not is_relevant(mk("Data Engineer + AI Engineering (Python & Cloud)"), EXCLUDE)
    assert not is_relevant(mk("Lead Full Stack Engineer (Python / AWS)"), EXCLUDE)
    assert is_relevant(mk("Azure DevOps Engineer"), EXCLUDE)
    assert is_relevant(mk("Platform Engineer, AWS, Kubernetes"), EXCLUDE)
    assert is_relevant(mk("Power Platform Lead"), EXCLUDE, exclude_titles=[])   # overridable
