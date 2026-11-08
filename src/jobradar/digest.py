"""Daily email: every job not yet emailed, ranked by score.

Preview from the table without fetching or sending (opens in a browser):
    PYTHONPATH=src python -m jobradar.digest --preview /tmp/digest.html
Send it now (marks the jobs as emailed):
    PYTHONPATH=src python -m jobradar.digest --send

All job text comes from third-party ads, so everything is HTML-escaped.
Board credits (Himalayas, Remotive, Remote OK) follow their API terms.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from datetime import date, datetime, timezone

TOP, GOOD = 80, 60
MAX_TOP, MAX_GOOD, MAX_LOW = 40, 30, 15
BOARD_LINKS = {"himalayas": ("Himalayas", "https://himalayas.app"),
               "remotive": ("Remotive", "https://remotive.com"),
               "remoteok": ("Remote OK", "https://remoteok.com"),
               "hn": ("Hacker News", "https://news.ycombinator.com"),
               "reed": ("Reed", "https://www.reed.co.uk"),
               "adzuna": ("Adzuna", "https://www.adzuna.co.uk")}


def _f(v):
    return float(v) if v is not None else None


def pay_text(item: dict) -> str:
    lo, hi = _f(item.get("salary_min")), _f(item.get("salary_max"))
    if not (lo or hi):
        return ""
    if item.get("salary_period") == "day":
        fmt = lambda v: f"£{v:,.0f}"
        suffix = "/day"
    else:
        fmt = lambda v: f"£{v / 1000:.0f}k"
        suffix = ""
    if lo and hi and round(lo) != round(hi):
        return f"{fmt(lo)}–{fmt(hi)}{suffix}"
    return f"{fmt(hi or lo)}{suffix}"


def age_text(posted: str | None, today: date) -> str:
    if not posted:
        return ""
    try:
        days = (today - date.fromisoformat(posted[:10])).days
    except ValueError:
        return ""
    return "today" if days <= 0 else ("yesterday" if days == 1 else f"{days}d ago")


def _why(item: dict) -> str:
    reasons = [r for r in item.get("score_reasons") or [] if not r.endswith(" title")]
    return "; ".join(reasons)[:160]


def _card(item: dict, today: date) -> str:
    e = html.escape
    score = int(item.get("score", 0))
    colour = "#1a7f37" if score >= TOP else ("#9a6700" if score >= GOOD else "#6e7781")
    meta = " · ".join(x for x in [item.get("company"), item.get("location"), pay_text(item),
                                  age_text(item.get("posted"), today)] if x)
    unclear = ""
    if item.get("eligibility") == "unclear":
        unclear = (f'<div style="color:#9a6700;font-size:12px">? Check UK eligibility: '
                   f'{e(item.get("eligibility_reason", ""))}</div>')
    board, board_url = BOARD_LINKS.get(item.get("source"), (None, None))
    via = (f' · via <a href="{e(board_url)}" style="color:#6e7781">{e(board)}</a>'
           if board and item.get("source") not in ("reed", "adzuna") else "")
    return f"""
<tr><td style="padding:10px 0;border-bottom:1px solid #eaeef2">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
    <td width="44" valign="top"><div style="background:{colour};color:#fff;font-weight:bold;border-radius:6px;
        text-align:center;padding:6px 0;font-size:14px;width:38px">{score}</div></td>
    <td valign="top">
      <a href="{e(item.get('url', ''))}" style="font-size:15px;font-weight:bold;color:#0969da;text-decoration:none">
        {e(item.get('title', ''))}</a>
      <div style="color:#24292f;font-size:13px">{e(meta)}</div>
      <div style="color:#57606a;font-size:12px">{e(_why(item))}{via}</div>
      {unclear}
    </td></tr></table>
</td></tr>"""


def _section(title: str, items: list[dict], cap: int, today: date) -> str:
    if not items:
        return ""
    more = len(items) - cap
    rows = "".join(_card(i, today) for i in items[:cap])
    tail = (f'<tr><td style="padding:8px 0;color:#6e7781;font-size:12px">+ {more} more in this group '
            f'(saved in the table)</td></tr>' if more > 0 else "")
    return (f'<h2 style="font-size:16px;margin:24px 0 4px;color:#24292f">{html.escape(title)} '
            f'<span style="color:#6e7781;font-weight:normal">({len(items)})</span></h2>'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{rows}{tail}</table>')


def build(items: list[dict], run: dict | None = None, today: date | None = None) -> tuple[str, str, str]:
    """Return (subject, html, text) for the pending items."""
    today = today or datetime.now(timezone.utc).date()
    items = sorted(items, key=lambda i: int(i.get("score", 0)), reverse=True)
    top = [i for i in items if int(i["score"]) >= TOP]
    good = [i for i in items if GOOD <= int(i["score"]) < TOP]
    low = [i for i in items if int(i["score"]) < GOOD]
    day = today.strftime("%a %-d %b")

    if items:
        subject = f"Job Radar: {len(items)} new job{'s' if len(items) != 1 else ''}"
        subject += f" ({len(top)} top match{'es' if len(top) != 1 else ''}) – {day}" if top else f" – {day}"
    else:
        subject = f"Job Radar: no new jobs – {day}"

    run = run or {}
    errors = run.get("errors") or []
    footer_bits = []
    if run.get("raw_by_source"):
        footer_bits.append("Checked: " + ", ".join(f"{k} {v}" for k, v in run["raw_by_source"].items()))
    if run.get("already_seen") is not None:
        footer_bits.append(f"{run.get('already_seen')} already seen, "
                           f"{run.get('cross_board_duplicates', 0)} duplicates skipped")
    warn = ""
    if errors:
        warn = ('<div style="background:#fff8c5;border:1px solid #d4a72c;padding:8px;border-radius:6px;'
                f'font-size:12px;margin-top:12px"><b>{len(errors)} source error(s):</b><br>'
                + "<br>".join(html.escape(x) for x in errors[:5]) + "</div>")

    body = (_section("Top matches", top, MAX_TOP, today) + _section("Worth a look", good, MAX_GOOD, today)
            + _section("Lower matches", low, MAX_LOW, today)) or (
        '<p style="color:#57606a">Nothing new since the last digest. The sources were checked; '
        'this email just confirms the radar is running.</p>')

    page = f"""<!doctype html><html><body style="margin:0;background:#f6f8fa">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:16px">
<table role="presentation" width="640" cellspacing="0" cellpadding="0"
       style="max-width:640px;width:100%;background:#fff;border-radius:8px;padding:20px;
              font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">
<tr><td>
  <h1 style="font-size:20px;margin:0 0 4px;color:#24292f">Job Radar · {html.escape(day)}</h1>
  <div style="color:#57606a;font-size:13px">{len(items)} new · {len(top)} top · {len(good)} worth a look ·
    scores are against your CV (title, skills, location, pay, level)</div>
  {warn}{body}
  <p style="color:#8c959f;font-size:11px;margin-top:24px">{html.escape(' · '.join(footer_bits))}<br>
  Sent by your Job Radar on AWS. Results are for your own use; apply on the original site.</p>
</td></tr></table></td></tr></table></body></html>"""

    lines = [subject, ""]
    for label, group in (("TOP MATCHES", top), ("WORTH A LOOK", good), ("LOWER MATCHES", low[:MAX_LOW])):
        if group:
            lines.append(label)
            for i in group:
                lines.append(f"[{int(i['score'])}] {i.get('title')} | {i.get('company')} | {i.get('location')} "
                             f"{pay_text(i)}".rstrip())
                lines.append(f"     {i.get('url', '')}")
            lines.append("")
    if errors:
        lines.append("Source errors: " + "; ".join(errors[:5]))
    return subject, page, "\n".join(lines)


def send_email(subject: str, page: str, text: str, sender: str | None = None, to: str | None = None,
               client=None) -> str:
    if client is None:
        import boto3
        client = boto3.client("sesv2")
    resp = client.send_email(
        FromEmailAddress=sender or os.environ["DIGEST_FROM"],
        Destination={"ToAddresses": [to or os.environ["DIGEST_TO"]]},
        Content={"Simple": {"Subject": {"Data": subject, "Charset": "UTF-8"},
                            "Body": {"Html": {"Data": page, "Charset": "UTF-8"},
                                     "Text": {"Data": text, "Charset": "UTF-8"}}}},
    )
    return resp.get("MessageId", "")


def send_digest(backend, run: dict | None = None, send_empty: bool = True, client=None) -> dict:
    """Email every pending job, then mark them as emailed. Sending comes first, so a
    failure to send leaves them pending for tomorrow rather than losing them."""
    items = backend.list_pending()
    if not items and not send_empty:
        return {"sent": False, "jobs": 0}
    subject, page, text = build(items, run)
    message_id = send_email(subject, page, text, client=client)
    backend.mark_sent([i["pk"] for i in items])
    return {"sent": True, "jobs": len(items), "subject": subject, "message_id": message_id}


def main() -> None:
    p = argparse.ArgumentParser(description="Preview or send the digest of pending jobs.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--preview", metavar="FILE", help="write the email as HTML to FILE, send nothing")
    g.add_argument("--send", action="store_true", help="send now and mark the jobs as emailed")
    args = p.parse_args()
    os.environ.setdefault("TABLE_NAME", "job-radar-jobs")
    from .store import DynamoBackend
    backend = DynamoBackend()

    if args.preview:
        items = backend.list_pending()
        subject, page, _ = build(items)
        with open(args.preview, "w", encoding="utf-8") as fh:
            fh.write(page)
        print(f"{subject}\nWrote {args.preview} ({len(items)} jobs). Open it with: open {args.preview}")
    else:
        os.environ.setdefault("DIGEST_FROM", "Job Radar <radar@jobs.mustaphaseriki.dev>")
        if "DIGEST_TO" not in os.environ:
            raise SystemExit("Set DIGEST_TO to your verified address first.")
        print(json.dumps(send_digest(backend), indent=2))


if __name__ == "__main__":
    main()
