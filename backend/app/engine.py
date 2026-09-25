"""
Recommendation engine: Safe / Optimal / Risk, and the stay-versus-move-up call.

The three modes are not invented labels. They correspond to the confirmation
options that the Directorate of Technical Education actually offers a candidate
who has been allotted a seat (TNEA counselling procedure, "Various confirmation
options"):

  Accept and Upward   The candidate pays the fee at a TFC and waits for a higher
                      choice. The official procedure states that if no better
                      choice becomes available the candidate "is confirmed with
                      the previously allotted choice". The current seat therefore
                      acts as a floor, so trying to move up this way has almost no
                      downside beyond the fee.

  Decline and Upward  The candidate declines the allotted seat and waits for a
                      higher choice. If the upgrade does not arrive the candidate
                      "will be moved to the next round" WITHOUT the declined seat.
                      The downside here is real.

  Decline and move to next round / Decline and Quit
                      The seat is given up outright.

So:
  SAFE    -> high-probability upgrades pursued through Accept and Upward, where the
             existing seat is retained if the upgrade fails.
  OPTIMAL -> best expected value, again through Accept and Upward.
  RISK    -> high-quality, low-probability targets that in practice require giving
             up the current seat, with the downside stated explicitly.

One more real constraint is surfaced rather than hidden: upward movement only
considers choices ranked ABOVE the current allotment in the candidate's own
choice list. A college this tool suggests can only be reached in upward movement
if the candidate had already placed it higher in their choice order; otherwise it
has to be pursued in a later round.
"""

from __future__ import annotations

from typing import Any

from . import probability as prob
from .data_store import DataStore, ROUNDS_WITH_OFFICIAL_DATA, get_store
from .scoring import score_college, is_scorable

# Probability bands for the three heads.
SAFE_MIN = 0.80
OPTIMAL_MIN = 0.45
RISK_MIN = 0.12

# Minimum quality gain (points of the 0-100 score) before a move is worth advising.
SAFE_UPLIFT = 3.0
OPTIMAL_UPLIFT = 5.0
RISK_UPLIFT = 8.0

MODE_DEFINITIONS = {
    "safe": {
        "label": "Safe",
        "probability_band": f"{SAFE_MIN:.0%} and above",
        "objective": "Highest college quality among seats you are very likely to actually get.",
        "tnea_mechanism": "Accept and Upward",
        "downside": (
            "Minimal. Under Accept and Upward the official procedure confirms your "
            "existing allotment if no better choice arrives, so your current seat is "
            "a floor."
        ),
    },
    "optimal": {
        "label": "Optimal",
        "probability_band": f"{OPTIMAL_MIN:.0%} to {SAFE_MIN:.0%}",
        "objective": "Best expected value, balancing how much better the college is against how likely you are to get it.",
        "tnea_mechanism": "Accept and Upward",
        "downside": (
            "Low. Still pursued through Accept and Upward, so a failed upgrade leaves "
            "you with your current seat."
        ),
    },
    "risk": {
        "label": "Risk",
        "probability_band": f"{RISK_MIN:.0%} to {OPTIMAL_MIN:.0%}",
        "objective": "Highest quality colleges that are a genuine stretch for your rank. Large gain if it lands.",
        "tnea_mechanism": "Decline and Upward, or declining to a later round",
        "downside": (
            "Real. If you decline your seat and the upgrade does not arrive, the "
            "official procedure moves you to the next round without the declined "
            "seat, and you may end up with a weaker college or none."
        ),
    },
}


def _candidate_rows(
    store: DataStore,
    student_rank: int,
    community: str,
    target_round: int,
    branch_filter: set[str] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Evaluate every recommendable college+branch the student could be allotted.

    Returns two lists:
      scored    colleges with published placement data, which can be ranked on
                quality and therefore drive the Safe / Optimal / Risk heads;
      unscored  colleges whose NIRF rank band is verified but for which NIRF
                publishes no placement or laboratory figures. These are still
                real TNEA options, so they are returned with their admission
                probability, but deliberately without a quality number that would
                invite a false comparison against a fully measured college.
    """
    scored: list[dict[str, Any]] = []
    unscored: list[dict[str, Any]] = []

    for college in store.recommendable_colleges():
        code = college["college_code"]
        quality = score_college(college, store)
        scorable = quality.get("scorable", False)

        for branch in college.get("branches", []):
            if branch_filter and branch not in branch_filter:
                continue
            estimate = prob.estimate(store, code, branch, community, student_rank, target_round)
            if estimate is None:
                continue
            row = {
                "college_code": code,
                "college_name": college["display_name"],
                "official_college_name": college["official_name"],
                "city": college.get("city"),
                "institution_type": college["institution_type"],
                "data_confidence": college["data_confidence"],
                "nirf": college.get("nirf"),
                "fee_band": college["fee_band"],
                "branch_code": branch,
                "branch_name": store.branch_name(branch),
                "quality": quality,
                "admission": estimate,
            }
            (scored if scorable else unscored).append(row)

    return scored, unscored


def _current_allotment_view(
    store: DataStore,
    college_code: int | None,
    branch_code: str | None,
) -> dict[str, Any] | None:
    if not college_code:
        return None
    college = store.college(college_code)
    if college is None:
        return {
            "known": False,
            "college_code": college_code,
            "message": f"College code {college_code} is not in the official TNEA 2026 general academic list.",
        }
    quality = score_college(college, store) if college.get("recommendable") else None
    return {
        "known": True,
        "college_code": college_code,
        "college_name": college["display_name"],
        "official_college_name": college["official_name"],
        "branch_code": branch_code,
        "branch_name": store.branch_name(branch_code) if branch_code else None,
        "institution_type": college["institution_type"],
        "data_confidence": college["data_confidence"],
        "quality": quality,
        "quality_unavailable_reason": (
            None
            if quality
            else (
                "This college has no NIRF presence, so no verified placement, "
                "laboratory or ranking data exists for it. Its quality cannot be "
                "scored, and this tool will not invent a number for it."
            )
        ),
    }


def _expected_value(mode: str, target_quality: float, probability: float, current_quality: float | None) -> dict[str, Any]:
    """
    Expected quality of attempting the move, using the correct fallback for the
    TNEA mechanism that the mode relies on.
    """
    if mode in ("safe", "optimal"):
        # Accept and Upward: a failed upgrade leaves the existing seat intact.
        fallback = current_quality
        if fallback is None:
            return {
                "expected_quality": None,
                "explanation": (
                    "Expected value needs the quality of your current seat, which "
                    "cannot be scored for that college."
                ),
            }
        ev = probability * target_quality + (1 - probability) * fallback
        return {
            "expected_quality": round(ev, 2),
            "fallback_quality": round(fallback, 2),
            "explanation": (
                "Under Accept and Upward a failed upgrade keeps your current seat, so "
                "the downside is your current college, not nothing."
            ),
        }
    # Risk: declining forfeits the seat, so the fallback is genuinely worse and is
    # not quantified as a score. We state that rather than invent a number.
    return {
        "expected_quality": None,
        "explanation": (
            "Not quantified. This path involves declining your seat, and the official "
            "procedure then moves you to the next round without it. The outcome of "
            "that round depends on other candidates' choices and cannot be estimated "
            "honestly from published data."
        ),
    }


def _pick(mode: str, rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if mode == "safe":
        pool = [r for r in rows if r["admission"]["probability"] >= SAFE_MIN]
        pool.sort(key=lambda r: (-r["quality"]["quality_score"], -r["admission"]["probability"]))
    elif mode == "optimal":
        pool = [r for r in rows if OPTIMAL_MIN <= r["admission"]["probability"] < SAFE_MIN]
        pool.sort(
            key=lambda r: -(r["quality"]["quality_score"] * r["admission"]["probability"])
        )
    else:
        pool = [r for r in rows if RISK_MIN <= r["admission"]["probability"] < OPTIMAL_MIN]
        pool.sort(key=lambda r: (-r["quality"]["quality_score"], -r["admission"]["probability"]))
    return pool[:limit]


def _verdict(
    mode: str,
    picks: list[dict[str, Any]],
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    uplift_needed = {"safe": SAFE_UPLIFT, "optimal": OPTIMAL_UPLIFT, "risk": RISK_UPLIFT}[mode]
    mechanism = MODE_DEFINITIONS[mode]["tnea_mechanism"]

    if not picks:
        return {
            "action": "stay",
            "headline": "No option in this band",
            "reasoning": (
                "No college and branch combination falls in this probability band for "
                "your rank, community and round, so there is nothing to move up to here."
            ),
            "tnea_mechanism": mechanism,
        }

    best = picks[0]
    target_quality = best["quality"]["quality_score"]
    probability = best["admission"]["probability"]

    current_quality = None
    if current and current.get("quality") and current["quality"].get("quality_score") is not None:
        current_quality = current["quality"]["quality_score"]

    ev = _expected_value(mode, target_quality, probability, current_quality)

    if current is None:
        return {
            "action": "pursue",
            "headline": f"No current allotment given, so every option here is a gain",
            "target": f"{best['college_name']} - {best['branch_name']}",
            "target_quality": target_quality,
            "probability": probability,
            "expected_value": ev,
            "tnea_mechanism": mechanism,
            "reasoning": (
                "You did not provide a current allotment, so this is simply the best "
                "option in this band for your rank and community."
            ),
        }

    if current_quality is None:
        return {
            "action": "compare_not_possible",
            "headline": "Cannot compare against your current seat",
            "target": f"{best['college_name']} - {best['branch_name']}",
            "target_quality": target_quality,
            "probability": probability,
            "expected_value": ev,
            "tnea_mechanism": mechanism,
            "reasoning": (
                "Your current college has no verified NIRF, placement or laboratory "
                "data, so a like-for-like quality comparison is not possible. The "
                "option shown is the strongest in this band, but whether it is an "
                "upgrade for you cannot be established from official data."
            ),
        }

    uplift = target_quality - current_quality

    if uplift < uplift_needed:
        return {
            "action": "stay",
            "headline": "Stay with your current allotment",
            "target": f"{best['college_name']} - {best['branch_name']}",
            "target_quality": target_quality,
            "current_quality": current_quality,
            "quality_uplift": round(uplift, 2),
            "probability": probability,
            "expected_value": ev,
            "tnea_mechanism": mechanism,
            "reasoning": (
                f"The best option in this band scores {target_quality:.1f} against your "
                f"current {current_quality:.1f}, a gain of only {uplift:.1f} points. That "
                f"is below the {uplift_needed:.0f}-point threshold this mode uses, so "
                f"moving is not worth the effort or the fee."
            ),
        }

    if mode == "risk":
        return {
            "action": "move_up_with_risk",
            "headline": "Worth a gamble, with a real downside",
            "target": f"{best['college_name']} - {best['branch_name']}",
            "target_quality": target_quality,
            "current_quality": current_quality,
            "quality_uplift": round(uplift, 2),
            "probability": probability,
            "expected_value": ev,
            "tnea_mechanism": mechanism,
            "reasoning": (
                f"{best['college_name']} scores {target_quality:.1f} against your current "
                f"{current_quality:.1f}, a gain of {uplift:.1f} points, but the estimated "
                f"chance is only {probability:.0%}. Pursuing it means declining your "
                f"current seat, and if the upgrade does not arrive the official procedure "
                f"moves you to the next round without it."
            ),
        }

    return {
        "action": "move_up",
        "headline": "Move up",
        "target": f"{best['college_name']} - {best['branch_name']}",
        "target_quality": target_quality,
        "current_quality": current_quality,
        "quality_uplift": round(uplift, 2),
        "probability": probability,
        "expected_value": ev,
        "tnea_mechanism": mechanism,
        "reasoning": (
            f"{best['college_name']} scores {target_quality:.1f} against your current "
            f"{current_quality:.1f}, a gain of {uplift:.1f} points, with an estimated "
            f"{probability:.0%} chance. Because Accept and Upward confirms your existing "
            f"allotment if no better choice arrives, your current seat is protected while "
            f"you try."
        ),
    }


def recommend(
    cutoff_mark: float,
    rank: int,
    community: str,
    current_round: int,
    current_college_code: int | None = None,
    current_branch_code: str | None = None,
    branches: list[str] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    store = get_store()

    branch_filter = set(branches) if branches else None
    rows, unscored = _candidate_rows(store, rank, community, current_round, branch_filter)
    current = _current_allotment_view(store, current_college_code, current_branch_code)

    modes: dict[str, Any] = {}
    for mode in ("safe", "optimal", "risk"):
        picks = _pick(mode, rows, limit)
        modes[mode] = {
            "definition": MODE_DEFINITIONS[mode],
            "verdict": _verdict(mode, picks, current),
            "options": picks,
            "option_count": len(picks),
        }

    # Reachable options that cannot be quality-ranked, highest probability first.
    unscored.sort(key=lambda r: -r["admission"]["probability"])
    reachable_unscored = [r for r in unscored if r["admission"]["probability"] >= RISK_MIN][:limit]

    warnings: list[str] = []
    if current_round not in ROUNDS_WITH_OFFICIAL_DATA:
        warnings.append(
            f"TNEA has published rounds {ROUNDS_WITH_OFFICIAL_DATA} for the 2026 general "
            f"academic stream. Round {current_round} is a forward simulation that reuses "
            f"the most recent published round as its benchmark."
        )
    if current_round == 1:
        warnings.append(
            "Seats available before round 1 are reconstructed as (seats vacant after "
            "round 1 + seats allotted in round 1), because TNEA's only online "
            "pre-round seat matrix is from 2023."
        )
    if not rows:
        warnings.append(
            "No college and branch combination had official closing-rank evidence for "
            "this community and round, so no recommendation could be produced."
        )

    return {
        "input": {
            "cutoff_mark": cutoff_mark,
            "rank": rank,
            "community": community,
            "current_round": current_round,
            "current_college_code": current_college_code,
            "current_branch_code": current_branch_code,
            "branch_filter": sorted(branch_filter) if branch_filter else None,
        },
        "current_allotment": current,
        "modes": modes,
        "unscored_available_options": {
            "explanation": (
                "These colleges are reachable for your rank and their NIRF rank band is "
                "verified, but NIRF publishes no placement or laboratory figures for "
                "them (it publishes per-institute data only down to rank 200). They are "
                "listed so you can see them, without a quality score that would look "
                "comparable to a fully measured college."
            ),
            "options": reachable_unscored,
            "option_count": len(reachable_unscored),
        },
        "candidates_evaluated": len(rows) + len(unscored),
        "scored_candidates": len(rows),
        "unscored_candidates": len(unscored),
        "warnings": warnings,
        "disclaimer": (
            "Probabilities are estimates derived from officially published TNEA 2026 "
            "closing ranks and round-wise vacancy figures. They are not guarantees. "
            "Actual allotment also depends on your own choice ordering and on how other "
            "candidates behave in the same round. Always confirm against tneaonline.org."
        ),
    }
