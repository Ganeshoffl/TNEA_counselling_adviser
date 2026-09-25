"""
College quality scoring.

Placement is the single most heavily weighted factor, as requested: median salary
and placement rate together carry half of the total weight.

Two deliberate design decisions, both made to avoid misleading output:

1. A quality score requires published placement data.
   Placement carries 50% of the weight. A college for which NIRF publishes no
   placement figure cannot be scored on the same scale as one that has it, so it
   is returned with quality_score = None and an explicit reason instead. An
   earlier version renormalised the weights in that situation, and the result was
   actively misleading: a government college with no placement data scored 40.0
   purely because its tuition is low, which put it above a college with fully
   verified placement, laboratory and ranking data scoring 37.7. Such colleges are
   still shown to the student as available options, but without a quality number
   that would invite a false comparison.

2. Components are normalised against fixed absolute anchors, not against the
   best and worst college in the cohort.
   Cohort min-max normalisation made whichever college happened to be last on
   every metric collapse to nearly zero (Mepco Schlenk scored 4.88), which
   misrepresents a well-regarded institution. Absolute anchors keep scores stable
   and interpretable, and they do not shift when the dataset grows.

The anchors and weights below are a MODELLING CHOICE, not data. They are stated
openly and returned by the API so the ranking can be argued with. Everything they
are applied to is an officially published figure.
"""

from __future__ import annotations

import math
from typing import Any

from .data_store import DataStore, infra_per_student, lab_per_student, nirf_position

WEIGHTS: dict[str, float] = {
    "placement_median_salary": 0.35,
    "placement_rate": 0.15,
    "lab_spend_per_student": 0.15,
    "infrastructure_spend_per_student": 0.10,
    "nirf_standing": 0.15,
    "fee_band": 0.10,
}

# Components without which no score is produced at all.
REQUIRED_COMPONENTS = {"placement_median_salary"}

# Absolute anchors: (value scoring 0.0, value scoring 1.0).
ANCHORS: dict[str, tuple[float, float]] = {
    # Realistic span of median salaries for Tamil Nadu engineering colleges.
    "placement_median_salary": (300_000, 1_000_000),
    "placement_rate": (0.40, 0.95),
    # Money-per-student anchors are applied on a log scale, because spending
    # differences of this kind are multiplicative rather than additive.
    "lab_spend_per_student": (10_000, 250_000),
    "infrastructure_spend_per_student": (20_000, 600_000),
    # NIRF position: rank 1 is best, 300 is the bottom of the published bands.
    "nirf_standing": (300.0, 1.0),
    # Fee tier: 1 is the government tier, 3 is self-financing.
    "fee_band": (3.0, 1.0),
}

LOG_SCALED = {"lab_spend_per_student", "infrastructure_spend_per_student"}

COMPONENT_LABELS = {
    "placement_median_salary": "Median salary of placed graduates",
    "placement_rate": "Share of graduating students placed",
    "lab_spend_per_student": "Annual spend on new laboratory equipment and software, per student",
    "infrastructure_spend_per_student": "Annual capital spend on labs, library, classrooms and workshops, per student",
    "nirf_standing": "NIRF national standing in Engineering",
    "fee_band": "Fee tier (lower tuition scores higher)",
}


def anchor_normalise(component: str, value: float) -> float:
    zero_at, one_at = ANCHORS[component]
    if component in LOG_SCALED:
        value = math.log(max(value, 1.0))
        zero_at = math.log(zero_at)
        one_at = math.log(one_at)
    if one_at == zero_at:
        return 0.5
    return max(0.0, min(1.0, (value - zero_at) / (one_at - zero_at)))


def _component_values(college: dict) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    placement = college.get("placement")
    if placement:
        shared = {
            "source": placement.get("source"),
            "source_url": placement.get("source_url"),
            "as_of": placement.get("graduating_year"),
            "hosted_by": placement.get("hosted_by"),
            "caveat": placement.get("provenance_caveat"),
            "host_note": placement.get("host_note"),
        }
        salary = placement.get("median_salary_inr")
        if salary:
            out["placement_median_salary"] = {
                "raw": salary,
                "display": f"Rs {salary:,} per annum",
                "normalised": anchor_normalise("placement_median_salary", float(salary)),
                **shared,
            }
        rate = placement.get("placement_rate")
        if rate is not None:
            out["placement_rate"] = {
                "raw": rate,
                "display": (
                    f"{rate * 100:.1f}% "
                    f"({placement.get('students_placed')} of {placement.get('students_graduating')})"
                ),
                "normalised": anchor_normalise("placement_rate", float(rate)),
                **shared,
            }

    infrastructure = college.get("infrastructure") or {}
    infra_shared = {
        "source": infrastructure.get("source"),
        "source_url": infrastructure.get("source_url"),
        "hosted_by": infrastructure.get("hosted_by"),
        "caveat": infrastructure.get("provenance_caveat"),
    }
    lab = lab_per_student(college)
    if lab:
        out["lab_spend_per_student"] = {
            "raw": lab,
            "display": f"Rs {round(lab):,} per student per year",
            "normalised": anchor_normalise("lab_spend_per_student", float(lab)),
            **infra_shared,
        }
    infra = infra_per_student(college)
    if infra:
        out["infrastructure_spend_per_student"] = {
            "raw": infra,
            "display": f"Rs {round(infra):,} per student per year",
            "normalised": anchor_normalise("infrastructure_spend_per_student", float(infra)),
            **infra_shared,
        }

    nirf = college.get("nirf")
    position = nirf_position(college)
    if nirf and position:
        if nirf.get("rank"):
            display = f"NIRF {nirf['year']} rank {nirf['rank']} (score {nirf['score']})"
            basis = "published rank"
        else:
            display = f"NIRF {nirf['year']} rank band {nirf['rank_band']}"
            basis = (
                "midpoint of the published band, because NIRF publishes no rank or "
                "score for institutes inside a band"
            )
        out["nirf_standing"] = {
            "raw": position,
            "display": display,
            "normalised": anchor_normalise("nirf_standing", float(position)),
            "source": nirf.get("publisher"),
            "source_url": nirf.get("source_url"),
            "basis": basis,
        }

    fee = college["fee_band"]
    out["fee_band"] = {
        "raw": fee["relative_tier"],
        "display": fee["band"],
        "normalised": anchor_normalise("fee_band", float(fee["relative_tier"])),
        "source": "Derived from the institution type in the official TNEA college name",
        "caveat": fee["caveat"],
    }
    return out


def score_college(college: dict, store: DataStore | None = None) -> dict[str, Any]:
    components = _component_values(college)

    missing_required = sorted(REQUIRED_COMPONENTS - set(components))
    breakdown = []
    used_weight = 0.0
    weighted = 0.0

    for key, weight in WEIGHTS.items():
        comp = components.get(key)
        if comp is None or comp.get("normalised") is None:
            breakdown.append(
                {
                    "component": key,
                    "label": COMPONENT_LABELS[key],
                    "weight": weight,
                    "available": False,
                    "reason": "Not published by the official source for this college",
                }
            )
            continue
        used_weight += weight
        weighted += weight * comp["normalised"]
        entry = {
            "component": key,
            "label": COMPONENT_LABELS[key],
            "weight": weight,
            "available": True,
            "value": comp["display"],
            "normalised": round(comp["normalised"], 4),
            "source": comp.get("source"),
            "source_url": comp.get("source_url"),
        }
        for extra in ("as_of", "basis", "caveat", "hosted_by", "host_note"):
            if comp.get(extra):
                entry[extra] = comp[extra]
        breakdown.append(entry)

    if missing_required or used_weight <= 0:
        return {
            "quality_score": None,
            "scorable": False,
            "unscorable_reason": (
                "No placement figure could be obtained for this college, and placement "
                "carries half of the quality weight. Rather than renormalise the "
                "remaining factors and produce a number that would look comparable to "
                "a fully measured college, no quality score is given. NIRF publishes "
                "per-institute data only down to rank 200, and no copy of this "
                "college's own submission was found on its website either."
            ),
            "missing_required_components": missing_required,
            "evidence_completeness": round(used_weight / sum(WEIGHTS.values()), 3),
            "data_confidence": college.get("data_confidence"),
            "components": breakdown,
        }

    return {
        "quality_score": round(100.0 * weighted / used_weight, 2),
        "scorable": True,
        "evidence_completeness": round(used_weight / sum(WEIGHTS.values()), 3),
        "data_confidence": college.get("data_confidence"),
        "components": breakdown,
        "scoring_note": (
            "Placement carries 50% of the total weight (median salary 35%, placement "
            "rate 15%). Each factor is normalised against fixed absolute anchors, not "
            "against the best and worst college in this dataset, so scores stay "
            "interpretable and do not shift as the dataset grows. Weights and anchors "
            "are a modelling choice and are published by the API."
        ),
    }


def is_scorable(college: dict) -> bool:
    placement = college.get("placement") or {}
    return bool(placement.get("median_salary_inr"))


def score_all(store: DataStore) -> dict[int, dict]:
    return {c["college_code"]: score_college(c, store) for c in store.recommendable_colleges()}
