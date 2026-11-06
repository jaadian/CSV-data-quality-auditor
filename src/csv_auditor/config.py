import math
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from csv_auditor.exceptions import ConfigError
from csv_auditor.models import Severity


class ColumnRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    required: bool = False
    unique: bool = False
    min: float | int | None = None
    max: float | int | None = None
    min_length: int | None = None
    max_length: int | None = None
    allowed: list[Any] | None = None
    format: str | None = None
    regex: str | None = None
    severity: Severity = Severity.HIGH

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str | None) -> str | None:
        if value is not None and value not in {"string", "integer", "float", "boolean", "date"}:
            raise ValueError(f"Unsupported column type: {value}")
        return value

    @field_validator("regex")
    @classmethod
    def validate_regex(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"Invalid regular expression '{value}': {exc}") from exc
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> "ColumnRule":
        for name in ("min", "max"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        for name in ("min_length", "max_length"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.format is not None and self.format != "email" and self.type != "date":
            raise ValueError("format must be 'email' or be used with a date type")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) cannot be greater than max ({self.max})")
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError(
                f"min_length ({self.min_length}) cannot be greater than max_length ({self.max_length})"
            )
        return self


class CrossColumnRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    rule: str
    severity: Severity = Severity.HIGH

    @field_validator("rule")
    @classmethod
    def validate_expression(cls, value: str) -> str:
        operators = [">=", "<=", "!=", "==", ">", "<"]
        if not any(op in value for op in operators) or not re.fullmatch(
            r"\s*.+?\s*(?:>=|<=|!=|==|>|<)\s*.+?\s*", value
        ):
            raise ValueError(
                f"Cross-column rule '{value}' must contain a comparison operator (>=, <=, ==, !=, >, <)"
            )
        return value


class ScoreWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completeness: float = 0.30
    uniqueness: float = 0.25
    validity: float = 0.30
    consistency: float = 0.15

    @model_validator(mode="after")
    def validate_sum(self) -> "ScoreWeights":
        total = self.completeness + self.uniqueness + self.validity + self.consistency
        if abs(total - 1.0) > 1e-4:
            raise ValueError(f"Score weights must sum to 1.0, got {total:.4f}")
        for field_name, weight in [
            ("completeness", self.completeness),
            ("uniqueness", self.uniqueness),
            ("validity", self.validity),
            ("consistency", self.consistency),
        ]:
            if weight < 0:
                raise ValueError(f"Weight for '{field_name}' cannot be negative: {weight}")
        return self


class AuditorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    missing_markers: list[str] = Field(
        default_factory=lambda: ["", "NULL", "null", "N/A", "n/a", "NA", "NaN", "nan", "-", "None"]
    )
    whitespace_as_missing: bool = True
    columns: dict[str, ColumnRule] = Field(default_factory=dict)
    cross_column: list[CrossColumnRule] = Field(default_factory=list)
    score_weights: ScoreWeights = Field(default_factory=ScoreWeights)
    fail_on: Severity | None = None
    mask_columns: list[str] = Field(default_factory=list)
    max_examples: int = Field(default=5, ge=1)
    max_tracked_rows: int = Field(default=500_000, ge=1)
    chunk_size: int = Field(default=50_000, ge=1)


def load_config(path: str | Path | None) -> AuditorConfig:
    if path is None:
        return AuditorConfig()

    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML parsing error in {config_path}: {exc}") from exc
    except Exception as exc:
        raise ConfigError(f"Unable to read configuration file: {exc}") from exc

    if data is None:
        return AuditorConfig()

    if not isinstance(data, dict):
        raise ConfigError(f"Configuration file {config_path} must define a mapping/dictionary")

    try:
        return AuditorConfig.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Configuration validation failed: {exc}") from exc
