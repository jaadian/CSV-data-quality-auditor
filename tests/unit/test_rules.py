import pandas as pd

from csv_auditor.checks.rules import RuleEngine
from csv_auditor.config import AuditorConfig, ColumnRule, CrossColumnRule


def test_column_rule_bounds_and_format():
    config = AuditorConfig(
        columns={
            "age": ColumnRule(type="integer", min=0, max=100),
            "email": ColumnRule(type="string", format="email"),
            "status": ColumnRule(type="string", allowed=["active", "inactive"]),
        },
        mask_columns=["email"],
    )
    engine = RuleEngine(config)
    df = pd.DataFrame(
        {
            "age": ["25", "-5", "150"],
            "email": ["valid@test.com", "not-an-email", "user@domain.org"],
            "status": ["active", "unknown", "inactive"],
        }
    )
    engine.update(df, start_row_idx=1)
    issues, counts, rows_with_violations = engine.finalize()

    assert counts.get("age_min_bound", 0) == 1
    assert counts.get("age_max_bound", 0) == 1
    assert counts.get("email_email_format", 0) == 1
    assert counts.get("status_allowed_values", 0) == 1
    assert rows_with_violations == 2

    email_issue = next(i for i in issues if i.rule_name == "email_email_format")
    assert email_issue.sample_value == "***"


def test_cross_column_rule():
    config = AuditorConfig(
        cross_column=[CrossColumnRule(name="valid_dates", rule="end_date >= start_date")]
    )
    engine = RuleEngine(config)
    df = pd.DataFrame(
        {
            "start_date": ["2026-01-01", "2026-05-01"],
            "end_date": ["2026-01-10", "2026-04-01"],
        }
    )
    engine.update(df, start_row_idx=1)
    issues, counts, rows_with_violations = engine.finalize()

    assert counts.get("valid_dates", 0) == 1
    assert rows_with_violations == 1
