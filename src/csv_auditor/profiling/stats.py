import math
import random
from collections import Counter
from typing import Any, Protocol

import pandas as pd


class Accumulator(Protocol):
    def update(self, chunk: pd.DataFrame) -> None: ...
    def finalize(self) -> dict[str, Any]: ...


class NumericAccumulator:
    def __init__(self, column: str, reservoir_size: int = 20_000) -> None:
        self.column = column
        self.count = 0
        self.null_count = 0
        self.min_val: float | None = None
        self.max_val: float | None = None
        self.mean = 0.0
        self.m2 = 0.0
        self.reservoir_size = reservoir_size
        self.reservoir: list[float] = []
        self._rng = random.Random(42)

    def update_series(self, series: pd.Series, missing_set: set[str]) -> None:
        for raw in series:
            val_str = str(raw).strip()
            if not val_str or val_str.casefold() in missing_set:
                self.null_count += 1
                continue

            try:
                num = float(val_str)
                if math.isnan(num) or math.isinf(num):
                    self.null_count += 1
                    continue
            except (ValueError, TypeError):
                self.null_count += 1
                continue

            self.count += 1
            if self.min_val is None or num < self.min_val:
                self.min_val = num
            if self.max_val is None or num > self.max_val:
                self.max_val = num

            delta = num - self.mean
            self.mean += delta / self.count
            delta2 = num - self.mean
            self.m2 += delta * delta2

            if len(self.reservoir) < self.reservoir_size:
                self.reservoir.append(num)
            else:
                idx = self._rng.randint(0, self.count - 1)
                if idx < self.reservoir_size:
                    self.reservoir[idx] = num

    def finalize(self) -> dict[str, Any]:
        if self.count == 0:
            return {
                "count": 0,
                "null_count": self.null_count,
                "min": None,
                "max": None,
                "mean": None,
                "std": None,
                "median": None,
                "is_median_approximate": False,
            }

        variance = self.m2 / (self.count - 1) if self.count > 1 else 0.0
        std = math.sqrt(variance)

        is_approx = self.count > self.reservoir_size
        median_val = None
        if self.reservoir:
            sorted_res = sorted(self.reservoir)
            mid = len(sorted_res) // 2
            if len(sorted_res) % 2 == 1:
                median_val = sorted_res[mid]
            else:
                median_val = (sorted_res[mid - 1] + sorted_res[mid]) / 2.0

        return {
            "count": self.count,
            "null_count": self.null_count,
            "min": round(self.min_val, 4) if self.min_val is not None else None,
            "max": round(self.max_val, 4) if self.max_val is not None else None,
            "mean": round(self.mean, 4),
            "std": round(std, 4),
            "median": round(median_val, 4) if median_val is not None else None,
            "is_median_approximate": is_approx,
        }


class CategoricalAccumulator:
    def __init__(self, column: str, max_cardinality: int = 50_000, top_k: int = 20) -> None:
        self.column = column
        self.max_cardinality = max_cardinality
        self.top_k = top_k
        self.counts: Counter[str] = Counter()
        self.null_count = 0
        self.total_count = 0
        self.is_approximate = False

    def update_series(self, series: pd.Series, missing_set: set[str]) -> None:
        for raw in series:
            self.total_count += 1
            val_str = str(raw).strip()
            if not val_str or val_str.casefold() in missing_set:
                self.null_count += 1
                continue

            if val_str in self.counts or len(self.counts) < self.max_cardinality:
                self.counts[val_str] += 1
            else:
                self.is_approximate = True

    def finalize(self) -> dict[str, Any]:
        most_common = dict(self.counts.most_common(self.top_k))
        return {
            "count": self.total_count - self.null_count,
            "null_count": self.null_count,
            "unique_count": len(self.counts),
            "is_unique_approximate": self.is_approximate,
            "top_values": most_common,
        }


class StringAccumulator:
    def __init__(self, column: str) -> None:
        self.column = column
        self.total_count = 0
        self.null_count = 0
        self.min_length: int | None = None
        self.max_length: int | None = None
        self.whitespace_only_count = 0
        self.leading_trailing_space_count = 0

    def update_series(self, series: pd.Series, missing_set: set[str]) -> None:
        for raw in series:
            self.total_count += 1
            val = str(raw)
            if val.isspace():
                self.whitespace_only_count += 1

            if (
                not val
                or val.strip().casefold() in missing_set
                or val.strip() in missing_set
                or val.isspace()
            ):
                self.null_count += 1
                continue

            length = len(val)
            if self.min_length is None or length < self.min_length:
                self.min_length = length
            if self.max_length is None or length > self.max_length:
                self.max_length = length

            if len(val) != len(val.strip()):
                self.leading_trailing_space_count += 1

    def finalize(self) -> dict[str, Any]:
        return {
            "count": self.total_count - self.null_count,
            "null_count": self.null_count,
            "min_length": self.min_length,
            "max_length": self.max_length,
            "whitespace_only_count": self.whitespace_only_count,
            "leading_trailing_space_count": self.leading_trailing_space_count,
        }
