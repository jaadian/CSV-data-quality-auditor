# Engineering learning log

This is a technical record of what changed while the CSV auditor was being tested. The examples below come from the code, regression tests and dataset notes in this repository. They are **not** a claim that every experiment was personally performed by the repository owner.

A useful way to turn this into a personal learning log: run the linked test, read the implementation, change one thing in a throwaway branch, and add two or three sentences in your own words about what you observed. Don't break the release branch just to recreate an old bug.

## Why this project took more than a `read_csv()` call

A CSV can look fine and still be wrong. An ID such as `00123` is not the number 123; an empty cabin field may be an important warning even if the schema does not say `required: true`; and a high overall quality score can hide a serious problem in one column. That is why ingestion, profiling, rule checks, scoring and reporting are separate modules.

The main design trade-off is deliberate: read values as strings first, then infer types *advisably*. It costs some performance, but avoids changing the source data before we know what a column means.

## Eight cases worth understanding

### 1. Missing data was counted but not raised as an issue

**Dataset:** Titanic. `Cabin` is missing for most passengers.

**Problem:** The original missing-value checker created issues only for columns marked as required. A report could show a large missing percentage and still have no issue for the CLI's severity threshold to act on.

**Change:** `MissingValueChecker.finalize()` now reports missing values in optional columns too, with severity based on the missing percentage. Required columns keep a separate, high-severity rule.

**Check:** `tests/regression/test_hardening.py::test_optional_column_missing_values_raise_issue`

**Lesson:** A metric is not the same as an actionable warning. I should check both what is calculated and what is surfaced to users.

### 2. Age looked like an integer until one decimal appeared

**Dataset:** Titanic (`Age` contains values such as `28.5`).

**Problem:** Integer-looking entries dominated the type vote, even though the column also contained fractional numbers. Suggesting `integer` for the whole column was misleading.

**Change:** When integer and floating-point values coexist, the type inference combines them into the floating-point category. Ingestion still preserves the original text.

**Check:** `tests/regression/test_hardening.py::test_mixed_int_and_float_column_inferred_as_float`

**Lesson:** A column's most frequent format is not necessarily its correct type. Type inference is a hint, not a schema contract.

### 3. An empty header prevented a useful audit

**Dataset:** Ames housing, where an exported index creates a blank first header.

**Problem:** Rejecting every empty header made the tool fail on a dataset that could be read safely.

**Change:** The parser assigns a collision-free name such as `unnamed_0` and emits a warning. Actual duplicate header names still cause an error because the tool cannot know which column a rule should reference.

**Checks:** `test_blank_headers_renamed_and_flagged`, `test_blank_header_rename_avoids_collision`, `test_duplicate_headers_fail`

**Lesson:** Input validation should distinguish recoverable formatting problems from ambiguity that would make results unreliable.

### 4. A score of 100 hid a few bad dates

**Dataset:** Earthquakes, with three dates that did not match the configured format.

**Problem:** Rounding a score close to 100 to two decimal places could display `100.0`, even when rule violations existed.

**Change:** The scoring module floors to two decimal places instead of rounding to nearest. The issue details remain the authoritative result.

**Check:** `test_score_below_100_when_any_issue_exists`

**Lesson:** Formatting a metric is part of its meaning. A rounded summary should never contradict the detailed findings. The score is still a heuristic, not a guarantee of data quality.

### 5. A cross-column rule could compare unrelated strings

**Example:** `b >= a` with values `a=10`, `b=abc`.

**Problem:** A fallback lexical comparison could silently return a result for values that were neither compatible numbers nor dates.

**Change:** Uncomparable values produce a rule violation explaining that the comparison could not be evaluated.

**Check:** `test_cross_column_uncomparable_values_are_reported`

**Lesson:** A failed conversion is not permission to guess. An explicit error is better than a plausible-looking wrong answer.

### 6. Masking worked in one field but leaked through messages

**Example:** A protected `salary` column with an out-of-range value.

**Problem:** The structured sample value could be masked while the free-text error message still contained the raw number.

**Change:** Range-violation messages now respect masked columns. Other report fields, such as sample rows and top categorical values, have separate masking checks.

**Checks:** `test_range_violation_message_respects_masking`, `test_masked_data_not_exposed_in_report`

**Lesson:** Privacy must be checked at every output boundary, not just where the first sample value is stored. Masking is limited to columns the user explicitly selects.

### 7. An absolute file path could reveal a local directory

**Example:** Auditing `/home/person/private-data/customers.csv`.

**Problem:** Replacing `path.resolve()` with `str(path)` reduced path disclosure for relative inputs, but **still** exposed the full directory if the caller supplied an absolute path.

**Change:** Report metadata now uses the input filename (`path.name`), not the full path. The file is still read from the path the user provided; only the report label changes.

**Check:** `test_report_does_not_disclose_absolute_input_path`

**Lesson:** A fix must be tested against the original failure mode *and* nearby cases. Relative-path tests alone would not catch this.

### 8. The HTML report recommended a schema fix without a schema failure

**Dataset:** Titanic.

**Problem:** The recommendation builder treated high-severity issues as though they were all rule violations. Missing values could trigger a 'Schema Validation' recommendation even when no schema rule failed.

**Change:** The recommendation now relies on actual rule-violation totals, not the severity of unrelated issues.

**Check:** `test_validation_recommendation_only_for_rule_violations`

**Lesson:** Different kinds of problems need different labels. Severity tells us how urgent an issue is; category tells us what actually went wrong.

## Tests and trade-offs to be ready to discuss

- **Streaming:** The parser processes chunks instead of loading an entire file into one DataFrame. Exact duplicate tracking still consumes memory until it reaches its configured limit; after that, the report marks estimates as approximate.
- **Independent checks:** `scripts/verify_datasets.py` uses a separate standard-library implementation to compare counts. This helps catch mistakes that would be invisible if the test simply reused the same auditing functions.
- **Real data matters:** The dataset notes include clean data, missing fields, quoted CSV values, a headerless file, scientific measurements and seeded corruptions. A good test suite needs both expected successes and expected failures.
- **A high score can be misleading:** The overall score combines several dimensions. Always inspect per-column issues, rule violations and the rules that were actually configured.

## Reproduce a case locally

Install the development dependencies and run a single regression test:

```bash
python -m pip install -e ".[dev]"
pytest -q tests/regression/test_hardening.py::test_score_below_100_when_any_issue_exists
```

To explore a fix without changing the release branch:

```bash
git switch -c learning/score-rounding
# Make a temporary change in src/csv_auditor/scoring/quality_score.py
pytest -q tests/regression/test_hardening.py::test_score_below_100_when_any_issue_exists
# Restore the file after observing the result
git restore src/csv_auditor/scoring/quality_score.py
git switch main
```

## Personal reflections — add after doing the exercises

- **The bug I reproduced myself:** _Write the test name, what failed and why._
- **The fix I can explain without looking at code:** _Explain the trade-off in your own words._
- **Something I initially misunderstood:** _Describe the wrong assumption and how you checked it._
- **One change I would make next:** _A small improvement, its test, and why it matters._

The project used AI assistance; the point of this log is to make its engineering decisions inspectable and to support hands-on learning, not to manufacture a personal development story.
