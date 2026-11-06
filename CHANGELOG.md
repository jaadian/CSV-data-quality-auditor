# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
- Shared reports now show only the input filename, including when the caller supplies an absolute path. Added a regression test for this case.

### Documentation
- Added a technical learning log with reproducible bug walkthroughs and personal reflection prompts.
- Documented the authentic Git import history and publishing steps.

## [1.1.0] - 2026-11-05

Tested on ten full datasets instead of ten-row samples. Every fix below has a regression test in `tests/regression/test_hardening.py`.

### Fixed
- Missing values in non-required columns now raise an issue (low/medium/high by percentage). Before, Titanic with Cabin 77% empty reported zero issues and `--fail-on` could not react.
- Type inference counts integers as floats when a column has both, so Titanic `Age` is `float`, not `integer`.
- A blank header (pandas index column, as in Ames housing) is renamed `unnamed_<position>` with a medium issue instead of stopping the run. Duplicate headers are still rejected.
- Scores round down, so a file with problems never shows 100.00 (earthquakes was printing 100.0 with three bad dates).
- Cross-column rules report values that are neither numbers nor ISO dates instead of comparing them as text.
- `min`/`max` violation messages respected masking in `sample_value` but printed the raw number in `message`.
- Reports store the input path as given instead of the resolved absolute path, which exposed local home directories.
- The "Schema Validation" recommendation counted every high-severity issue, so a file with no rule violations was told it had validation failures. It now uses rule violation totals.
- HTML report labelled columns with 0% missing as "low" severity; they now show "none".
- CI installed no `jsonschema`, so the schema test failed to import on every Python version.

### Added
- `rule_violations` and `rows_with_rule_violations` in the result and JSON report: full counts, not just the first `max_examples` rows per rule.
- Ten dataset manifests with real URLs and SHA-256 of the downloaded file, and a rules file per dataset in `configs/datasets/`.
- `scripts/download_datasets.py` actually downloads and checks hashes (it previously wrote hard-coded ten-row samples).
- `scripts/verify_datasets.py` compares the auditor with an independent standard-library reference on all ten datasets, including the synthetic ground truth. Runs as its own CI job.
- `scripts/benchmark.py` measures each run in a fresh process with peak RSS, without `tracemalloc`.

### Changed
- CI runs full `ruff check`, `ruff format --check` and `mypy` (it only checked syntax errors before). Type stubs added to dev dependencies.
- Packaging uses an SPDX `license = "MIT"` (setuptools 77+).
- Removed the ten-row samples, DuckDB dependency and `verify_samples_stdlib.py`.
- Rewrote the docs to match the code (hash size, performance figures, dataset results).

## [1.0.1] - 2026-11-05

### Fixed
- Malformed row widths stop the run by default instead of being skipped or padded.
- Duplicate and blank headers are rejected instead of silently renamed by pandas.
- Row hashes length-prefix each field and use 128-bit BLAKE2b, so different rows cannot produce the same hash input.
- Key-uniqueness tracking falls back to a Bloom filter with `mode: approximate` instead of silently stopping.
- `mask_columns` also masks sample rows, top values and duplicate-key examples.
- Rules for unknown columns, invalid limits and unsupported types are config errors.
- UTF-16 BOM decoding; missing-value markers handled the same way in profiling and validation.
- HTML template included in built wheels.

## [1.0.0] - 2026-11-05

### Added
- `csv-auditor analyze` CLI with JSON and HTML reports and exit codes 0-3.
- Two-pass reader: sniff encoding, delimiter and header, then stream chunks as strings.
- Profiling: Welford mean/std, reservoir median, top values, string lengths, advisory type inference with leading-zero detection.
- Checks: missing values, exact and key duplicates, YAML rules with Pydantic validation, cross-column comparisons.
- Quality score over completeness, uniqueness, validity and consistency, renormalised when no rules are given.
- Unit, integration, regression and Hypothesis tests; GitHub Actions on Python 3.11-3.13.
