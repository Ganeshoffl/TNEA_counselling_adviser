#!/usr/bin/env python3
"""
Parse the institution-hosted NIRF Engineering disclosures discovered by
scripts/discover_self_hosted.py into placement and laboratory/infrastructure
figures.

The extraction logic is shared with the Ministry-hosted path (parse_nirf.py), so
the same fields are read the same way. What differs is only the provenance, which
is recorded on every field: these documents are the institution's own NIRF
submission but are served by the institution rather than by the Ministry of
Education. Everything derived here is therefore graded S, never A.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_nirf import parse_disclosure  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data-sources" / "raw" / "self_hosted"
PARSED = ROOT / "data-sources" / "parsed"


def main() -> int:
    sources_doc = json.loads((PARSED / "self_hosted_sources.json").read_text(encoding="utf-8"))
    sources = sources_doc["sources"]

    out: dict[str, dict] = {}
    failures: list[dict] = []

    for college, meta in sources.items():
        pdf_path = RAW / meta["local_file"]
        if not pdf_path.exists():
            failures.append({"college": college, "reason": f"missing local file {meta['local_file']}"})
            continue
        try:
            parsed = parse_disclosure(pdf_path)
        except Exception as exc:  # noqa: BLE001
            failures.append({"college": college, "reason": f"parse failed: {exc}"})
            continue

        if not parsed.get("placement"):
            failures.append(
                {
                    "college": college,
                    "reason": "no UG 4-year placement table could be read from the disclosure",
                }
            )
            print(f"NO PLACEMENT  {college[:50]:<50} {meta['institute_id']}")
            continue

        parsed["source_url"] = meta["source_url"]
        parsed["source_host"] = meta["source_host"]
        parsed["rankings_year"] = meta["rankings_year"]
        parsed["verified_institute_name"] = meta["institute_name_in_pdf"]
        parsed["verified_institute_id"] = meta["institute_id"]
        parsed["provenance"] = "self_hosted_by_institution"
        parsed["host_note"] = meta.get("host_note")
        out[college] = parsed

        median = (parsed["placement"] or {}).get("median_salary_inr")
        print(
            f"OK            {college[:50]:<50} {meta['institute_id']:<14} "
            f"NIRF {meta['rankings_year']}  median={median}  lab={parsed['lab_equipment_expenditure_inr']}"
        )

    payload = {
        "meta": {
            "dataset": "Institution-hosted NIRF Engineering disclosures, parsed",
            "publisher_of_document": "National Institutional Ranking Framework (NIRF), Ministry of Education, Government of India",
            "served_by": "the institution's own website (not the Ministry CDN)",
            "confidence_grade": "S",
            "provenance_warning": (
                "These are the institutions' own NIRF submissions, but they are served "
                "by the institutions rather than by the Ministry of Education. The "
                "document content was verified (correct submission year, Engineering "
                "category, and matching institute name and id), but the chain of custody "
                "is weaker than a Ministry-hosted copy, so this data is graded S and is "
                "never presented as Ministry-hosted."
            ),
            "parsed_count": len(out),
            "failures": failures,
        },
        "disclosures": out,
    }

    dest = PARSED / "nirf_disclosures_self_hosted.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nparsed={len(out)} failures={len(failures)} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
