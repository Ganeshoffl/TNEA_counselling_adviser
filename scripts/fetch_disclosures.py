#!/usr/bin/env python3
"""
Fetch and VERIFY NIRF 2025 per-institute data disclosures for the Tamil Nadu
TNEA colleges whose NIRF institute IDs were recovered separately (see
data-sources/curated/nirf_institute_ids.json).

The verification step is the point of this script. A disclosure is accepted only
if the institute name printed inside the fetched PDF matches the institution the
ID is claimed to belong to. If the names disagree the disclosure is REJECTED and
reported, because silently accepting it would attach one college's placement
record and laboratory spending to a different college.
"""

from __future__ import annotations

import difflib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_nirf import parse_disclosure  # noqa: E402  (shared extraction logic)

ROOT = Path(__file__).resolve().parent.parent
CURATED = ROOT / "data-sources" / "curated"
PARSED = ROOT / "data-sources" / "parsed"
RAW = ROOT / "data-sources" / "raw" / "nirf_disclosures"

YEAR = 2025
URL = "https://www.nirfindia.org/nirfpdfcdn/{year}/pdf/Engineering/{id}.pdf"
UA = "Mozilla/5.0 (compatible; TNEA-advisor-dataset-builder)"

GENERIC = {
    "college", "institute", "institution", "engineering", "technology", "science",
    "sciences", "research", "advanced", "studies", "university", "autonomous",
    "of", "and", "the", "for", "campus", "school", "academy", "applied", "dr",
    "sri", "shri", "sree", "st", "s",
}

NAME_IN_PDF = re.compile(r"Institute Name:\s*(?P<name>.+?)\s*\[(?P<id>IR-[A-Z]-[A-Z]-\d+)\]")


def normalise_str(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


def tokens(text: str) -> set[str]:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return {t for t in text.split() if t not in GENERIC and len(t) > 1}


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as resp:
        dest.write_bytes(resp.read())
    time.sleep(0.3)
    return dest


def name_in_pdf(pdf_path: Path) -> tuple[str | None, str | None]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[0]
        tp = page.get_textpage()
        text = tp.get_text_range()
        tp.close()
        page.close()
    finally:
        pdf.close()
    flat = " ".join(text.split())
    match = NAME_IN_PDF.search(flat)
    if not match:
        return None, None
    return match.group("name"), match.group("id")


def main() -> int:
    spec = json.loads((CURATED / "nirf_institute_ids.json").read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)

    accepted: dict[str, dict] = {}
    rejected: list[dict] = []

    for expected_name, institute_id in spec["ids"].items():
        url = URL.format(year=YEAR, id=institute_id)
        dest = RAW / f"{institute_id}.pdf"
        try:
            fetch(url, dest)
        except urllib.error.HTTPError as exc:
            rejected.append(
                {"expected_name": expected_name, "institute_id": institute_id,
                 "reason": f"HTTP {exc.code} fetching disclosure"}
            )
            print(f"REJECT {institute_id:<15} {expected_name[:44]:<44} HTTP {exc.code}")
            continue
        except Exception as exc:  # noqa: BLE001
            rejected.append(
                {"expected_name": expected_name, "institute_id": institute_id,
                 "reason": f"fetch failed: {exc}"}
            )
            print(f"REJECT {institute_id:<15} {expected_name[:44]:<44} {exc}")
            continue

        pdf_name, pdf_id = name_in_pdf(dest)
        if pdf_name is None:
            rejected.append(
                {"expected_name": expected_name, "institute_id": institute_id,
                 "reason": "could not read 'Institute Name' line from disclosure"}
            )
            print(f"REJECT {institute_id:<15} {expected_name[:44]:<44} no name line")
            continue

        want, have = tokens(expected_name), tokens(pdf_name)
        overlap = len(want & have) / len(want) if want else 0.0

        # Names made almost entirely of initials (for example "R.M.K.
        # Engineering College") lose every distinctive token once punctuation is
        # stripped and single letters are dropped, which would reject a perfect
        # match. Fall back to whole-string similarity in that case.
        ratio = difflib.SequenceMatcher(
            None, normalise_str(expected_name), normalise_str(pdf_name)
        ).ratio()
        name_ok = overlap >= 0.8 or ratio >= 0.9
        id_ok = (pdf_id == institute_id)

        if not name_ok or not id_ok:
            rejected.append(
                {
                    "expected_name": expected_name,
                    "institute_id": institute_id,
                    "name_in_pdf": pdf_name,
                    "id_in_pdf": pdf_id,
                    "token_overlap": round(overlap, 3),
                    "string_similarity": round(ratio, 3),
                    "reason": "institute name in the official disclosure does not match the expected college",
                }
            )
            print(
                f"REJECT {institute_id:<15} expected={expected_name[:36]!r} "
                f"pdf={pdf_name[:36]!r} overlap={overlap:.2f}"
            )
            continue

        parsed = parse_disclosure(dest)
        parsed["source_url"] = url
        parsed["verified_institute_name"] = pdf_name
        parsed["verified_institute_id"] = pdf_id
        accepted[expected_name] = parsed

        median = (parsed["placement"] or {}).get("median_salary_inr")
        print(
            f"ACCEPT {institute_id:<15} {expected_name[:40]:<40} "
            f"median_salary={median} lab={parsed['lab_equipment_expenditure_inr']}"
        )

    payload = {
        "meta": {
            "dataset": f"NIRF {YEAR} per-institute disclosures for band-ranked Tamil Nadu TNEA colleges",
            "publisher": "National Institutional Ranking Framework (NIRF), Ministry of Education, Government of India",
            "year": YEAR,
            "verification": "Each disclosure was accepted only after the institute name printed inside the official PDF matched the expected college and the embedded ID matched the requested ID.",
            "accepted_count": len(accepted),
            "rejected": rejected,
        },
        "disclosures": accepted,
    }

    out = PARSED / f"nirf_{YEAR}_disclosures_extra.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\naccepted={len(accepted)} rejected={len(rejected)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
