# Validation Rules Reference

`csv-auditor` supports declarative validation rules defined in YAML format. The configuration is schema-validated using Pydantic v2.

## Full Configuration Specification

```yaml
version: 1

# List of string literals treated as null / missing
missing_markers: ["", "NULL", "null", "N/A", "n/a", "NA", "NaN", "nan", "-", "None"]

# Treat whitespace-only strings ("   ") as missing
whitespace_as_missing: true

# Severity threshold to trigger CLI exit code 1: low, medium, or high
fail_on: high

# List of sensitive column names whose sample values will be masked (e.g. '***')
mask_columns: ["customer_email", "phone_number", "ssn"]

# Maximum violation examples to retain per rule
max_examples: 5

# Memory boundary: threshold before duplicate tracker falls back to Bloom filter
max_tracked_rows: 500000

# Chunk size for streaming processing
chunk_size: 50000

# Composite score dimension weights (must sum to 1.0)
score_weights:
  completeness: 0.30
  uniqueness: 0.25
  validity: 0.30
  consistency: 0.15

# Per-column validation specifications
columns:
  customer_id:
    type: string
    required: true
    unique: true
    min_length: 5
    max_length: 20

  age:
    type: integer
    min: 0
    max: 120
    severity: high

  account_balance:
    type: float
    min: 0.00
    severity: medium

  email:
    type: string
    format: email
    severity: high

  status:
    type: string
    allowed: ["active", "pending", "churned", "suspended"]
    severity: high

  signup_date:
    type: date
    format: "%Y-%m-%d"
    severity: medium

  phone:
    type: string
    regex: "^\\+?[1-9]\\d{1,14}$"
    severity: low

# Cross-column relationship assertions
cross_column:
  - name: valid_date_order
    rule: "end_date >= start_date"
    severity: high

  - name: total_greater_than_subtotal
    rule: "total_amount >= subtotal"
    severity: high
```

## Supported Rule Attributes

| Attribute | Type | Description |
|---|---|---|
| `type` | `string` | Target datatype: `integer`, `float`, `date`, `boolean`, `string` |
| `required` | `boolean` | Requires column to have 0% missing values |
| `unique` | `boolean` | Values must be distinct. Blank values are compared too, so two empty IDs count as a duplicate |
| `min` | `number` | Minimum numerical value bound (inclusive) |
| `max` | `number` | Maximum numerical value bound (inclusive) |
| `min_length` | `integer` | Minimum character length for text |
| `max_length` | `integer` | Maximum character length for text |
| `allowed` | `list` | Discrete enumeration of allowable string values |
| `format` | `string` | Predefined format: `email`, or strptime date format (e.g., `"%Y-%m-%d"`) |
| `regex` | `string` | Regular expression pattern that values must match |
| `severity` | `string` | Violation classification: `low`, `medium`, `high` |

## Cross-Column Operators

Cross-column rules evaluate comparative assertions between two columns in each row without using Python's unsafe `eval()`:
- `>=` : Greater than or equal to
- `<=` : Less than or equal to
- `==` : Strict equality
- `!=` : Inequality
- `>`  : Strict greater than
- `<`  : Strict less than

Both sides are parsed as numbers first, then as ISO-8601 dates. If neither works for both values, the row is reported as a violation ("could not be evaluated"). It is never compared as text: `"abc" >= "10"` would otherwise pass. Rows where either side is missing are skipped.

Column names may contain spaces and dots (`Yr Sold >= Year Built`, `AAPL.High >= AAPL.Low`).

## Order of checks

Missing cells are skipped by every rule (use `required: true` to flag them). For other cells the checks run in this order and **only the first failure is reported**:

1. `type`
2. `format` (date or email)
3. `regex`
4. `min`, then `max`
5. `min_length`, then `max_length`
6. `allowed`

So `-5` with `type: integer, min: 0` is one `min_bound` violation, and `abc` with the same rule is one `type_integer` violation.

## Where violations appear

- `issues`: up to `max_examples` rows per rule, with row numbers counted from the first data row (1-based, header excluded), plus one summary line for the rest.
- `rule_violations`: the full count per rule name, e.g. `{"glucose_min_bound": 5}`.
- `rows_with_rule_violations`: rows with at least one violation. This drives the Validity score.

Examples for each evaluation dataset are in [`configs/datasets/`](../configs/datasets/).
