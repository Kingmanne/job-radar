from datetime import date
from decimal import Decimal

from jobradar import daily, digest
from jobradar.store import MemoryBackend

TODAY = date(2026, 11, 9)


def item(pk, score, title="DevOps Engineer", source="reed", **kw):
    base = {"pk": pk, "score": Decimal(score), "title": title, "company": "Acme", "location": "Manchester",
            "url": f"https://example.com/{pk}", "source": source, "posted": "2026-11-08",
            "score_reasons": ["DevOps title", "skills: AWS, Terraform", "Manchester area"],
            "eligibility": "eligible", "digest_pending": "1"}
    base.update(kw)
    return base


class FakeSES:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send_email(self, **kw):
        if self.fail:
            raise RuntimeError("AccessDenied")
        self.sent.append(kw)
        return {"MessageId": "m-1"}


def test_pay_text():
    assert digest.pay_text({"salary_min": Decimal(65000), "salary_max": Decimal(75000)}) == "£65k–£75k"
    assert digest.pay_text({"salary_max": Decimal(550), "salary_period": "day"}) == "£550/day"
    assert digest.pay_text({}) == ""


def test_build_groups_and_subject():
    items = [item("a", 92), item("b", 70), item("c", 40), item("d", 85)]
    subject, page, text = digest.build(items, today=TODAY)
    assert subject == "Job Radar: 4 new jobs (2 top matches) – Mon 9 Nov"
    assert page.index("Top matches") < page.index("Worth a look") < page.index("Lower matches")
    assert "[92] DevOps Engineer" in text and "yesterday" in page


def test_escapes_untrusted_ad_text():
    _, page, _ = digest.build([item("x", 90, title='<script>alert(1)</script>', company="A&B")], today=TODAY)
    assert "<script>" not in page and "&lt;script&gt;" in page and "A&amp;B" in page


def test_unclear_and_board_credit():
    _, page, _ = digest.build([item("h", 85, source="himalayas", eligibility="unclear",
                                    eligibility_reason="region: Europe")], today=TODAY)
    assert "Check UK eligibility" in page and "via <a href=\"https://himalayas.app\"" in page


def test_caps_long_groups():
    items = [item(f"t{n}", 90) for n in range(digest.MAX_TOP + 5)]
    _, page, _ = digest.build(items, today=TODAY)
    assert "+ 5 more in this group" in page


def test_empty_day_still_confirms_running():
    subject, page, _ = digest.build([], run={"raw_by_source": {"reed": 10}, "errors": ["hn: HTTP 503"]},
                                    today=TODAY)
    assert "no new jobs" in subject and "radar is running" in page and "HTTP 503" in page


def test_send_marks_jobs_emailed(monkeypatch):
    monkeypatch.setenv("DIGEST_FROM", "radar@x.dev")
    monkeypatch.setenv("DIGEST_TO", "me@x.dev")
    backend = MemoryBackend()
    backend.put_many([item("a", 90), item("b", 60)])
    ses = FakeSES()
    result = digest.send_digest(backend, client=ses)
    assert result["sent"] and result["jobs"] == 2
    assert backend.count_pending() == 0 and "emailed_at" in backend.items["a"]
    again = digest.send_digest(backend, client=ses)
    assert again["jobs"] == 0 and "no new jobs" in ses.sent[1]["Content"]["Simple"]["Subject"]["Data"]


def test_failed_send_keeps_jobs_pending(monkeypatch):
    monkeypatch.setenv("DIGEST_FROM", "radar@x.dev")
    monkeypatch.setenv("DIGEST_TO", "me@x.dev")
    backend = MemoryBackend()
    backend.put_many([item("a", 90)])
    try:
        digest.send_digest(backend, client=FakeSES(fail=True))
    except RuntimeError:
        pass
    assert backend.count_pending() == 1


def test_send_uses_env_addresses(monkeypatch):
    monkeypatch.setenv("DIGEST_FROM", "Job Radar <radar@jobs.example.dev>")
    monkeypatch.setenv("DIGEST_TO", "me@example.com")
    ses = FakeSES()
    digest.send_email("s", "<p>x</p>", "x", client=ses)
    assert ses.sent[0]["FromEmailAddress"] == "Job Radar <radar@jobs.example.dev>"
    assert ses.sent[0]["Destination"] == {"ToAddresses": ["me@example.com"]}


def test_handler_digest_only(monkeypatch):
    backend = MemoryBackend()
    backend.put_many([item("a", 90)])
    monkeypatch.setattr(daily, "DynamoBackend", lambda: backend)
    sent = []
    monkeypatch.setattr(daily, "send_digest", lambda b, run=None: sent.append(b) or {"sent": True, "jobs": 1})
    monkeypatch.setattr(daily, "fetch_all", lambda: (_ for _ in ()).throw(AssertionError("must not fetch")))
    result = daily.handler({"digest_only": True}, None)
    assert result["digest"]["sent"] and sent == [backend]
