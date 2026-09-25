"""
TNEA Counselling Advisor API.

Stateless. No login, no persistence. Every response carries the provenance of the
figures it is built from.
"""

from __future__ import annotations

from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .data_store import COMMUNITIES, ROUNDS_WITH_OFFICIAL_DATA, SUPPORTED_ROUNDS, get_store
from .engine import MODE_DEFINITIONS, recommend
from .models import MetaResponse, RecommendRequest
from .scoring import WEIGHTS, score_college

app = FastAPI(
    title="TNEA Counselling Advisor",
    version="1.0.0",
    description=(
        "Safe / Optimal / Risk guidance for Tamil Nadu Engineering Admissions "
        "counselling, built only on officially published TNEA and NIRF data."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    store = get_store()
    return {
        "status": "ok",
        "colleges_loaded": len(store.colleges),
        "cutoff_keys": len(store.cutoffs),
    }


@app.get("/api/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    store = get_store()
    m = store.colleges_meta
    return MetaResponse(
        admission_year=m["admission_year"],
        communities=COMMUNITIES,
        supported_rounds=SUPPORTED_ROUNDS,
        rounds_with_official_data=ROUNDS_WITH_OFFICIAL_DATA,
        college_count=m["college_count"],
        recommendable_count=m["recommendable_count"],
        data_confidence_counts=m["data_confidence_counts"],
        data_confidence_legend=m["data_confidence_legend"],
        sources=m["sources"],
        scoring_weights=WEIGHTS,
    )


@app.get("/api/modes")
def modes() -> dict[str, Any]:
    return {
        "modes": MODE_DEFINITIONS,
        "note": (
            "The three modes map onto the confirmation options published in the "
            "official TNEA counselling procedure, so the downside of each is the "
            "downside the procedure actually defines."
        ),
    }


@app.get("/api/branches")
def branches() -> dict[str, Any]:
    store = get_store()
    return {"branches": store.branches}


@app.get("/api/colleges")
def colleges(
    recommendable_only: bool = Query(True, description="Only colleges that have verifiable quality data."),
    search: str | None = Query(None, description="Case-insensitive substring of the college name."),
    limit: int = Query(500, ge=1, le=1000),
) -> dict[str, Any]:
    store = get_store()
    items = []
    for college in store.colleges.values():
        if recommendable_only and not college.get("recommendable"):
            continue
        if search:
            needle = search.strip().lower()
            if needle not in college["official_name"].lower():
                continue
        quality = score_college(college, store) if college.get("recommendable") else None
        items.append(
            {
                "college_code": college["college_code"],
                "display_name": college["display_name"],
                "official_name": college["official_name"],
                "city": college.get("city"),
                "institution_type": college["institution_type"],
                "data_confidence": college["data_confidence"],
                "recommendable": college["recommendable"],
                "branches": college.get("branches", []),
                "nirf": college.get("nirf"),
                "fee_band": college["fee_band"],
                "quality_score": quality["quality_score"] if quality else None,
                "evidence_completeness": quality["evidence_completeness"] if quality else None,
            }
        )
    items.sort(key=lambda c: (c["quality_score"] is None, -(c["quality_score"] or 0)))
    return {"count": len(items), "colleges": items[:limit]}


@app.get("/api/colleges/{college_code}")
def college_detail(college_code: int) -> dict[str, Any]:
    store = get_store()
    college = store.college(college_code)
    if college is None:
        raise HTTPException(status_code=404, detail=f"College code {college_code} not found.")
    quality = score_college(college, store) if college.get("recommendable") else None
    return {
        "college": college,
        "quality": quality,
        "branch_names": {b: store.branch_name(b) for b in college.get("branches", [])},
    }


@app.post("/api/recommend")
def recommend_endpoint(payload: RecommendRequest) -> dict[str, Any]:
    return recommend(
        cutoff_mark=payload.cutoff_mark,
        rank=payload.rank,
        community=payload.community,
        current_round=payload.current_round,
        current_college_code=payload.current_college_code,
        current_branch_code=payload.current_branch_code,
        branches=payload.branches,
        limit=payload.limit,
    )


# Serve the built React app from the same origin when it has been built, so that
# `npm run build` plus this one process is a complete deployment. During frontend
# development the Vite dev server proxies /api here instead.
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
