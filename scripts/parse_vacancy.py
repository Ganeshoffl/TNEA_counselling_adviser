#!/usr/bin/env python3
"""
Parse the official TNEA 2026 GENERAL ACADEMIC "vacancy position after round N"
PDFs published by the Directorate of Technical Education (DoTE), Tamil Nadu.

Source PDFs (official):
  https://static.tneaonline.org/docs/TNEA-2026-GENERAL-ACADEMIC-VACANCY-POSITION-AFTER-ROUND-{N}.pdf

These files are the authoritative mapping of TNEA college codes and branch codes
to their official names, and they report the seats still vacant per community
after each counselling round.

Two correctness details that this parser handles explicitly:

1. The community column order is NOT constant across files. Round 1 and 2 print
   "OC BC BCM MBC SC SCA ST" while Round 3 prints "OC BCM BC MBC SCA SC ST".
   The order is therefore read from each page's own header row rather than
   assumed, so columns can never be silently transposed.

2. College and branch names wrap across several physical lines. The PDFs contain
   ruled table borders, so table extraction is used to recover whole cells
   instead of reconstructing wrapped text by guesswork.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pdfplumber

RAW_DIR = Path(__file__).resolve().parent.parent / "data-sources" / "raw"
OUT_DIR = Path(__file__).resolve().parent.parent / "data-sources" / "parsed"

FILENAME_TEMPLATE = "TNEA-2026-GENERAL-ACADEMIC-VACANCY-POSITION-AFTER-ROUND-{round}.pdf"
SOURCE_URL_TEMPLATE = (
    "https://static.tneaonline.org/docs/"
    "TNEA-2026-GENERAL-ACADEMIC-VACANCY-POSITION-AFTER-ROUND-{round}.pdf"
)

COMMUNITIES = {"OC", "BC", "BCM", "MBC", "SC", "SCA", "ST"}

HEADER_TOKENS = {"COLLEGECODE", "COLLEGENAME", "BRANCHCODE", "BRANCHNAME"}


def norm(cell: str | None) -> str:
    """Collapse all whitespace in a table cell to single spaces."""
    if cell is None:
        return ""
    return " ".join(str(cell).split())


def is_header_row(cells: list[str]) -> bool:
    compact = {c.replace(" ", "").upper() for c in cells if c}
    return bool(HEADER_TOKENS & compact)


def community_order(cells: list[str]) -> list[str] | None:
    """Extract the community column order from a header row."""
    order = [c.strip().upper() for c in cells if c.strip().upper() in COMMUNITIES]
    if len(order) == len(COMMUNITIES) and len(set(order)) == len(COMMUNITIES):
        return order
    return None


def parse_round(round_no: int, page_limit: int | None = None) -> dict:
    pdf_path = RAW_DIR / FILENAME_TEMPLATE.format(round=round_no)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing source PDF: {pdf_path}")

    college_names: dict[int, Counter] = defaultdict(Counter)
    branch_names: dict[str, Counter] = defaultdict(Counter)
    vacancy: dict[tuple[int, str], dict[str, int]] = {}

    header_orders: Counter = Counter()
    current_order: list[str] | None = None
    data_rows = 0
    skipped_rows = 0
    skipped_samples: list[list[str]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        pages = pdf.pages if page_limit is None else pdf.pages[:page_limit]
        for page in pages:
            table = page.extract_table()
            if not table:
                continue
            for raw_row in table:
                cells = [norm(c) for c in raw_row]

                if is_header_row(cells):
                    order = community_order(cells)
                    if order:
                        current_order = order
                        header_orders[tuple(order)] += 1
                    continue

                # Expect: college_code, college_name, branch_code, branch_name, 7 numbers
                if len(cells) < 11 or current_order is None:
                    if any(cells):
                        skipped_rows += 1
                        if len(skipped_samples) < 15:
                            skipped_samples.append(cells)
                    continue

                code_cell, college_name, branch_code, branch_name = cells[:4]
                number_cells = cells[4:11]

                # Some rows render the branch code with a leading dash artifact
                # (e.g. "- AD" instead of "AD"); strip it so the row is kept.
                branch_code = re.sub(r"^[-\u2013\u2014]\s*", "", branch_code).strip()

                if not re.fullmatch(r"\d{1,5}", code_cell):
                    if any(cells):
                        skipped_rows += 1
                        if len(skipped_samples) < 15:
                            skipped_samples.append(cells)
                    continue
                if not re.fullmatch(r"[A-Z0-9]{2,4}", branch_code.upper()):
                    skipped_rows += 1
                    if len(skipped_samples) < 15:
                        skipped_samples.append(cells)
                    continue
                if not all(re.fullmatch(r"-?\d{1,5}", n) for n in number_cells):
                    skipped_rows += 1
                    if len(skipped_samples) < 15:
                        skipped_samples.append(cells)
                    continue

                college_code = int(code_cell)
                branch_code = branch_code.upper()
                data_rows += 1

                if college_name:
                    college_names[college_code][college_name] += 1
                if branch_name:
                    branch_names[branch_code][branch_name] += 1

                seats = {
                    community: int(value)
                    for community, value in zip(current_order, number_cells)
                }
                vacancy[(college_code, branch_code)] = seats

    records = [
        {
            "college_code": college_code,
            "branch_code": branch_code,
            "round": round_no,
            "vacant_seats": seats,
            "vacant_total": sum(seats.values()),
        }
        for (college_code, branch_code), seats in sorted(vacancy.items())
    ]

    return {
        "round": round_no,
        "source_url": SOURCE_URL_TEMPLATE.format(round=round_no),
        "source_file": pdf_path.name,
        "data_rows": data_rows,
        "skipped_rows": skipped_rows,
        "skipped_samples": skipped_samples,
        "community_column_orders_seen": {
            ",".join(order): count for order, count in header_orders.items()
        },
        "records": records,
        "college_names": {
            str(code): counter.most_common(1)[0][0] for code, counter in college_names.items()
        },
        "branch_names": {
            code: counter.most_common(1)[0][0] for code, counter in branch_names.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", default="1,2,3")
    parser.add_argument("--pages", type=int, default=None)
    args = parser.parse_args()

    rounds = [int(r) for r in args.rounds.split(",") if r.strip()]

    all_vacancy: list[dict] = []
    college_votes: dict[int, Counter] = defaultdict(Counter)
    branch_votes: dict[str, Counter] = defaultdict(Counter)
    reports = []

    for round_no in rounds:
        report = parse_round(round_no, args.pages)
        all_vacancy.extend(report.pop("records"))
        for code, name in report.pop("college_names").items():
            college_votes[int(code)][name] += 1
        for code, name in report.pop("branch_names").items():
            branch_votes[code][name] += 1
        reports.append(report)
        print(
            f"Round {round_no}: data_rows={report['data_rows']:,} "
            f"skipped={report['skipped_rows']:,} "
            f"column_order={report['community_column_orders_seen']}"
        )
        for sample in report["skipped_samples"][:5]:
            print(f"    skipped | {sample}")

    colleges = {
        str(code): counter.most_common(1)[0][0] for code, counter in sorted(college_votes.items())
    }
    branches = {
        code: counter.most_common(1)[0][0] for code, counter in sorted(branch_votes.items())
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUT_DIR / "tnea_2026_vacancy.json").write_text(
        json.dumps(
            {
                "meta": {
                    "dataset": "TNEA 2026 general academic round-wise vacancy position",
                    "publisher": "Directorate of Technical Education (DoTE), Tamil Nadu",
                    "admission_year": 2026,
                    "note": (
                        "vacant_seats are the seats still unfilled after the stated "
                        "round, taken directly from the official DoTE vacancy PDFs. "
                        "Community column order is read from each page header."
                    ),
                    "rounds": reports,
                },
                "records": all_vacancy,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (OUT_DIR / "tnea_2026_codes.json").write_text(
        json.dumps(
            {
                "meta": {
                    "dataset": "TNEA 2026 official college and branch code directory",
                    "publisher": "Directorate of Technical Education (DoTE), Tamil Nadu",
                    "derived_from": "TNEA 2026 general academic vacancy position PDFs",
                },
                "colleges": colleges,
                "branches": branches,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nWrote {len(all_vacancy):,} vacancy rows")
    print(f"Wrote {len(colleges):,} college names, {len(branches):,} branch names")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
