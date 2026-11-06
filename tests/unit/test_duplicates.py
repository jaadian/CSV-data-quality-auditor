import pandas as pd

from csv_auditor.checks.duplicates import DuplicateChecker


def test_exact_duplicates_across_chunks():
    checker = DuplicateChecker()
    chunk1 = pd.DataFrame({"id": ["1", "2"], "val": ["A", "B"]})
    chunk2 = pd.DataFrame({"id": ["3", "1"], "val": ["C", "A"]})

    checker.update(chunk1)
    checker.update(chunk2)

    report, issues = checker.finalize()
    assert report.total_rows == 4
    assert report.exact_duplicate_rows == 1
    assert report.unique_rows == 3
    assert any(i.rule_name == "exact_duplicate_rows" for i in issues)


def test_key_duplicates():
    checker = DuplicateChecker(key_columns=[["user_id"]])
    chunk = pd.DataFrame(
        {
            "user_id": ["u1", "u2", "u1", "u3"],
            "action": ["login", "view", "logout", "view"],
        }
    )
    checker.update(chunk)
    report, issues = checker.finalize()
    assert report.key_duplicates["user_id"] == 1
    assert "u1" in report.sample_duplicate_keys["user_id"]
    assert any(i.rule_name == "key_uniqueness_violation" for i in issues)


def test_bloom_filter_fallback():
    checker = DuplicateChecker(max_tracked_rows=5)
    df = pd.DataFrame({"id": [str(i) for i in range(10)]})
    checker.update(df)
    report, _ = checker.finalize()
    assert report.mode == "approximate"
