import re
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from csv_auditor.models import InferredColumnType

INTEGER_REGEX = re.compile(r"^[-+]?\d+$")
FLOAT_REGEX = re.compile(r"^[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?$")
BOOLEAN_STRINGS = {"true", "false", "yes", "no", "t", "f"}
DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S%z",
]


@dataclass
class TypeClassification:
    category: str
    is_leading_zero: bool = False


def classify_scalar(val: str, missing_markers: set[str]) -> TypeClassification | None:
    stripped = val.strip()
    if not stripped or stripped.lower() in missing_markers or stripped in missing_markers:
        return None

    lower = stripped.lower()
    if lower in BOOLEAN_STRINGS:
        return TypeClassification("boolean")

    if INTEGER_REGEX.match(stripped):
        has_lead_zero = len(stripped) > 1 and stripped.startswith("0")
        return TypeClassification("integer", is_leading_zero=has_lead_zero)

    if FLOAT_REGEX.match(stripped) and ("." in stripped or "e" in lower):
        return TypeClassification("float")

    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(stripped, fmt)
            return TypeClassification("date")
        except ValueError:
            continue

    return TypeClassification("string")


def infer_series_type(
    series: pd.Series, missing_markers: set[str] | None = None
) -> InferredColumnType:
    if missing_markers is None:
        missing_markers = {"", "null", "none", "nan", "n/a", "na", "-"}
    else:
        missing_markers = {m.lower() for m in missing_markers} | set(missing_markers)

    counts: dict[str, int] = {
        "integer": 0,
        "float": 0,
        "date": 0,
        "boolean": 0,
        "string": 0,
    }
    leading_zero_count = 0
    total_valid = 0

    sample = series.dropna()
    if len(sample) > 5000:
        sample = sample.sample(5000, random_state=42)

    for item in sample:
        classification = classify_scalar(str(item), missing_markers)
        if classification is None:
            continue
        total_valid += 1
        counts[classification.category] += 1
        if classification.is_leading_zero:
            leading_zero_count += 1

    if total_valid == 0:
        return InferredColumnType(
            suggested_type="string",
            confidence=0.0,
            has_leading_zeros=False,
            dominant_type_share=0.0,
        )

    # Every integer literal is also a valid float. Counting them apart made a column
    # like Titanic `Age` (mostly "22", sometimes "28.5") come out as "integer".
    if counts["float"] and counts["integer"]:
        counts["float"] += counts["integer"]
        counts["integer"] = 0

    dominant_category, dominant_count = max(counts.items(), key=lambda kv: kv[1])
    share = dominant_count / total_valid

    has_leading_zeros = leading_zero_count > 0 and (dominant_category in ("integer", "string"))

    if dominant_category == "integer" and has_leading_zeros:
        suggested_type = "string"
    else:
        suggested_type = dominant_category

    confidence = round(share, 4)
    return InferredColumnType(
        suggested_type=suggested_type,
        confidence=confidence,
        has_leading_zeros=has_leading_zeros,
        dominant_type_share=round(share, 4),
    )
