import pandas as pd

from csv_auditor.profiling.stats import (
    CategoricalAccumulator,
    NumericAccumulator,
    StringAccumulator,
)


def test_numeric_accumulator_welford_stats():
    acc = NumericAccumulator("val")
    series_1 = pd.Series(["10", "20", "30"])
    series_2 = pd.Series(["40", "50"])
    missing_set = {"", "null"}

    acc.update_series(series_1, missing_set)
    acc.update_series(series_2, missing_set)

    res = acc.finalize()
    assert res["count"] == 5
    assert res["min"] == 10.0
    assert res["max"] == 50.0
    assert res["mean"] == 30.0
    assert res["median"] == 30.0
    assert abs(res["std"] - 15.8114) < 1e-3


def test_numeric_accumulator_constant_column():
    acc = NumericAccumulator("const")
    series = pd.Series(["42", "42", "42", "42"])
    acc.update_series(series, set())
    res = acc.finalize()
    assert res["min"] == 42.0
    assert res["max"] == 42.0
    assert res["mean"] == 42.0
    assert res["std"] == 0.0


def test_categorical_accumulator():
    acc = CategoricalAccumulator("cat", top_k=2)
    s = pd.Series(["apple", "banana", "apple", "orange", "apple", "banana"])
    acc.update_series(s, set())
    res = acc.finalize()
    assert res["count"] == 6
    assert res["unique_count"] == 3
    assert res["top_values"]["apple"] == 3
    assert res["top_values"]["banana"] == 2


def test_string_accumulator():
    acc = StringAccumulator("text")
    s = pd.Series(["hello", "   ", "world!", " spaced "])
    acc.update_series(s, {"null"})
    res = acc.finalize()
    assert res["min_length"] == 5
    assert res["max_length"] == 8
    assert res["whitespace_only_count"] == 1
    assert res["leading_trailing_space_count"] == 1
