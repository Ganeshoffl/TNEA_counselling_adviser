"""Request and response models for the API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from .data_store import COMMUNITIES, SUPPORTED_ROUNDS


class RecommendRequest(BaseModel):
    cutoff_mark: float = Field(
        ...,
        ge=0,
        le=200,
        description="TNEA cutoff mark out of 200 (Maths + Physics/2 + Chemistry/2 as computed by DoTE).",
    )
    rank: int = Field(..., ge=1, description="TNEA general merit rank.")
    community: str = Field(..., description=f"One of {COMMUNITIES}.")
    current_round: int = Field(
        ..., description=f"The counselling round you are choosing for. One of {SUPPORTED_ROUNDS}."
    )
    current_college_code: int | None = Field(
        None, description="Official TNEA college code of your current allotment, if you have one."
    )
    current_branch_code: str | None = Field(
        None, description="Official TNEA branch code of your current allotment, if you have one."
    )
    branches: list[str] | None = Field(
        None, description="Optional list of branch codes to restrict suggestions to."
    )
    limit: int = Field(10, ge=1, le=50, description="Maximum options per mode.")

    @field_validator("community")
    @classmethod
    def _community_valid(cls, value: str) -> str:
        upper = value.strip().upper()
        if upper not in COMMUNITIES:
            raise ValueError(f"community must be one of {COMMUNITIES}")
        return upper

    @field_validator("current_round")
    @classmethod
    def _round_valid(cls, value: int) -> int:
        if value not in SUPPORTED_ROUNDS:
            raise ValueError(f"current_round must be one of {SUPPORTED_ROUNDS}")
        return value

    @field_validator("current_branch_code")
    @classmethod
    def _branch_upper(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("branches")
    @classmethod
    def _branches_upper(cls, value: list[str] | None) -> list[str] | None:
        if not value:
            return None
        return [v.strip().upper() for v in value if v and v.strip()]


class CollegeSummary(BaseModel):
    college_code: int
    display_name: str
    official_name: str
    city: str | None
    institution_type: str
    data_confidence: str
    recommendable: bool
    branches: list[str]
    nirf: dict[str, Any] | None = None
    quality_score: float | None = None


class MetaResponse(BaseModel):
    admission_year: int
    communities: list[str]
    supported_rounds: list[int]
    rounds_with_official_data: list[int]
    college_count: int
    recommendable_count: int
    data_confidence_counts: dict[str, int]
    data_confidence_legend: dict[str, str]
    sources: list[str]
    scoring_weights: dict[str, float]
