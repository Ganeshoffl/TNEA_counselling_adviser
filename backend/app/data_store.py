"""
Loads the official TNEA + NIRF dataset and builds the lookup indices the
recommendation engine needs.

All data originates from the government sources documented in README.md. This
module performs no estimation: it only indexes, and derives quantities that are
exact arithmetic on official figures (see derived_initial_seats below).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"

COMMUNITIES = ["OC", "BC", "BCM", "MBC", "SC", "SCA", "ST"]

# The official TNEA 2026 general academic counselling published three rounds.
# Round 4 is offered by this tool as a forward-looking simulation only.
ROUNDS_WITH_OFFICIAL_DATA = [1, 2, 3]
SUPPORTED_ROUNDS = [1, 2, 3, 4]


def _percentile_bounds(values: list[float], low: float = 0.05, high: float = 0.95) -> tuple[float, float]:
    """Robust min/max so a single outlier cannot flatten the whole scale."""
    if not values:
        return (0.0, 1.0)
    ordered = sorted(values)
    if len(ordered) == 1:
        return (ordered[0], ordered[0] + 1e-9)
    lo = ordered[max(0, int(len(ordered) * low) - 1)]
    hi = ordered[min(len(ordered) - 1, int(math.ceil(len(ordered) * high)) - 1)]
    if hi <= lo:
        lo, hi = ordered[0], ordered[-1]
    if hi <= lo:
        hi = lo + 1e-9
    return (lo, hi)


def normalise(value: float | None, bounds: tuple[float, float]) -> float | None:
    if value is None:
        return None
    lo, hi = bounds
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


@dataclass
class Norms:
    """Normalisation bounds computed across the recommendable college cohort."""

    median_salary: tuple[float, float] = (0.0, 1.0)
    placement_rate: tuple[float, float] = (0.0, 1.0)
    lab_per_student_log: tuple[float, float] = (0.0, 1.0)
    infra_per_student_log: tuple[float, float] = (0.0, 1.0)
    nirf_position: tuple[float, float] = (1.0, 300.0)
    fee_tier: tuple[float, float] = (1.0, 3.0)


@dataclass
class DataStore:
    colleges_meta: dict[str, Any] = field(default_factory=dict)
    colleges: dict[int, dict] = field(default_factory=dict)
    branches: dict[str, str] = field(default_factory=dict)

    # (college, branch, community) -> {round: record}
    cutoffs: dict[tuple[int, str, str], dict[int, dict]] = field(default_factory=dict)
    # (college, branch, community) -> {round: seats available BEFORE that round}
    seats_before_round: dict[tuple[int, str, str], dict[int, int]] = field(default_factory=dict)
    # college -> sorted branch codes
    branches_by_college: dict[int, list[str]] = field(default_factory=dict)

    norms: Norms = field(default_factory=Norms)
    sources: dict[str, Any] = field(default_factory=dict)

    # ---------- lookups ----------

    def college(self, code: int) -> dict | None:
        return self.colleges.get(code)

    def branch_name(self, code: str) -> str:
        return self.branches.get(code, code)

    def recommendable_colleges(self) -> list[dict]:
        return [c for c in self.colleges.values() if c.get("recommendable")]

    def cutoff_for(self, college: int, branch: str, community: str) -> dict[int, dict]:
        return self.cutoffs.get((college, branch, community), {})

    def seats_available(self, college: int, branch: str, community: str, target_round: int) -> int | None:
        by_round = self.seats_before_round.get((college, branch, community))
        if not by_round:
            return None
        return by_round.get(target_round)

    def reference_cutoff(
        self, college: int, branch: str, community: str, target_round: int
    ) -> tuple[dict | None, int | None]:
        """
        Pick the closing-rank record that best represents what it takes to be
        allotted this seat in `target_round`.

        Preference order:
          1. the same round, when TNEA actually published it (same-year, same-round
             evidence is the strongest signal available);
          2. otherwise the latest earlier round, because closing ranks drift to
             larger (weaker) values as rounds progress;
          3. otherwise the earliest later round.
        The round actually used is returned so the UI can state it.
        """
        by_round = self.cutoffs.get((college, branch, community))
        if not by_round:
            return None, None
        if target_round in by_round:
            return by_round[target_round], target_round
        earlier = [r for r in by_round if r < target_round]
        if earlier:
            r = max(earlier)
            return by_round[r], r
        r = min(by_round)
        return by_round[r], r


def _nirf_position(college: dict) -> float | None:
    """
    Map NIRF standing onto a comparable 'position' number (smaller is better).

    A ranked institute uses its published rank. A band-ranked institute has no
    published rank, so the midpoint of its band is used. That midpoint is an
    approximation of standing within the band and is labelled as such wherever it
    is surfaced; it is never presented as a published rank.
    """
    nirf = college.get("nirf")
    if not nirf:
        return None
    if nirf.get("rank"):
        return float(nirf["rank"])
    band = nirf.get("rank_band")
    midpoints = {"101-150": 125.5, "151-200": 175.5, "201-300": 250.5}
    return midpoints.get(band)


def _infra_per_student(college: dict) -> float | None:
    infra = college.get("infrastructure")
    if not infra:
        return None
    total_students = infra.get("ug4_total_students")
    if not total_students:
        return None
    parts = [
        infra.get("lab_equipment_expenditure_inr"),
        infra.get("library_expenditure_inr"),
        infra.get("other_capital_expenditure_inr"),
        infra.get("engineering_workshops_expenditure_inr"),
    ]
    present = [p for p in parts if p is not None]
    if not present:
        return None
    return sum(present) / total_students


def _lab_per_student(college: dict) -> float | None:
    infra = college.get("infrastructure")
    if not infra:
        return None
    return infra.get("lab_spend_per_student_inr")


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    store = DataStore()

    colleges_doc = json.loads((DATA_DIR / "colleges.json").read_text(encoding="utf-8"))
    store.colleges_meta = colleges_doc["meta"]
    store.colleges = {c["college_code"]: c for c in colleges_doc["colleges"]}

    branches_doc = json.loads((DATA_DIR / "branches.json").read_text(encoding="utf-8"))
    store.branches = branches_doc["branches"]

    cutoffs_doc = json.loads((DATA_DIR / "cutoffs.json").read_text(encoding="utf-8"))
    vacancy_doc = json.loads((DATA_DIR / "vacancy.json").read_text(encoding="utf-8"))

    cutoffs: dict[tuple[int, str, str], dict[int, dict]] = defaultdict(dict)
    for rec in cutoffs_doc["records"]:
        key = (rec["college_code"], rec["branch_code"], rec["community"])
        cutoffs[key][rec["round"]] = rec
    store.cutoffs = dict(cutoffs)

    # Seats still vacant after each published round, per community.
    vacant_after: dict[tuple[int, str, str], dict[int, int]] = defaultdict(dict)
    branches_by_college: dict[int, set[str]] = defaultdict(set)
    for rec in vacancy_doc["records"]:
        college, branch, rnd = rec["college_code"], rec["branch_code"], rec["round"]
        branches_by_college[college].add(branch)
        for community, seats in rec["vacant_seats"].items():
            vacant_after[(college, branch, community)][rnd] = seats

    store.branches_by_college = {c: sorted(b) for c, b in branches_by_college.items()}

    # Seats available BEFORE a given round.
    #
    # TNEA publishes "vacancy position after round N", so the seats a candidate
    # competes for in round N+1 are exactly the seats vacant after round N.
    #
    # For round 1 there is no published pre-round-1 matrix for 2026 (the only
    # seat-matrix PDF still online is a 2023 file). The pre-round-1 figure is
    # therefore DERIVED by exact arithmetic on two official numbers:
    #     seats before round 1 = seats vacant after round 1
    #                          + seats actually allotted in round 1
    # This is reconstruction from official data, not estimation.
    seats_before: dict[tuple[int, str, str], dict[int, int]] = defaultdict(dict)
    for key, after in vacant_after.items():
        allotted_r1 = 0
        rec = cutoffs.get(key, {}).get(1)
        if rec:
            allotted_r1 = rec.get("seats_allotted", 0)
        if 1 in after:
            seats_before[key][1] = after[1] + allotted_r1
            seats_before[key][2] = after[1]
        if 2 in after:
            seats_before[key][3] = after[2]
        if 3 in after:
            seats_before[key][4] = after[3]
    store.seats_before_round = dict(seats_before)

    # Normalisation bounds over the recommendable cohort only.
    pool = store.recommendable_colleges()
    salaries, rates, labs, infras, positions, fees = [], [], [], [], [], []
    for c in pool:
        placement = c.get("placement")
        if placement:
            if placement.get("median_salary_inr"):
                salaries.append(float(placement["median_salary_inr"]))
            if placement.get("placement_rate") is not None:
                rates.append(float(placement["placement_rate"]))
        lab = _lab_per_student(c)
        if lab:
            labs.append(math.log1p(lab))
        infra = _infra_per_student(c)
        if infra:
            infras.append(math.log1p(infra))
        pos = _nirf_position(c)
        if pos:
            positions.append(pos)
        fees.append(float(c["fee_band"]["relative_tier"]))

    store.norms = Norms(
        median_salary=_percentile_bounds(salaries),
        placement_rate=_percentile_bounds(rates),
        lab_per_student_log=_percentile_bounds(labs),
        infra_per_student_log=_percentile_bounds(infras),
        nirf_position=(
            min(positions) if positions else 1.0,
            max(positions) if positions else 300.0,
        ),
        fee_tier=(min(fees) if fees else 1.0, max(fees) if fees else 3.0),
    )

    store.sources = {
        "colleges": colleges_doc["meta"].get("sources", []),
        "cutoffs": cutoffs_doc["meta"],
        "vacancy": vacancy_doc["meta"],
    }
    return store


# Exported helpers used by the scoring module.
nirf_position = _nirf_position
lab_per_student = _lab_per_student
infra_per_student = _infra_per_student
