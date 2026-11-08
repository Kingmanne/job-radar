"""Can someone living in the UK apply? Returns ("eligible"|"unclear"|"not_eligible", reason).

Rules, in order:
1. The ad explicitly rules the UK out, or says US/Canada/EU-only  -> not_eligible
2. Location mentions the UK (country, nation or a big UK city)   -> eligible
3. Location says worldwide / anywhere                             -> eligible
4. Location says Europe / EMEA / GMT-ish time zones               -> unclear (often fine, check)
5. Location names somewhere else (US, India, Germany...)          -> not_eligible
6. Ad body says UK-based / right to work in the UK                -> eligible
7. On-site job somewhere not in the UK                            -> not_eligible
8. Nothing to go on                                               -> unclear
"""
from __future__ import annotations

import re

UK = re.compile(r"\b(uk|u\.k\.|united kingdom|great britain|britain|gb|england|scotland|wales|northern ireland|"
                r"london|manchester|birmingham|leeds|bristol|edinburgh|glasgow|cardiff|belfast|liverpool|"
                r"sheffield|newcastle|nottingham|cambridge|oxford|reading|milton keynes|salford|stockport)\b", re.I)
WORLD = re.compile(r"\b(worldwide|anywhere|global(ly)?|international|all countries|any country|any location|"
                   r"location independent)\b", re.I)
WIDE = re.compile(r"\b(europe|european|emea|gmt|bst|wet|cet|cest|eu time ?zones?|europe time ?zones?)\b", re.I)
OTHER = re.compile(r"\b(us|usa|u\.s\.a?\.?|united states|america|americas|north america|latam|latin america|"
                   r"canada|mexico|brazil|argentina|colombia|apac|asia|india|pakistan|australia|new zealand|"
                   r"singapore|japan|philippines|africa|nigeria|kenya|south africa|germany|france|spain|italy|"
                   r"netherlands|poland|portugal|romania|ireland|israel|sweden|denmark|norway|finland|"
                   r"switzerland|austria|belgium|czech|ukraine|turkey|uae|dubai|"
                   r"new york|nyc|san francisco|sf|bay area|seattle|austin|boston|chicago|los angeles|toronto|"
                   r"palo alto|mountain view|menlo park|san jose|san diego|denver|atlanta|miami|dallas|"
                   r"houston|phoenix|portland|washington|dc|philadelphia|pittsburgh|vancouver|montreal|"
                   r"berlin|paris|amsterdam|madrid|barcelona|lisbon|dublin|warsaw|bangalore|bengaluru)\b", re.I)
US_STATE = re.compile(r",\s*(A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|"
                      r"PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b")      # "Austin, TX" (case-sensitive)
UTC_OFFSET = re.compile(r"\b(?:utc|gmt)\s*([+-]\s*\d{1,2})", re.I)

EXCLUDES_UK = re.compile(r"\b(excluding|except|not|no)\s+(the\s+)?(uk|united kingdom)\b", re.I)
BODY_NO = re.compile(
    r"(\b(must|need to|required to|have to)\s+(be\s+)?(based|located|resid\w*|liv\w*)\s+in\s+(the\s+)?"
    r"(us|usa|u\.s\.|united states|canada|eu|european union)\b)"
    r"|\b(us|usa|u\.s\.)[- ]only\b"
    r"|\b(us|u\.s\.) (citizens?|residents?) only\b"
    r"|\bauthori[sz]ed to work in the (us|u\.s\.|united states)\b"
    r"|\b(eu|european union) (work permit|citizens?|residents?) only\b", re.I)
BODY_UK = re.compile(r"\b(uk[- ]based|based in the uk|right to work in the uk|uk residents?|uk only)\b", re.I)


def classify(location: str | None, description: str = "", remote: bool = True,
             restrictions: list[str] | None = None) -> tuple[str, str]:
    loc = (location or "").strip()
    body = description or ""

    if restrictions is not None:                     # Himalayas gives an explicit country list
        if not restrictions:
            loc = "worldwide"
        elif any(UK.search(r) for r in restrictions):
            return "eligible", "UK in allowed countries"
        else:
            return "not_eligible", "allowed: " + ", ".join(restrictions[:4])

    if EXCLUDES_UK.search(loc) or EXCLUDES_UK.search(body):
        return "not_eligible", "ad excludes the UK"
    m = BODY_NO.search(body) or BODY_NO.search(loc)
    if m:
        return "not_eligible", f"ad says: {m.group(0).strip()[:60]}"
    if UK.search(loc):
        return "eligible", "UK location"
    if WORLD.search(loc):
        return "eligible", "worldwide"
    offsets = [int(o.replace(" ", "")) for o in UTC_OFFSET.findall(loc)]
    if offsets:
        lo, hi = min(offsets), max(offsets)
        label = f"UTC{lo:+d}" if lo == hi else f"UTC{lo:+d} to UTC{hi:+d}"
        if lo <= 0 <= hi or any(-2 <= h <= 3 for h in offsets):     # range covers UK time
            return "unclear", f"time zone {label}"
        return "not_eligible", f"time zone {label}"
    if WIDE.search(loc):
        return "unclear", f"region: {loc[:40]} (check UK is included)"
    if OTHER.search(loc) or US_STATE.search(loc):
        return "not_eligible", f"location: {loc[:40]}"
    if BODY_UK.search(body):
        return "eligible", "ad mentions UK"
    if loc and not remote:
        return "not_eligible", f"on-site: {loc[:40]}"
    return "unclear", "location not stated"
