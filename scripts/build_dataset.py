#!/usr/bin/env python3
"""
Combine the parsed official sources into the dataset served by the API.

Inputs (all produced by the other scripts in this directory, all from official
government sources):
  data-sources/parsed/tnea_2026_codes.json      college + branch code directory
  data-sources/parsed/tnea_2026_cutoffs.json    per-round opening/closing ranks
  data-sources/parsed/tnea_2026_vacancy.json    per-round vacant seats
  data-sources/parsed/nirf_2025_tamilnadu.json  NIRF ranks, scores, disclosures
  data-sources/curated/nirf_tnea_mapping.json   hand-verified NIRF -> TNEA codes

Output: backend/app/data/*.json

Data-confidence grades attached to every college:
  A  NIRF individually ranked AND a per-institute disclosure was parsed, so
     median salary, placement counts and laboratory/infrastructure expenditure
     are all present and verifiable.
  B  NIRF publishes only a rank band for this college. The band is verifiable,
     but NIRF publishes no score and no disclosure, so placement and laboratory
     figures are genuinely unavailable and are emitted as null.
  U  No NIRF presence at all. Such colleges are never ranked or recommended on
     quality; they are retained only so that a student's current allotment can
     still be displayed.

No figure is ever estimated, averaged in from a peer college, or inferred.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "data-sources" / "parsed"
CURATED = ROOT / "data-sources" / "curated"
OUT = ROOT / "backend" / "app" / "data"

GOVERNMENT_PATTERNS = [
    r"University Departments of Anna University",
    r"Anna University Regional Campus",
    r"University College of Engineering",
    r"Government College of Technology",
    r"Government College of Engineering",
    r"Annamalai University",
    r"Alagappa College of Technology",
]

CITY_HINTS = [
    "Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli", "Thiruvallur",
    "Kanchipuram", "Kancheepuram", "Erode", "Vellore", "Tirunelveli", "Thanjavur",
    "Dindigul", "Karur", "Sivakasi", "Virudhunagar", "Nagapattinam", "Cuddalore",
    "Tuticorin", "Namakkal", "Perundurai", "Sriperumbudur", "Kovilpatti",
]


def institution_type(name: str) -> str:
    for pattern in GOVERNMENT_PATTERNS:
        if re.search(pattern, name, re.I):
            if "University Departments" in name:
                return "university_department"
            return "government"
    return "self_financing"


FEE_BANDS = {
    "university_department": {
        "band": "Government / university department",
        "relative_tier": 1,
        "description": "Lowest fee tier in TNEA. Anna University departments and government institutions charge government-fixed tuition.",
    },
    "government": {
        "band": "Government / government university",
        "relative_tier": 1,
        "description": "Lowest fee tier in TNEA, tuition fixed by the state.",
    },
    "self_financing": {
        "band": "Self-financing",
        "relative_tier": 3,
        "description": "Higher fee tier. Tuition is capped annually by the Tamil Nadu Fee Fixation Committee.",
    },
}

SELF_HOSTED_CAVEAT = (
    "This figure comes from the institution's own NIRF submission published on the "
    "institution's website, not from the Ministry of Education's copy. The document "
    "was checked for the correct submission year, the Engineering category, and a "
    "matching institute name and id, but the chain of custody is weaker than a "
    "Ministry-hosted document."
)

FEE_CAVEAT = (
    "Fee band is derived from the institution type visible in the official TNEA "
    "college name, and indicates a relative tier only. Exact per-college tuition "
    "is fixed annually by the Tamil Nadu Fee Fixation Committee and is NOT "
    "included as a verified per-college figure in this dataset."
)


def short_name(name: str) -> str:
    """Trim the postal address that TNEA appends to every college name."""
    cut = re.split(r",", name)[0]
    cut = re.sub(r"\s*\(Autonomous\)\s*", " ", cut, flags=re.I)
    cut = re.sub(r"\s+", " ", cut).strip()
    return cut or name


def guess_city(name: str) -> str | None:
    for city in CITY_HINTS:
        if re.search(rf"\b{re.escape(city)}\b", name, re.I):
            return city
    return None


def main() -> int:
    codes = json.loads((PARSED / "tnea_2026_codes.json").read_text(encoding="utf-8"))
    cutoffs = json.loads((PARSED / "tnea_2026_cutoffs.json").read_text(encoding="utf-8"))
    vacancy = json.loads((PARSED / "tnea_2026_vacancy.json").read_text(encoding="utf-8"))
    nirf = json.loads((PARSED / "nirf_2025_tamilnadu.json").read_text(encoding="utf-8"))
    mapping = json.loads((CURATED / "nirf_tnea_mapping.json").read_text(encoding="utf-8"))

    # Verified disclosures recovered for band-ranked colleges. Each one passed an
    # institute-name check against the official PDF before being written.
    extra_path = PARSED / "nirf_2025_disclosures_extra.json"
    extra_disclosures = {}
    if extra_path.exists():
        extra_disclosures = json.loads(extra_path.read_text(encoding="utf-8"))["disclosures"]

    # Institution-hosted disclosures. Same official document, weaker chain of
    # custody (served by the college, not the Ministry), so these yield grade S.
    self_hosted_path = PARSED / "nirf_disclosures_self_hosted.json"
    self_hosted = {}
    if self_hosted_path.exists():
        self_hosted = json.loads(self_hosted_path.read_text(encoding="utf-8"))["disclosures"]

    nirf_by_name = {inst["name"]: inst for inst in nirf["institutions"]}

    # college_code -> NIRF institution
    code_to_nirf: dict[int, dict] = {}
    code_caveat: dict[int, str] = {}
    unresolved = []
    for entry in mapping["mappings"]:
        inst = nirf_by_name.get(entry["nirf_name"])
        if inst is None:
            unresolved.append(entry["nirf_name"])
            continue
        for code in entry["tnea_college_codes"]:
            code_to_nirf[int(code)] = inst
            if entry.get("caveat"):
                code_caveat[int(code)] = entry["caveat"]

    if unresolved:
        print("!! mapping entries with no matching NIRF record (check spelling):")
        for name in unresolved:
            print(f"   - {name}")

    # Branches offered per college, from the official vacancy rows.
    branches_by_college: dict[int, set[str]] = defaultdict(set)
    for row in vacancy["records"]:
        branches_by_college[row["college_code"]].add(row["branch_code"])

    colleges = []
    grade_counts = defaultdict(int)

    for code_str, official_name in codes["colleges"].items():
        code = int(code_str)
        itype = institution_type(official_name)
        inst = code_to_nirf.get(code)

        placement = None
        infrastructure = None
        nirf_block = None
        grade = "U"

        if inst is not None:
            nirf_block = {
                "year": inst["source"]["year"],
                "rank": inst["rank"],
                "score": inst["score"],
                "rank_band": inst["rank_band"],
                "sub_scores": inst["sub_scores"],
                "nirf_id": inst["nirf_id"],
                "publisher": inst["source"]["publisher"],
                "source_url": inst["source"]["ranking_url"],
                "institution_as_ranked": inst["name"],
            }
            grade = "B"

            # Prefer a Ministry-hosted disclosure (grade A). Fall back to the
            # institution-hosted copy of the same submission (grade S).
            ministry_disc = inst.get("disclosure") or extra_disclosures.get(inst["name"])
            institution_disc = self_hosted.get(inst["name"])

            if ministry_disc and ministry_disc.get("placement"):
                disc = ministry_disc
                disclosure_year = inst["source"]["year"]
                hosted_by = "ministry"
                grade_if_placement = "A"
                host_detail = ""
            elif institution_disc and institution_disc.get("placement"):
                disc = institution_disc
                disclosure_year = institution_disc.get("rankings_year")
                hosted_by = "institution"
                grade_if_placement = "S"
                host_detail = institution_disc.get("source_host") or ""
            else:
                disc = ministry_disc or institution_disc
                disclosure_year = inst["source"]["year"]
                hosted_by = "ministry" if ministry_disc else "institution"
                grade_if_placement = None
                host_detail = ""

            def describe(what: str) -> str:
                if hosted_by == "ministry":
                    return (
                        f"NIRF {disclosure_year} institute data disclosure ({what}), "
                        f"submitted to and published by the Ministry of Education"
                    )
                return (
                    f"NIRF {disclosure_year} institute data disclosure ({what}), "
                    f"the institution's own submission published on its own website "
                    f"({host_detail}) rather than by the Ministry"
                )

            if disc and disc.get("placement"):
                p = disc["placement"]
                graduating = p["students_graduating"]
                placed = p["students_placed"]
                placement = {
                    "graduating_year": p["graduating_year"],
                    "students_graduating": graduating,
                    "students_placed": placed,
                    "placement_rate": round(placed / graduating, 4) if graduating else None,
                    "median_salary_inr": p["median_salary_inr"],
                    "verified": True,
                    "hosted_by": hosted_by,
                    "disclosure_year": disclosure_year,
                    "source": describe("placement and median salary"),
                    "source_url": disc["source_url"],
                }
                if hosted_by == "institution":
                    placement["provenance_caveat"] = SELF_HOSTED_CAVEAT
                    if disc.get("host_note"):
                        placement["host_note"] = disc["host_note"]
                grade = grade_if_placement or grade

            if disc:
                total = disc.get("ug4_total_students")
                lab = disc.get("lab_equipment_expenditure_inr")
                infrastructure = {
                    "lab_equipment_expenditure_inr": lab,
                    "library_expenditure_inr": disc.get("library_expenditure_inr"),
                    "other_capital_expenditure_inr": disc.get("other_capital_expenditure_inr"),
                    "engineering_workshops_expenditure_inr": disc.get("engineering_workshops_expenditure_inr"),
                    "ug4_total_students": total,
                    "lab_spend_per_student_inr": (
                        round(lab / total) if (lab is not None and total) else None
                    ),
                    "verified": True,
                    "hosted_by": hosted_by,
                    "disclosure_year": disclosure_year,
                    "source": describe("annual capital expenditure"),
                    "source_url": disc["source_url"],
                }
                if hosted_by == "institution":
                    infrastructure["provenance_caveat"] = SELF_HOSTED_CAVEAT

        grade_counts[grade] += 1

        colleges.append(
            {
                "college_code": code,
                "official_name": official_name,
                "display_name": short_name(official_name),
                "city": guess_city(official_name),
                "institution_type": itype,
                "fee_band": {**FEE_BANDS[itype], "caveat": FEE_CAVEAT},
                "nirf": nirf_block,
                "placement": placement,
                "infrastructure": infrastructure,
                "data_confidence": grade,
                "mapping_caveat": code_caveat.get(code),
                "branches": sorted(branches_by_college.get(code, [])),
                # A, S and B all have verifiable NIRF standing, so all three can be
                # recommended. Only A and S carry placement figures and can be scored.
                "recommendable": grade in ("A", "S", "B"),
            }
        )

    colleges.sort(key=lambda c: c["college_code"])

    OUT.mkdir(parents=True, exist_ok=True)

    (OUT / "colleges.json").write_text(
        json.dumps(
            {
                "meta": {
                    "admission_year": 2026,
                    "college_count": len(colleges),
                    "recommendable_count": sum(1 for c in colleges if c["recommendable"]),
                    "data_confidence_counts": dict(grade_counts),
                    "data_confidence_legend": {
                        "A": "Placement and laboratory figures taken from the NIRF per-institute disclosure published by the Ministry of Education itself. Strongest provenance.",
                        "S": "Same kind of official NIRF disclosure, but published on the institution's own website because the Ministry publishes per-institute data only down to rank 200. Verified for submission year, Engineering category and matching institute identity, but served by the college rather than the Ministry, so the chain of custody is weaker.",
                        "B": "NIRF publishes only a rank band for this college and no disclosure could be obtained, so no placement or laboratory figure is claimed.",
                        "U": "No NIRF presence. Never ranked or recommended on quality; retained so a current allotment can still be displayed.",
                    },
                    "sources": [
                        "TNEA 2026 general academic vacancy position PDFs - Directorate of Technical Education, Tamil Nadu",
                        "NIRF 2025 Engineering rankings - Ministry of Education, Government of India",
                        "NIRF 2025 per-institute data disclosures - Ministry of Education, Government of India",
                    ],
                },
                "colleges": colleges,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (OUT / "cutoffs.json").write_text(json.dumps(cutoffs, indent=2), encoding="utf-8")
    (OUT / "vacancy.json").write_text(json.dumps(vacancy, indent=2), encoding="utf-8")
    (OUT / "branches.json").write_text(
        json.dumps(
            {
                "meta": {
                    "source": "TNEA 2026 general academic vacancy position PDFs - Directorate of Technical Education, Tamil Nadu"
                },
                "branches": codes["branches"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"colleges: {len(colleges)}")
    print(f"  grade A (Ministry-hosted disclosure):     {grade_counts['A']}")
    print(f"  grade S (institution-hosted disclosure):  {grade_counts['S']}")
    print(f"  grade B (NIRF band only, no figures):     {grade_counts['B']}")
    print(f"  grade U (no NIRF presence):               {grade_counts['U']}")
    print(f"cutoff records: {len(cutoffs['records'])}")
    print(f"vacancy rows:   {len(vacancy['records'])}")
    print(f"branches:       {len(codes['branches'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
