#!/usr/bin/env python3
"""
Match NIRF Tamil Nadu institutions to official TNEA college codes.

This is the step where an error would silently attach one college's placement
record to a different college, so the matching is deliberately conservative:

  * Names are compared on their DISTINCTIVE tokens only. Generic words that
    almost every engineering college shares ("college", "institute",
    "engineering", "technology", ...) are ignored, because they create false
    confidence.
  * A match additionally requires the NIRF-reported city to appear in the TNEA
    record, since TNEA names embed the full postal address.
  * Every candidate is printed with its score so the mapping can be reviewed by
    a human instead of being trusted blindly.
  * An institution with no confident TNEA match is reported as unmatched. That
    is the expected and correct outcome for deemed universities (VIT, SRM,
    Amrita, SASTRA, ...) which do not admit through TNEA at all.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PARSED = Path(__file__).resolve().parent.parent / "data-sources" / "parsed"

GENERIC = {
    "college",
    "institute",
    "institutes",
    "institution",
    "engineering",
    "technology",
    "technologies",
    "science",
    "sciences",
    "research",
    "advanced",
    "studies",
    "university",
    "autonomous",
    "of",
    "and",
    "the",
    "for",
    "campus",
    "school",
    "academy",
    "education",
    "educational",
    "applied",
    "deemed",
    "be",
    "to",
    "dr",
    "sri",
    "shri",
    "sree",
    "st",
    "co",
    "ed",
}

CITY_ALIASES = {
    "chennai": {"chennai", "kanchipuram", "kancheepuram", "chengalpattu", "thiruvallur", "tiruvallur"},
    "kancheepuram": {"kancheepuram", "kanchipuram", "chennai", "chengalpattu"},
    "thiruvallur": {"thiruvallur", "tiruvallur", "chennai"},
    "coimbatore": {"coimbatore"},
    "sriperumbudur": {"sriperumbudur", "kanchipuram", "kancheepuram", "chennai"},
    "perundurai": {"perundurai", "erode"},
    "samayapuram": {"samayapuram", "tiruchirappalli", "trichy"},
    "krishnan koil": {"krishnankoil", "virudhunagar", "srivilliputhur"},
}


def normalise(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def tokens(text: str) -> set[str]:
    return {t for t in normalise(text).split() if t not in GENERIC and len(t) > 1}


def city_tokens(city: str | None) -> set[str]:
    if not city:
        return set()
    key = normalise(city)
    aliases = CITY_ALIASES.get(key)
    if aliases:
        return aliases
    return {t for t in key.split() if len(t) > 2}


def main() -> int:
    codes = json.loads((PARSED / "tnea_2026_codes.json").read_text(encoding="utf-8"))
    nirf = json.loads((PARSED / "nirf_2025_tamilnadu.json").read_text(encoding="utf-8"))

    tnea = {int(code): name for code, name in codes["colleges"].items()}
    tnea_tokens = {code: tokens(name) for code, name in tnea.items()}
    tnea_norm = {code: normalise(name) for code, name in tnea.items()}

    matched: list[dict] = []
    unmatched: list[dict] = []

    for inst in nirf["institutions"]:
        want = tokens(inst["name"])
        if not want:
            continue
        cities = city_tokens(inst.get("city"))

        scored = []
        for code, have in tnea_tokens.items():
            overlap = want & have
            score = len(overlap) / len(want)
            if score < 0.6:
                continue
            city_ok = (not cities) or bool(cities & set(tnea_norm[code].split()))
            scored.append((score, city_ok, code))

        scored.sort(key=lambda t: (t[1], t[0]), reverse=True)
        confident = [s for s in scored if s[0] >= 0.8 and s[1]]

        entry = {
            "nirf_name": inst["name"],
            "nirf_city": inst.get("city"),
            "nirf_rank": inst.get("rank"),
            "nirf_band": inst.get("rank_band"),
            "candidates": [
                {
                    "college_code": code,
                    "tnea_name": tnea[code],
                    "token_score": round(score, 3),
                    "city_match": city_ok,
                }
                for score, city_ok, code in scored[:5]
            ],
        }
        if confident:
            matched.append(entry)
        else:
            unmatched.append(entry)

    print("=" * 78)
    print("CONFIDENT MATCHES (review each one)")
    print("=" * 78)
    for entry in matched:
        label = f"rank {entry['nirf_rank']}" if entry["nirf_rank"] else f"band {entry['nirf_band']}"
        print(f"\nNIRF: {entry['nirf_name']} ({entry['nirf_city']}, {label})")
        for cand in entry["candidates"]:
            flag = "OK " if cand["token_score"] >= 0.8 and cand["city_match"] else "   "
            print(
                f"  {flag} score={cand['token_score']:<6} city={str(cand['city_match']):<5} "
                f"[{cand['college_code']}] {cand['tnea_name'][:78]}"
            )

    print("\n" + "=" * 78)
    print("NO CONFIDENT TNEA MATCH (expected for non-TNEA deemed universities)")
    print("=" * 78)
    for entry in unmatched:
        label = f"rank {entry['nirf_rank']}" if entry["nirf_rank"] else f"band {entry['nirf_band']}"
        print(f"\nNIRF: {entry['nirf_name']} ({entry['nirf_city']}, {label})")
        for cand in entry["candidates"][:3]:
            print(
                f"      score={cand['token_score']:<6} city={str(cand['city_match']):<5} "
                f"[{cand['college_code']}] {cand['tnea_name'][:70]}"
            )

    print(f"\n\nSummary: {len(matched)} matched, {len(unmatched)} unmatched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
