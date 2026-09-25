"""
Admission probability for a specific college + branch + community in a target
TNEA round.

The estimate combines two official facts:

1. Closing rank. TNEA's per-candidate provisional allotment lists give the exact
   worst (largest) rank that was actually allotted that college + branch under
   that community in a given round. A candidate comfortably ahead of that rank
   would have been allotted the seat; a candidate well behind it would not.

2. Seat availability. TNEA's "vacancy position after round N" tells us exactly how
   many seats of that community remain unfilled, which is precisely the pool a
   candidate competes for in the following round. Zero vacant seats is a hard
   stop, not a low probability.

Both are real published figures for the current (2026) admission year, so this is
a same-year model rather than an extrapolation from an older cycle.

The output is an estimate and is labelled as such. It is not a guarantee: TNEA
allotment also depends on the candidate's own choice ordering and on how other
candidates behave in the same round, neither of which is knowable in advance.
"""

from __future__ import annotations

import math
from typing import Any

from .data_store import DataStore, ROUNDS_WITH_OFFICIAL_DATA

# Controls how sharply probability falls as the candidate's rank passes the
# closing rank. At rel == 0 (rank exactly equal to the closing rank) probability
# is 0.5, which is the honest reading of sitting precisely on the boundary.
RANK_SPREAD = 0.12

# Small-vacancy discounts. Few remaining seats genuinely reduce the chance of
# being reached even for a candidate whose rank looks sufficient.
def _availability_factor(seats: int) -> float:
    if seats <= 0:
        return 0.0
    if seats == 1:
        return 0.70
    if seats == 2:
        return 0.80
    if seats <= 5:
        return 0.90
    return 1.0


def _logistic(rel: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(rel / RANK_SPREAD))
    except OverflowError:
        return 0.0 if rel > 0 else 1.0


def estimate(
    store: DataStore,
    college_code: int,
    branch_code: str,
    community: str,
    student_rank: int,
    target_round: int,
) -> dict[str, Any] | None:
    """
    Return an estimate dict, or None when no official closing-rank evidence
    exists for this combination (in which case nothing is asserted).
    """
    cutoff, cutoff_round = store.reference_cutoff(
        college_code, branch_code, community, target_round
    )
    seats = store.seats_available(college_code, branch_code, community, target_round)

    if cutoff is None:
        return None

    closing_rank = cutoff["closing_rank"]
    opening_rank = cutoff["opening_rank"]

    rel = (student_rank - closing_rank) / max(closing_rank, 1)
    p_rank = _logistic(rel)

    notes: list[str] = []

    if seats is None:
        # No vacancy row for this community: availability unknown, so report the
        # rank-based reading only and say so.
        probability = p_rank
        availability_state = "unknown"
        notes.append(
            "TNEA published no vacancy figure for this community in this branch, "
            "so only the closing-rank evidence is reflected."
        )
        factor = 1.0
    else:
        factor = _availability_factor(seats)
        probability = p_rank * factor
        if seats <= 0:
            availability_state = "none"
            notes.append(
                "No seats of this community remained vacant going into this round, "
                "so this seat cannot be allotted regardless of rank."
            )
        elif seats <= 5:
            availability_state = "scarce"
            notes.append(f"Only {seats} seat(s) of this community were vacant going into this round.")
        else:
            availability_state = "available"

    if student_rank <= opening_rank:
        notes.append(
            f"Your rank is ahead of the best rank allotted here in round {cutoff_round} "
            f"(rank {opening_rank})."
        )
    elif student_rank <= closing_rank:
        notes.append(
            f"Your rank falls inside the range actually allotted here in round {cutoff_round} "
            f"(ranks {opening_rank} to {closing_rank})."
        )
    else:
        gap = student_rank - closing_rank
        notes.append(
            f"Your rank is {gap:,} behind the last rank allotted here in round "
            f"{cutoff_round} (rank {closing_rank})."
        )

    if target_round not in ROUNDS_WITH_OFFICIAL_DATA:
        notes.append(
            f"Round {target_round} has not been published by TNEA, so round "
            f"{cutoff_round} evidence is used as the closest available benchmark."
        )
    elif cutoff_round != target_round:
        notes.append(
            f"No allotments were recorded here in round {target_round}; round "
            f"{cutoff_round} evidence is used instead."
        )

    return {
        "probability": round(max(0.0, min(1.0, probability)), 4),
        "closing_rank": closing_rank,
        "opening_rank": opening_rank,
        "closing_mark": cutoff.get("closing_mark"),
        "evidence_round": cutoff_round,
        "seats_allotted_in_evidence_round": cutoff.get("seats_allotted"),
        "seats_vacant_entering_round": seats,
        "availability": availability_state,
        "availability_factor": factor,
        "rank_component": round(p_rank, 4),
        "notes": notes,
        "method": (
            "Logistic in the relative gap between your rank and the official closing "
            "rank, multiplied by a discount when very few seats remain. Estimate only."
        ),
    }
