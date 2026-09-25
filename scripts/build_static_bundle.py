#!/usr/bin/env python3
"""
Build the trimmed, static data bundle that the browser-only build of the app uses.

Why a separate bundle
---------------------
The full dataset is ~7.8 MB, which is fine for a server but wasteful to ship to a
phone. Only the 40 colleges that have verifiable NIRF standing can ever be
recommended, so cutoff and vacancy rows for the other 382 are dead weight. A
name-only index is still emitted for all 422 colleges, because a student's
CURRENT allotment can be at any college in the official TNEA list and they must
be able to find it.

Derivations stay in Python
--------------------------
Anything derived rather than read straight from source is computed here, not in
the browser, so there is exactly one implementation of it:

  * seats available BEFORE each round, including the round-1 figure that is
    reconstructed as (seats vacant after round 1 + seats allotted in round 1);
  * the lookup keys used by the engine.

The JavaScript engine therefore only scores and ranks; it never re-derives data.
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "backend" / "app" / "data"
OUT = ROOT / "frontend" / "public" / "data"

# Fields the browser needs for a recommendable college. Everything here is either
# an official figure or carries its own provenance.
COLLEGE_FIELDS = (
    "college_code",
    "official_name",
    "display_name",
    "city",
    "institution_type",
    "fee_band",
    "nirf",
    "placement",
    "infrastructure",
    "data_confidence",
    "mapping_caveat",
    "branches",
    "recommendable",
)


def key(college: int, branch: str, community: str) -> str:
    return f"{college}|{branch}|{community}"


def main() -> int:
    colleges_doc = json.loads((DATA / "colleges.json").read_text(encoding="utf-8"))
    cutoffs_doc = json.loads((DATA / "cutoffs.json").read_text(encoding="utf-8"))
    vacancy_doc = json.loads((DATA / "vacancy.json").read_text(encoding="utf-8"))
    branches_doc = json.loads((DATA / "branches.json").read_text(encoding="utf-8"))

    colleges = colleges_doc["colleges"]
    recommendable = {c["college_code"] for c in colleges if c["recommendable"]}

    # --- full records for the colleges that can be recommended -------------
    full = [
        {field: c.get(field) for field in COLLEGE_FIELDS}
        for c in colleges
        if c["recommendable"]
    ]

    # --- name-only index for every college, so a current allotment resolves --
    index = [
        {
            "college_code": c["college_code"],
            "display_name": c["display_name"],
            "official_name": c["official_name"],
            "institution_type": c["institution_type"],
            "data_confidence": c["data_confidence"],
            "recommendable": c["recommendable"],
            "branches": c.get("branches", []),
        }
        for c in colleges
    ]

    # --- cutoffs, restricted to recommendable colleges ---------------------
    cutoffs: dict[str, dict[str, dict]] = defaultdict(dict)
    allotted_round1: dict[str, int] = {}
    for rec in cutoffs_doc["records"]:
        if rec["college_code"] not in recommendable:
            continue
        k = key(rec["college_code"], rec["branch_code"], rec["community"])
        cutoffs[k][str(rec["round"])] = {
            "opening_rank": rec["opening_rank"],
            "closing_rank": rec["closing_rank"],
            "closing_mark": rec.get("closing_mark"),
            "seats_allotted": rec.get("seats_allotted"),
        }
        if rec["round"] == 1:
            allotted_round1[k] = rec.get("seats_allotted", 0)

    # --- seats available BEFORE each round (derived here, once) ------------
    vacant_after: dict[str, dict[int, int]] = defaultdict(dict)
    for rec in vacancy_doc["records"]:
        if rec["college_code"] not in recommendable:
            continue
        for community, seats in rec["vacant_seats"].items():
            vacant_after[key(rec["college_code"], rec["branch_code"], community)][
                rec["round"]
            ] = seats

    seats_before: dict[str, dict[str, int]] = {}
    for k, after in vacant_after.items():
        before: dict[str, int] = {}
        if 1 in after:
            # Reconstruction by exact arithmetic on two official figures.
            before["1"] = after[1] + allotted_round1.get(k, 0)
            before["2"] = after[1]
        if 2 in after:
            before["3"] = after[2]
        if 3 in after:
            before["4"] = after[3]
        if before:
            seats_before[k] = before

    meta = {
        **{k: v for k, v in colleges_doc["meta"].items()},
        "bundle": {
            "purpose": "Trimmed dataset for the browser-only build.",
            "colleges_with_full_records": len(full),
            "colleges_in_name_index": len(index),
            "note": (
                "Cutoff and seat rows are included only for colleges that can be "
                "recommended. All 422 official TNEA colleges appear in the name index "
                "so that any current allotment can be identified and displayed."
            ),
            "seats_before_round_derivation": (
                "Seats available before round N are the seats vacant after round N-1, "
                "as published by DoTE. The pre-round-1 figure is reconstructed as "
                "(seats vacant after round 1 + seats allotted in round 1), because no "
                "2026 pre-round seat matrix is published."
            ),
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    artefacts = {
        "meta.json": meta,
        "colleges.json": full,
        "college-index.json": index,
        "cutoffs.json": cutoffs,
        "seats.json": seats_before,
        "branches.json": branches_doc["branches"],
    }

    total_raw = total_gz = 0
    for name, obj in artefacts.items():
        raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        (OUT / name).write_bytes(raw)
        gz = len(gzip.compress(raw, 9))
        total_raw += len(raw)
        total_gz += gz
        print(f"  {name:<20} {len(raw)/1024:>8.0f} KB raw  {gz/1024:>7.0f} KB gzipped")

    print(f"  {'TOTAL':<20} {total_raw/1024:>8.0f} KB raw  {total_gz/1024:>7.0f} KB gzipped")
    print(f"\nWrote {len(artefacts)} files -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
