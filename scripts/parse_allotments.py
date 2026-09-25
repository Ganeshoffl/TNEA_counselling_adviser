#!/usr/bin/env python3
"""
Parse the official TNEA 2026 GENERAL ACADEMIC provisional allotment list PDFs
published by the Directorate of Technical Education (DoTE), Tamil Nadu, and
derive per-round opening/closing ranks for every college + branch + community.

Source PDFs (official):
  https://static.tneaonline.org/docs/TNEA-2026-ROUND-{N}-GENERAL-ACADEMIC-PROVISIONAL-ALLOTMENT-LIST.pdf

Printed row format in the official PDF:
  S_NO  APPLN_NO  COMMUNITY  AGGREGATE_MARK  RANK  COLLEGE_CODE  BRANCH_CODE  ALLOTTED_COMMUNITY

Note on ranks: TNEA prints tie-broken ranks with a trailing letter (e.g. "53A",
"53B") when several candidates share the same rank position. The numeric part is
the rank; the suffix only encodes tie-break order, so the numeric part is used.

Data-integrity stance: every line that is neither a data row nor known
boilerplate is counted and sampled, so that silent data loss becomes visible
instead of being hidden. Nothing is inferred or synthesised.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pypdfium2 as pdfium

RAW_DIR = Path(__file__).resolve().parent.parent / "data-sources" / "raw"
OUT_DIR = Path(__file__).resolve().parent.parent / "data-sources" / "parsed"

SOURCE_URL_TEMPLATE = (
    "https://static.tneaonline.org/docs/"
    "TNEA-2026-ROUND-{round}-GENERAL-ACADEMIC-PROVISIONAL-ALLOTMENT-LIST.pdf"
)
FILENAME_TEMPLATE = (
    "TNEA-2026-ROUND-{round}-GENERAL-ACADEMIC-PROVISIONAL-ALLOTMENT-LIST.pdf"
)

# S_NO APPLN_NO COMMUNITY AGG_MARK RANK COLLEGE_CODE BRANCH_CODE ALLOTTED_COMMUNITY
ROW_RE = re.compile(
    r"^(?P<sno>\d{1,7})\s+"
    r"(?P<appln>\d{4,9})\s+"
    r"(?P<community>[A-Z]{2,7})\s+"
    r"(?P<mark>\d{1,3}(?:\.\d+)?)\s+"
    r"(?P<rank>\d{1,7})(?P<rank_suffix>[A-Z]?)\s+"
    r"(?P<college>\d{1,5})\s+"
    r"(?P<branch>[A-Z0-9]{2,4})\s+"
    r"(?P<allotted>[A-Z]{2,7})\s*$"
)

BOILERPLATE_MARKERS = (
    "TAMILNADU",
    "TAMIL NADU",
    "DIRECTORATE",
    "PROVISIONAL ALLOTMENT",
    "GENERAL ACADEMIC",
    "S NO",
    "APPLN",
    "AGGREGATE",
    "COMMUNITY",
    "RANK",
    "COLLEGE",
    "BRANCH",
    "CODE",
    "MARK",
    "ALLOTTED",
    "PAGE ",
)


def is_boilerplate(line: str) -> bool:
    upper = line.upper()
    return any(marker in upper for marker in BOILERPLATE_MARKERS)


def extract_pages(pdf_path: Path, page_limit: int | None = None):
    """Yield text for each page using pypdfium2 (fast native extraction)."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    total = len(pdf)
    count = total if page_limit is None else min(total, page_limit)
    try:
        for index in range(count):
            page = pdf[index]
            textpage = page.get_textpage()
            try:
                yield textpage.get_text_range()
            finally:
                textpage.close()
                page.close()
    finally:
        pdf.close()


def parse_round(round_no: int, page_limit: int | None = None) -> dict:
    pdf_path = RAW_DIR / FILENAME_TEMPLATE.format(round=round_no)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing source PDF: {pdf_path}")

    rows = 0
    unmatched = 0
    unmatched_samples: list[str] = []
    communities: set[str] = set()
    allotted_communities: set[str] = set()
    branches: set[str] = set()

    # (college_code, branch_code, allotted_community) -> aggregates
    agg: dict[tuple[int, str, str], dict] = {}

    for page_text in extract_pages(pdf_path, page_limit):
        for raw_line in (page_text or "").splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            match = ROW_RE.match(line)
            if not match:
                if not is_boilerplate(line):
                    unmatched += 1
                    if len(unmatched_samples) < 25:
                        unmatched_samples.append(line)
                continue

            rows += 1
            community = match.group("community")
            allotted = match.group("allotted")
            branch = match.group("branch")
            college = int(match.group("college"))
            rank = int(match.group("rank"))
            mark = float(match.group("mark"))

            communities.add(community)
            allotted_communities.add(allotted)
            branches.add(branch)

            key = (college, branch, allotted)
            entry = agg.get(key)
            if entry is None:
                agg[key] = {
                    "college_code": college,
                    "branch_code": branch,
                    "community": allotted,
                    "round": round_no,
                    "opening_rank": rank,
                    "closing_rank": rank,
                    "opening_mark": mark,
                    "closing_mark": mark,
                    "seats_allotted": 1,
                }
            else:
                if rank < entry["opening_rank"]:
                    entry["opening_rank"] = rank
                if rank > entry["closing_rank"]:
                    entry["closing_rank"] = rank
                if mark > entry["opening_mark"]:
                    entry["opening_mark"] = mark
                if mark < entry["closing_mark"]:
                    entry["closing_mark"] = mark
                entry["seats_allotted"] += 1

    return {
        "round": round_no,
        "source_url": SOURCE_URL_TEMPLATE.format(round=round_no),
        "source_file": pdf_path.name,
        "rows_parsed": rows,
        "unmatched_lines": unmatched,
        "unmatched_samples": unmatched_samples,
        "distinct_candidate_communities": sorted(communities),
        "distinct_allotted_communities": sorted(allotted_communities),
        "distinct_branch_codes": sorted(branches),
        "records": list(agg.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", default="1,2,3", help="comma separated round numbers")
    parser.add_argument("--pages", type=int, default=None, help="limit pages (smoke test)")
    parser.add_argument("--out", default=None, help="output JSON path")
    args = parser.parse_args()

    rounds = [int(r) for r in args.rounds.split(",") if r.strip()]

    all_records: list[dict] = []
    round_reports = []

    for round_no in rounds:
        report = parse_round(round_no, args.pages)
        all_records.extend(report.pop("records"))
        round_reports.append(report)
        print(
            f"Round {round_no}: rows={report['rows_parsed']:,} "
            f"unmatched={report['unmatched_lines']:,} "
            f"allotted_communities={report['distinct_allotted_communities']}",
            file=sys.stderr,
        )
        if report["unmatched_samples"]:
            print("  unmatched samples:", file=sys.stderr)
            for sample in report["unmatched_samples"][:10]:
                print(f"    | {sample}", file=sys.stderr)

    payload = {
        "meta": {
            "dataset": "TNEA 2026 general academic round-wise allotment cutoffs",
            "publisher": "Directorate of Technical Education (DoTE), Tamil Nadu",
            "admission_year": 2026,
            "stream": "general academic (B.E./B.Tech)",
            "derivation": (
                "Opening/closing ranks and marks were computed directly from the "
                "official per-candidate provisional allotment lists. closing_rank "
                "is the numerically largest TNEA rank allotted to that "
                "college+branch+community in that round; closing_mark is the "
                "lowest aggregate mark allotted."
            ),
            "rounds": round_reports,
        },
        "records": all_records,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUT_DIR / "tnea_2026_cutoffs.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {len(all_records):,} aggregated records -> {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
