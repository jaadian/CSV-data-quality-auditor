import pandas as pd

from csv_auditor.checks.missing import MissingValueChecker
from csv_auditor.models import Severity


def test_missing_checker_zero_and_false_are_not_missing():
    checker = MissingValueChecker(
        columns=["num", "flag", "empty_col"],
        missing_markers=["", "NULL", "N/A"],
        whitespace_as_missing=True,
    )
    df = pd.DataFrame(
        {
            "num": ["0", "1", "0"],
            "flag": ["False", "true", "false"],
            "empty_col": ["", "  ", "NULL"],
        }
    )
    checker.update(df)
    stats, issues = checker.finalize()

    assert stats["num"].missing_count == 0
    assert stats["flag"].missing_count == 0
    assert stats["empty_col"].missing_count == 3
    assert stats["empty_col"].missing_percentage == 100.0
    assert stats["empty_col"].severity == Severity.HIGH


def test_missing_checker_required_column_triggers_issue():
    checker = MissingValueChecker(
        columns=["req_id", "optional_val"],
        missing_markers=[""],
        required_columns={"req_id"},
    )
    df = pd.DataFrame(
        {
            "req_id": ["1", "", "3"],
            "optional_val": ["a", "b", ""],
        }
    )
    checker.update(df)
    stats, issues = checker.finalize()

    assert stats["req_id"].missing_count == 1
    assert any(i.rule_name == "required_column_missing" and i.column == "req_id" for i in issues)
