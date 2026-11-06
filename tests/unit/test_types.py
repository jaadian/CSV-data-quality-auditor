import pandas as pd

from csv_auditor.profiling.types import infer_series_type


def test_infer_integer():
    s = pd.Series(["1", "20", "-45", "1000", "0"])
    res = infer_series_type(s)
    assert res.suggested_type == "integer"
    assert res.has_leading_zeros is False
    assert res.confidence == 1.0


def test_infer_leading_zeros_flagged_as_string():
    s = pd.Series(["00123", "00456", "01234", "09999"])
    res = infer_series_type(s)
    assert res.suggested_type == "string"
    assert res.has_leading_zeros is True


def test_infer_float():
    s = pd.Series(["1.23", "-4.567", "0.0", "1.2e-3"])
    res = infer_series_type(s)
    assert res.suggested_type == "float"
    assert res.confidence == 1.0


def test_infer_date():
    s = pd.Series(["2026-01-15", "2026-02-20", "2026-03-30"])
    res = infer_series_type(s)
    assert res.suggested_type == "date"
    assert res.confidence == 1.0


def test_infer_boolean():
    s = pd.Series(["True", "false", "yes", "NO", "true"])
    res = infer_series_type(s)
    assert res.suggested_type == "boolean"


def test_all_null_series():
    s = pd.Series(["", "NULL", "nan", "-"])
    res = infer_series_type(s)
    assert res.suggested_type == "string"
    assert res.confidence == 0.0
