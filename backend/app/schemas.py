"""Pydantic models matching docs/api-contract.md."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RiskTier = Literal["monitor", "review", "str_ready"]
PatternType = Literal["cycle", "scatter_gather", "unclassified"]
Decision = Literal["confirm", "dismiss"]


class CaseSummary(BaseModel):
    case_id: str
    risk_tier: RiskTier
    risk_score: int
    account_count: int
    flagged_at: datetime


class SubScores(BaseModel):
    velocity: float
    fan_ratio: float
    cycle_match: float


class Node(BaseModel):
    id: str
    label: str


class Edge(BaseModel):
    source: str
    target: str
    amount: float
    timestamp: datetime


class CaseDetail(BaseModel):
    case_id: str
    risk_tier: RiskTier
    risk_score: int
    sub_scores: SubScores
    pattern_type: PatternType
    nodes: list[Node]
    edges: list[Edge]
    evidence_text: str
    str_deadline: datetime


class EscalateRequest(BaseModel):
    decision: Decision


class EscalateResponse(BaseModel):
    case_id: str
    status: str


class MetricSet(BaseModel):
    precision: float
    recall: float
    f1: float


class MetricsResponse(BaseModel):
    baseline: MetricSet
    candidate: MetricSet
