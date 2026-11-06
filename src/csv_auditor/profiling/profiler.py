from typing import Any

import pandas as pd

from csv_auditor.models import InferredColumnType
from csv_auditor.profiling.stats import (
    CategoricalAccumulator,
    NumericAccumulator,
    StringAccumulator,
)
from csv_auditor.profiling.types import infer_series_type


class DatasetProfiler:
    def __init__(self, columns: list[str], missing_markers: list[str]) -> None:
        self.columns = columns
        self.missing_set = {marker.casefold() for marker in missing_markers}
        self.numeric_accumulators = {col: NumericAccumulator(col) for col in columns}
        self.categorical_accumulators = {col: CategoricalAccumulator(col) for col in columns}
        self.string_accumulators = {col: StringAccumulator(col) for col in columns}
        self.inferred_types: dict[str, InferredColumnType] = {}
        self._sample_data: dict[str, list[str]] = {col: [] for col in columns}

    def update(self, chunk: pd.DataFrame) -> None:
        for col in self.columns:
            if col not in chunk.columns:
                continue
            series = chunk[col]

            if len(self._sample_data[col]) < 2000:
                self._sample_data[col].extend(
                    series.iloc[: 2000 - len(self._sample_data[col])].tolist()
                )

            self.numeric_accumulators[col].update_series(series, self.missing_set)
            self.categorical_accumulators[col].update_series(series, self.missing_set)
            self.string_accumulators[col].update_series(series, self.missing_set)

    def finalize(self) -> tuple[dict[str, InferredColumnType], dict[str, dict[str, Any]]]:
        for col in self.columns:
            sample_series = pd.Series(self._sample_data[col])
            self.inferred_types[col] = infer_series_type(sample_series, self.missing_set)

        profile_results: dict[str, dict[str, Any]] = {}
        for col in self.columns:
            inf = self.inferred_types[col]
            cat_stats = self.categorical_accumulators[col].finalize()
            str_stats = self.string_accumulators[col].finalize()

            col_profile: dict[str, Any] = {
                "inferred_type": inf.suggested_type,
                "confidence": inf.confidence,
                "has_leading_zeros": inf.has_leading_zeros,
                "categorical": cat_stats,
                "string": str_stats,
            }

            if inf.suggested_type in ("integer", "float"):
                num_stats = self.numeric_accumulators[col].finalize()
                col_profile["numeric"] = num_stats

            profile_results[col] = col_profile

        return self.inferred_types, profile_results
