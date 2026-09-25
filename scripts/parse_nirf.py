#!/usr/bin/env python3
"""
Build the verified college-quality dataset for Tamil Nadu engineering colleges
from the National Institutional Ranking Framework (NIRF), Ministry of Education,
Government of India.

Two kinds of official NIRF source are used:

1. Ranking tables (https://www.nirfindia.org/Rankings/2025/EngineeringRanking*.html)
   - Individually ranked institutes (top 100) carry a NIRF institute id, an
     overall score and the five published sub-scores:
       TLR        Teaching, Learning & Resources
       RPC        Research and Professional Practice
       GO         Graduation Outcomes  (placement / salary / graduation driven)
       OI         Outreach and Inclusivity
       PERCEPTION Peer perception
   - Institutes below rank 100 are published only as a rank BAND
     (101-150, 151-200, 201-300) with no id and no score.

2. Per-institute data disclosures
   (https://www.nirfindia.org/nirfpdfcdn/2025/pdf/Engineering/{id}.pdf)
   These are the forms each institute submits to the Ministry of Education and
   they contain the figures this project treats as the trustworthy basis for
   placement and laboratory/infrastructure quality:
       - number of students graduating in minimum stipulated time
       - number of students placed
       - median salary of placed graduates
       - annual capital expenditure on new laboratory equipment and software
       - annual capital expenditure on library resources
       - other capital expenditure on classrooms/labs/workshops
   Disclosures are only available for institutes that have a NIRF id, i.e. the
   individually ranked ones.

Nothing here is estimated or inferred. A field that cannot be read from the
official source is emitted as null and reported, so the application can label it
as unverified instead of presenting a guess.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data-sources" / "raw"
OUT_DIR = Path(__file__).resolve().parent.parent / "data-sources" / "parsed"

YEAR = 2025
RANKED_URL = f"https://www.nirfindia.org/Rankings/{YEAR}/EngineeringRanking.html"
BAND_URLS = {
    "101-150": f"https://www.nirfindia.org/Rankings/{YEAR}/EngineeringRanking150.html",
    "151-200": f"https://www.nirfindia.org/Rankings/{YEAR}/EngineeringRanking200.html",
    "201-300": f"https://www.nirfindia.org/Rankings/{YEAR}/EngineeringRanking300.html",
}
DISCLOSURE_URL = "https://www.nirfindia.org/nirfpdfcdn/{year}/pdf/Engineering/{id}.pdf"

UA = "Mozilla/5.0 (compatible; TNEA-advisor-dataset-builder)"

STATE = "Tamil Nadu"


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as resp:
        dest.write_bytes(resp.read())
    time.sleep(0.3)
    return dest


def strip_tags(fragment: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).split())


def parse_ranked(html: str) -> list[dict]:
    """Parse the individually ranked NIRF table (ids, scores, sub-scores)."""
    entries: list[dict] = []
    # Each row begins with the institute id in its own cell.
    for match in re.finditer(r"<td>(IR-E-[A-Z]-\d+)</td>", html):
        institute_id = match.group(1)
        window = html[match.end() : match.end() + 8000]

        # The sub-score breakdown sits in a nested hidden <table> inside this
        # row. That nested table contains its own </tr>, so it must be removed
        # BEFORE the row is delimited, otherwise the row would be truncated
        # before the city/state/score/rank cells are reached.
        sub_scores = None
        hidden = re.search(r'<div class="tbl_hidden".*?</table>\s*</div>', window, re.S)
        if hidden:
            numbers = re.findall(r"<td>([\d.]+)</td>", hidden.group(0))
            if len(numbers) >= 5:
                sub_scores = {
                    "TLR": float(numbers[0]),
                    "RPC": float(numbers[1]),
                    "GO": float(numbers[2]),
                    "OI": float(numbers[3]),
                    "PERCEPTION": float(numbers[4]),
                }
            window = window.replace(hidden.group(0), "")

        row = window.split("</tr>")[0]

        name_match = re.search(r"<td>(.*?)(?:<div|</td>)", row, re.S)
        name = strip_tags(name_match.group(1)) if name_match else ""

        cells = [strip_tags(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        # Trailing cells are: city, state, score, rank
        tail = [c for c in cells if c]
        city = state = None
        score = rank = None
        if len(tail) >= 4:
            city, state, score_text, rank_text = tail[-4:]
            try:
                score = float(score_text)
            except ValueError:
                score = None
            rank_digits = re.sub(r"\D", "", rank_text)
            rank = int(rank_digits) if rank_digits else None

        entries.append(
            {
                "nirf_id": institute_id,
                "name": name,
                "city": city,
                "state": state,
                "score": score,
                "rank": rank,
                "rank_band": None,
                "sub_scores": sub_scores,
            }
        )
    return entries


def parse_band(html: str, band: str) -> list[dict]:
    entries: list[dict] = []
    for row in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        cells = [strip_tags(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 3 and cells[0]:
            entries.append(
                {
                    "nirf_id": None,
                    "name": cells[0],
                    "city": cells[1],
                    "state": cells[2],
                    "score": None,
                    "rank": None,
                    "rank_band": band,
                    "sub_scores": None,
                }
            )
    return entries


# --- per-institute disclosure parsing -------------------------------------

UG4_ROW = re.compile(
    r"(?P<intake_year>\d{4}-\d{2})\s+(?P<intake>\d+)\s+(?P<admitted>\d+)\s+"
    r"(?P<lateral_year>\d{4}-\d{2})\s+(?P<lateral>\d+)\s+"
    r"(?P<grad_year>\d{4}-\d{2})\s+(?P<graduating>\d+)\s+(?P<placed>\d+)\s+"
    r"(?P<median>\d+)\s*\("
)

MONEY_AFTER = r"\s*(\d{3,})\s*\("


def money_after(text: str, label: str) -> int | None:
    idx = text.find(label)
    if idx == -1:
        return None
    match = re.search(MONEY_AFTER, text[idx + len(label) : idx + len(label) + 120])
    return int(match.group(1)) if match else None


def parse_disclosure(pdf_path: Path) -> dict:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    chunks = []
    try:
        for page in (pdf[i] for i in range(len(pdf))):
            tp = page.get_textpage()
            chunks.append(tp.get_text_range())
            tp.close()
            page.close()
    finally:
        pdf.close()
    raw = "\n".join(chunks)
    flat = " ".join(raw.split())

    # Placement: use the most recent graduating cohort in the UG 4-year table.
    best = None
    ug4_section = flat
    marker = flat.find("UG [4 Years Program(s)]: Placement & higher studies")
    if marker != -1:
        end = flat.find("UG [5 Years Program(s)]: Placement", marker)
        if end == -1:
            end = flat.find("PG [2 Years Program(s)]: Placement", marker)
        ug4_section = flat[marker : end if end != -1 else marker + 4000]

    for m in UG4_ROW.finditer(ug4_section):
        record = {
            "graduating_year": m.group("grad_year"),
            "students_graduating": int(m.group("graduating")),
            "students_placed": int(m.group("placed")),
            "median_salary_inr": int(m.group("median")),
        }
        if best is None or record["graduating_year"] > best["graduating_year"]:
            best = record

    lab = money_after(flat, "New Equipment and software for Laboratories")
    library = money_after(flat, "Library ( Books, Journals and e-Resources only)")
    if library is None:
        library = money_after(flat, "Library ( Books, Journals and e-Resources")
    other_capital = money_after(
        flat, "Other expenditure on creation of Capital Assets"
    )
    workshops = money_after(flat, "Engineering Workshops")

    # UG 4-year total student strength (male, female, total, ...)
    strength = None
    sm = re.search(
        r"UG \[4 Years\s*Program\(s\)\]\s+(\d+)\s+(\d+)\s+(\d+)\b", flat
    )
    if sm:
        strength = int(sm.group(3))

    return {
        "placement": best,
        "lab_equipment_expenditure_inr": lab,
        "library_expenditure_inr": library,
        "other_capital_expenditure_inr": other_capital,
        "engineering_workshops_expenditure_inr": workshops,
        "ug4_total_students": strength,
    }


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ranked_html = fetch(RANKED_URL, RAW_DIR / f"nirf{YEAR}_ranked.html").read_text(
        encoding="utf-8", errors="ignore"
    )
    all_entries = parse_ranked(ranked_html)

    for band, url in BAND_URLS.items():
        path = RAW_DIR / f"nirf{YEAR}_band_{band.replace('-', '_')}.html"
        html = fetch(url, path).read_text(encoding="utf-8", errors="ignore")
        all_entries.extend(parse_band(html, band))

    tn = [e for e in all_entries if (e.get("state") or "").strip() == STATE]
    print(f"NIRF {YEAR}: {len(all_entries)} total entries, {len(tn)} in {STATE}")

    # Fetch disclosures where an id exists.
    disclosure_dir = RAW_DIR / "nirf_disclosures"
    disclosure_dir.mkdir(exist_ok=True)

    for entry in tn:
        entry["source"] = {
            "publisher": "National Institutional Ranking Framework (NIRF), Ministry of Education, Government of India",
            "year": YEAR,
            "ranking_url": RANKED_URL if entry["nirf_id"] else BAND_URLS[entry["rank_band"]],
        }
        entry["disclosure"] = None
        if not entry["nirf_id"]:
            continue
        url = DISCLOSURE_URL.format(year=YEAR, id=entry["nirf_id"])
        dest = disclosure_dir / f"{entry['nirf_id']}.pdf"
        try:
            fetch(url, dest)
            parsed = parse_disclosure(dest)
            parsed["source_url"] = url
            entry["disclosure"] = parsed
            median = (parsed["placement"] or {}).get("median_salary_inr")
            print(
                f"  {entry['nirf_id']:<15} {entry['name'][:45]:<45} "
                f"median_salary={median} lab={parsed['lab_equipment_expenditure_inr']}"
            )
        except Exception as exc:  # noqa: BLE001 - reported, never silently ignored
            print(f"  !! disclosure failed for {entry['nirf_id']}: {exc}", file=sys.stderr)

    payload = {
        "meta": {
            "dataset": f"NIRF {YEAR} engineering data for {STATE} institutions",
            "publisher": "National Institutional Ranking Framework (NIRF), Ministry of Education, Government of India",
            "year": YEAR,
            "notes": [
                "Institutes ranked outside the top 100 are published by NIRF only as a rank band, with no score and no institute id.",
                "Per-institute disclosures (median salary, laboratory and infrastructure expenditure) exist only for institutes with a NIRF id.",
                "Fields that are absent from the official source are null and must be shown as unverified.",
            ],
        },
        "institutions": tn,
    }

    out = OUT_DIR / f"nirf_{YEAR}_tamilnadu.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {len(tn)} Tamil Nadu institutions -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
