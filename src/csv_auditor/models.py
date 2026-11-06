from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_name: str
    column: str | None = None
    row_index: int | None = None
    message: str
    severity: Severity = Severity.MEDIUM
    sample_value: str | None = None


class ColumnMissingStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    missing_count: int
    total_count: int
    missing_percentage: float
    severity: Severity


class DuplicateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exact_duplicate_rows: int = 0
    unique_rows: int = 0
    total_rows: int = 0
    mode: str = "exact"
    key_duplicates: dict[str, int] = Field(default_factory=dict)
    sample_duplicate_keys: dict[str, list[str]] = Field(default_factory=dict)


class InferredColumnType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggested_type: str
    confidence: float
    has_leading_zeros: bool = False
    dominant_type_share: float = 1.0


class QualityScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: float
    rating: str
    completeness: float
    uniqueness: float
    validity: float | None = None
    consistency: float
    weights_used: dict[str, float]
    dimensions_used: list[str]


class DatasetMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    file_size_bytes: int
    encoding: str
    delimiter: str
    total_rows: int
    total_columns: int
    column_names: list[str]
    sample_rows: list[list[str]] = Field(default_factory=list)
    sniff_warnings: list[str] = Field(default_factory=list)
    timestamp_utc: str
    auditor_version: str


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    issue: str
    suggested_action: str


class AuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: DatasetMetadata
    score: QualityScore
    missing: dict[str, ColumnMissingStats] = Field(default_factory=dict)
    duplicates: DuplicateReport = Field(default_factory=DuplicateReport)
    types: dict[str, InferredColumnType] = Field(default_factory=dict)
    profiling: dict[str, dict[str, Any]] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)
    issue_summary: dict[str, int] = Field(default_factory=dict)
    # Issues hold at most `max_examples` rows per rule; these are the full totals.
    rule_violations: dict[str, int] = Field(default_factory=dict)
    rows_with_rule_violations: int = 0
    recommendations: list[Recommendation] = Field(default_factory=list)
