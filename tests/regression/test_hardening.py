"""Regression cases identified in the release review."""

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from csv_auditor.checks.duplicates import DuplicateChecker
from csv_auditor.config import AuditorConfig, ColumnRule, CrossColumnRule
from csv_auditor.core.auditor import CsvAuditor
from csv_auditor.exceptions import ConfigError, EncodingError, InputFileError
from csv_auditor.reporting.json_report import generate_json_report


def csv_file(tmp_path: Path, text: str, encoding: str = "utf-8") -> Path:
    path = tmp_path / "input.csv"
    path.write_text(text, encoding=encoding)
    return path


def test_utf16_bom_roundtrip(tmp_path):
    result = CsvAuditor().audit(csv_file(tmp_path, "id,name\n001,José\n002,Sara\n", "utf-16"))
    assert result.metadata.column_names == ["id", "name"]
    assert result.metadata.sample_rows[0] == ["001", "José"]


def test_duplicate_headers_fail(tmp_path):
    with pytest.raises(InputFileError, match="headers must be unique"):
        CsvAuditor().audit(csv_file(tmp_path, "a,a\n1,2\n"))


@pytest.mark.parametrize(
    ("header", "expected"), [("a,", ["a", "unnamed_1"]), (",a", ["unnamed_0", "a"])]
)
def test_blank_headers_renamed_and_flagged(tmp_path, header, expected):
    # Found on the Ames housing CSV, which was saved with a pandas index column.
    result = CsvAuditor().audit(csv_file(tmp_path, f"{header}\n1,2\n"))
    assert result.metadata.column_names == expected
    assert any("Renamed blank" in i.message and i.severity == "medium" for i in result.issues)


def test_blank_header_rename_avoids_collision(tmp_path):
    result = CsvAuditor().audit(csv_file(tmp_path, "unnamed_0,,b\n1,2,3\n"))
    assert result.metadata.column_names == ["unnamed_0", "unnamed_1", "b"]


def test_optional_column_missing_values_raise_issue(tmp_path):
    # Titanic `Cabin` is 77% empty; the old checker only reported required columns.
    result = CsvAuditor().audit(csv_file(tmp_path, "a,b\n1,\n2,\n3,\n4,x\n"))
    issue = next(i for i in result.issues if i.rule_name == "missing_values")
    assert issue.column == "b" and issue.severity == "high"


def test_mixed_int_and_float_column_inferred_as_float(tmp_path):
    rows = "\n".join(["22", "38", "26", "28.5", "35"])
    result = CsvAuditor().audit(csv_file(tmp_path, f"age\n{rows}\n"))
    assert result.types["age"].suggested_type == "float"


@pytest.mark.parametrize("row", ["1", "1,2,3"])
def test_ragged_rows_fail(tmp_path, row):
    with pytest.raises(InputFileError, match="Malformed CSV record"):
        CsvAuditor().audit(csv_file(tmp_path, f"a,b\n0,0\n{row}\n"))


def test_skip_mode_explicit_and_flagged(tmp_path):
    result = CsvAuditor().audit(csv_file(tmp_path, "a,b\n1,2\n3\n4,5\n"), on_bad_rows="skip")
    assert result.metadata.total_rows == 2
    assert any(i.rule_name == "ingestion_skip_policy" for i in result.issues)


def test_unknown_schema_column_rejected(tmp_path):
    cfg = AuditorConfig(columns={"not_present": ColumnRule(required=True)})
    with pytest.raises(ConfigError, match="unknown columns"):
        CsvAuditor(cfg).audit(csv_file(tmp_path, "a,b\n1,2\n"))


def test_unknown_unique_key_rejected(tmp_path):
    with pytest.raises(ConfigError, match="Unknown unique-key"):
        CsvAuditor().audit(csv_file(tmp_path, "a,b\n1,2\n"), unique_keys=[["not_present"]])


def test_masked_data_not_exposed_in_report(tmp_path):
    secret = "secret-user-78231@example.test"
    cfg = AuditorConfig(columns={"email": ColumnRule(unique=True)}, mask_columns=["email"])
    result = CsvAuditor(cfg).audit(csv_file(tmp_path, f"email,amount\n{secret},10\n{secret},10\n"))
    assert result.duplicates.sample_duplicate_keys["email"] == ["***"]
    assert result.metadata.sample_rows[0][0] == "***"
    assert result.profiling["email"]["categorical"]["top_values"] == {}
    assert secret not in generate_json_report(result)


def test_row_hash_has_unambiguous_field_boundaries():
    checker = DuplicateChecker()
    checker.update(pd.DataFrame({"a": ["a\x1fb", "a"], "b": ["c", "b\x1fc"]}))
    report, _ = checker.finalize()
    assert report.exact_duplicate_rows == 0


def test_key_bloom_fallback_flagged_approximate():
    checker = DuplicateChecker(key_columns=[["id"]], max_tracked_rows=2)
    checker.update(pd.DataFrame({"id": [str(i) for i in range(10)]}))
    report, _ = checker.finalize()
    assert report.mode == "approximate"


@pytest.mark.parametrize(
    "settings", [{"chunk_size": 0}, {"max_examples": 0}, {"max_tracked_rows": 0}]
)
def test_invalid_runtime_limits_rejected(settings):
    with pytest.raises(ValidationError):
        AuditorConfig(**settings)


def test_invalid_type_rejected():
    with pytest.raises(ValidationError):
        ColumnRule(type="magical_number")


def test_cross_column_unknown_rejected(tmp_path):
    cfg = AuditorConfig(cross_column=[CrossColumnRule(name="check", rule="a <= missing")])
    with pytest.raises(ConfigError):
        CsvAuditor(cfg).audit(csv_file(tmp_path, "a,b\n1,2\n"))


def test_invalid_encoding_is_input_error(tmp_path):
    with pytest.raises(EncodingError):
        CsvAuditor().audit(csv_file(tmp_path, "a,b\n1,2\n"), user_encoding="not-an-encoding")


def test_headerless_csv_with_names(tmp_path):
    file = csv_file(tmp_path, "001,Ali\n002,Sara\n")
    result = CsvAuditor().audit(file, has_header=False, custom_columns=["id", "name"])
    assert result.metadata.total_rows == 2
    assert result.metadata.column_names == ["id", "name"]
    assert result.metadata.sample_rows[0] == ["001", "Ali"]


def test_whitespace_and_marker_policy_consistent(tmp_path):
    file = csv_file(tmp_path, "value\n NULL \n \n7\n")
    result = CsvAuditor().audit(file)
    assert result.missing["value"].missing_count == 2
    assert result.profiling["value"]["string"]["null_count"] == 2


def test_cross_column_uncomparable_values_are_reported(tmp_path):
    # Previously fell back to string comparison: "abc" >= "10" passed silently.
    cfg = AuditorConfig(cross_column=[CrossColumnRule(name="b_ge_a", rule="b >= a")])
    result = CsvAuditor(cfg).audit(csv_file(tmp_path, "a,b\n10,abc\n1,2\n"))
    assert result.rule_violations == {"b_ge_a": 1}
    assert (
        "could not be evaluated"
        in next(i for i in result.issues if i.rule_name == "b_ge_a").message
    )


def test_rule_violation_totals_exceed_examples(tmp_path):
    cfg = AuditorConfig(columns={"n": ColumnRule(type="integer", min=0)}, max_examples=2)
    rows = "\n".join(["-1"] * 7)
    result = CsvAuditor(cfg).audit(csv_file(tmp_path, f"n\n{rows}\n"))
    assert sum(result.rule_violations.values()) == 7
    assert result.rows_with_rule_violations == 7


def test_range_violation_message_respects_masking(tmp_path):
    # min/max messages printed the raw number even for masked columns.
    cfg = AuditorConfig(columns={"salary": ColumnRule(min=0)}, mask_columns=["salary"])
    result = CsvAuditor(cfg).audit(csv_file(tmp_path, "salary\n-98765\n"))
    assert all("98765" not in i.message for i in result.issues)


def test_score_below_100_when_any_issue_exists(tmp_path):
    # 3 bad dates in 23,412 earthquake rows used to round up to a perfect 100.0.
    rows = "\n".join(["2020-01-01"] * 9999 + ["not-a-date"])
    cfg = AuditorConfig(columns={"d": ColumnRule(type="date", format="%Y-%m-%d")})
    result = CsvAuditor(cfg).audit(csv_file(tmp_path, f"d\n{rows}\n"))
    assert result.score.overall < 100.0


def test_validation_recommendation_only_for_rule_violations(tmp_path):
    # A 75%-empty column is a high issue but not a schema validation failure.
    result = CsvAuditor().audit(csv_file(tmp_path, "a,b\n1,\n2,\n3,\n4,x\n"))
    assert all(r.category != "Schema Validation" for r in result.recommendations)
