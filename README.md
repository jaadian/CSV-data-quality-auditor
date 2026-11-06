# csv-auditor

[![ci](https://github.com/<your-username>/csv-data-quality-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-username>/csv-data-quality-auditor/actions/workflows/ci.yml)

A command-line tool that reads a CSV file in chunks and reports what is wrong with it: missing values, duplicate rows and keys, values that break rules you configure, and columns whose contents do not look like one type. It writes a JSON report for scripts and an HTML report for people. It never changes the data.

```bash
csv-auditor analyze datasets/raw/titanic.csv -c configs/datasets/titanic.yaml
```

```
Data Quality Audit Summary: 97.24/100 (Excellent)
File: datasets/raw/titanic.csv | Rows: 891 | Columns: 12
│ Completeness │  91.90% │        0.30 │
│ Uniqueness   │ 100.00% │        0.25 │
│ Consistency  │  97.80% │        0.15 │
│ Validity     │ 100.00% │        0.30 │
│ High     │     1 │     <- Cabin is 77.1% empty
│ Medium   │     1 │     <- Age is 19.9% empty
│ Low      │     1 │     <- Embarked is 0.2% empty
```

The terminal shows the summary; each issue, with row numbers and examples, is in the reports.

Example reports: [Titanic (HTML)](docs/examples/titanic_audit_report.html), [Titanic (JSON)](docs/examples/titanic_audit_report.json), [Earthquakes (HTML)](docs/examples/earthquakes_audit_report.html).

## Why

Most CSV problems are quiet. `pd.read_csv` turns `00123` into `123`, pads short rows with NaN, renames a duplicate header to `name.1`, and none of it raises an error. This tool reads every cell as a string, refuses malformed rows by default, and reports what it finds instead of guessing.

## Install

```bash
git clone https://github.com/<your-username>/csv-data-quality-auditor.git
cd csv-data-quality-auditor
pip install -e ".[dev]"
```

Python 3.11 or newer.

## Usage

```bash
# Profile a file with no rules: missing values, duplicates, inferred types
csv-auditor analyze data.csv

# Apply rules from YAML and mask a column in the report
csv-auditor analyze data.csv --config rules.yaml --mask-columns email

# File without a header row
csv-auditor analyze data.csv --no-header --columns id,name,amount

# Use as a gate in a pipeline: exit code 1 if any high-severity issue
csv-auditor analyze data.csv --fail-on high
```

Exit codes: `0` ran fine, `1` issues at or above `--fail-on`, `2` bad config or arguments, `3` the input file could not be read safely.

A rules file looks like this (full reference in [docs/validation_rules.md](docs/validation_rules.md)):

```yaml
version: 1
columns:
  customer_id: {type: string, required: true, unique: true}
  age:         {type: integer, min: 0, max: 120}
  email:       {type: string, format: email}
cross_column:
  - {name: end_after_start, rule: "end_date >= start_date", severity: high}
mask_columns: [email]
```

## How it works

1. **Sniff** the first part of the file: encoding (BOM, UTF-8, then charset-normalizer), delimiter, header, row widths.
2. **Stream** the file through Python's `csv` module in chunks. Rows with the wrong number of fields stop the run unless `--on-bad-rows skip` is passed.
3. **Accumulate** per chunk: missing counts, Welford mean and variance, top values, row hashes (128-bit BLAKE2b, length-prefixed fields) and rule checks.
4. **Finalize** into one result, score it, and render JSON and HTML.

Memory grows with the number of distinct rows because each row hash is kept until `max_tracked_rows` (default 500,000). Above that the tool switches to a Bloom filter and marks duplicate counts as `approximate`. Design notes and trade-offs: [docs/engineering_decisions.md](docs/engineering_decisions.md).

## Tested on ten real and synthetic datasets

`scripts/verify_datasets.py` runs the auditor on each dataset and compares every count against a separate reference written with the standard-library `csv` module (it does not import the auditor's checking code). All ten match. Details and what each one found: [docs/dataset_testing.md](docs/dataset_testing.md).

| Dataset | Rows | Duplicate rows | Missing cells | Rule violations | What it caught |
|---|---:|---:|---:|---:|---|
| Titanic | 891 | 0 | 866 | 0 | Cabin 77% empty |
| Iris | 150 | 1 | 0 | 0 | The well-known duplicate row |
| Telco churn | 7,043 | 0 | 11 | 0 | `TotalCharges` is a single space for new customers |
| Ames housing | 2,930 | 0 | 15,749 | 1 | Blank pandas index header; a house sold in 2007 but built in 2008 |
| Apple stock | 506 | 0 | 0 | 0 | Clean (no false positives) |
| Pima diabetes | 768 | 0 | 0 | 51 | Missing readings stored as `0` (glucose 5, blood pressure 35, BMI 11) |
| Diamonds | 53,940 | 146 | 0 | 35 | Zero length/width/depth |
| Seattle weather | 1,461 | 0 | 0 | 0 | Negative temperatures correctly not flagged |
| Earthquakes 1965-2016 | 23,412 | 2 | 0 | 3 | Three rows use ISO timestamps instead of `MM/DD/YYYY` |
| Synthetic (seeded) | 100,000 | 1 | 4,879 | 3,091 | Every injected error, matching the generator's ground truth |

```bash
python scripts/download_datasets.py   # ~5 MB into datasets/raw/, SHA-256 checked
python scripts/generate_synthetic.py
python scripts/verify_datasets.py
```

The data is not committed. Licenses for the upstream copies have not been verified; check them before redistributing.

## Performance

One run per row, Linux, 2-core Xeon at 2.8 GHz, Python 3.13 ([docs/performance.md](docs/performance.md)):

| Rows × columns | Chunk size | Time | Peak RSS |
|---|---:|---:|---:|
| 100,000 × 20 | 10,000 | 10.7 s | 146 MiB |
| 1,000,000 × 20 | 50,000 | 87 s | 293 MiB |

About 10,000 rows per second. It is not fast; row-by-row rule checking in Python is the main cost.

## Tests

```bash
pytest --cov=csv_auditor
ruff check . && ruff format --check .
```

Unit, integration, regression and Hypothesis property tests, including a check that results do not change with chunk size. CI runs them on Python 3.11 to 3.13 and then runs the ten-dataset verification.

## Limitations

- Reports problems; does not fix them.
- Delimited text only. No Excel, JSON, Parquet.
- Single process. Median is approximate above 20,000 values per column.
- The quality score is a heuristic of this project, not a standard. It is cell-weighted, so one bad column in a wide file moves it little (Titanic scores 97 with Cabin 77% empty). Read the issues, not just the number.
- Masking hides values in the chosen columns only. Review a report before sharing it.

More in [docs/limitations.md](docs/limitations.md).

## Development

Built with AI assistance. Design decisions and regression tests are recorded in [CHANGELOG.md](CHANGELOG.md) and [docs/engineering_decisions.md](docs/engineering_decisions.md). For concrete bug walkthroughs and hands-on reflection prompts, see the [engineering learning log](docs/learning_log.md). To review the real repository history and publish without losing commits, see [Git workflow](docs/git_workflow.md).

## License

MIT for the code. The evaluation datasets belong to their owners.
