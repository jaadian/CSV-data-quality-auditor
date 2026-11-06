# Engineering Decisions & Trade-Offs

This document records the foundational architectural decisions (D1–D9) behind `csv-auditor`, articulating the engineering motivations, alternatives considered, and deliberate trade-offs.

---

### D1: Raw Loading as Strings
- **Decision:** Read CSV records with Python's `csv.reader` and construct string-valued pandas chunks. Never allow automatic numeric casting during ingestion.
- **Problem Avoided:** Automatic integer inference converts leading zero identifiers (e.g., zip code `"00123"`, account `"004921"`) into integers (`123`, `4921`), destroying customer primary keys. Furthermore, string `"NaN"` or `"None"` ceases to be ambiguously coerced into float `np.nan`.
- **Trade-Off:** Increased string representation memory overhead during chunk processing compared to dense binary arrays. Chunking reduces peak memory but does not eliminate all memory pressure.

---

### D2: Decoupled Advisory Type Inference
- **Decision:** Separate ingestion from type inference (`csv_auditor.profiling.types`). User-configured rules always supersede inferred heuristics.
- **Problem Avoided:** Inferring types prematurely leads to false positives when encountering mixed-type columns, leading zeros, or exotic date formats.
- **Trade-Off:** Inferred types remain advisory recommendations rather than automatic schema enforcement.

---

### D3: Two-Pass File Inspection
- **Decision:** Execute a two-pass architecture. Pass 1 samples the file header, character encoding, delimiter, and row raggedness. Pass 2 iterates chunked analyzers across the full file.
- **Problem Avoided:** Surfaces common format problems early; malformed records later in the file are still detected by the streaming parser.
- **Trade-Off:** The first 256 KB slice is read twice. The performance cost is negligible (~1 ms) relative to pipeline stability.

---

### D4: Accumulators with Numerical Stability
- **Decision:** Design all analyzers as accumulators (`update(chunk)` and `finalize()`). Implement Welford's algorithm for online variance and standard deviation:
  $$M_k = M_{k-1} + \frac{x_k - M_{k-1}}{k}$$
  $$S_k = S_{k-1} + (x_k - M_{k-1})(x_k - M_k)$$
- **Problem Avoided:** Traditional two-pass sample variance ($S = \sum x^2 - (\sum x)^2 / N$) suffers from catastrophic numerical cancellation and requires retaining all numbers in memory.
- **Trade-Off:** Chunked median is computed exactly up to the reservoir buffer (20,000 samples) and switches to reservoir sampling approximation beyond that scale, marked with an explicit report flag (`is_median_approximate`).

---

### D5: Duplicate Detection Under Bounded Memory
- **Decision:** Hash each length-prefixed row using a 16-byte (128-bit) BLAKE2b digest; key constraints use the same approach. Fallback to a bit-packed Bloom filter when the number of distinct rows exceeds `max_tracked_rows` (config, default 500,000).
- **Problem Avoided:** Retaining millions of string rows in memory causes memory exhaustion and crashes.
- **Trade-Off:** A cryptographic digest still has a nonzero theoretical collision probability. When transitioning to Bloom filter mode, reporting mode is transparently flagged as `"approximate"`. Cross-chunk duplicate tracking is exact below the configured limit; Bloom-filter mode may overcount because of false positives.

---

### D6: Strict Schema Validation
- **Decision:** Validate all YAML configurations using Pydantic v2 models with `extra="forbid"`.
- **Problem Avoided:** Silent rule typos (e.g., `requried: true` or negative weights) leading to false confidence in audit reports.
- **Trade-Off:** Requires an external validation dependency (`pydantic`). In return, users receive precise line-level error messages.

---

### D7: Standardized Deterministic Exit Codes
- **Decision:** Provide POSIX-standard CLI exit codes:
  - `0`: Clean execution (no issues exceeding threshold).
  - `1`: Quality issues detected (meeting or exceeding `--fail-on` severity).
  - `2`: Configuration or CLI usage error.
  - `3`: Input file error (non-existent, 0 bytes, unreadable encoding).
- **Benefit:** Seamless integration into CI/CD pipelines, pre-commit hooks, and orchestrators (Airflow, Dagster, GitHub Actions).

---

### D8: Strict Determinism
- **Decision:** Given identical input CSV data and YAML configuration, output reports should produce identical logical metrics and sorted JSON keys.
- **Problem Avoided:** Non-deterministic key iteration causing phantom git diffs in automated audit repositories.
- **Trade-Off:** The JSON serializer sorts dictionary keys; timestamps and paths are intentionally environment-specific.

---

### D9: Report Safety and Sanitization
- **Decision:** Enforce Jinja2 `autoescape=True` on all HTML templates. Enforce `allow_nan=False` in JSON outputs, replacing `NaN`/`Inf` with `null`. Support explicit column masking (`--mask-columns`).
- **Problem Avoided:** Prevents Cross-Site Scripting (XSS) when untrusted CSV data contains malicious scripts (`<script>alert(1)</script>`) or formula injection strings (`=cmd|...`). Protects Personally Identifiable Information (PII) from leakage.

## D10 — Blank headers are renamed, duplicate headers are rejected

- **Found on:** Ames housing, saved by `DataFrame.to_csv()` with its index, so the first header is empty.
- **Decision:** Rename a blank header to `unnamed_<position>` (adding `_` until the name is free) and raise a medium issue. Keep rejecting duplicate names.
- **Why the difference:** A blank name has an obvious safe placeholder. For two columns both called `amount` there is no safe guess about which rule or key the user meant.

## D11 — Scores round down

- **Found on:** Earthquakes. Three bad dates in 23,412 rows gave 99.996, which `round(x, 2)` printed as a perfect `100.0`.
- **Decision:** Floor every score to two decimals, so 100.00 only appears when nothing was found.

## D12 — Cross-column rules never fall back to text comparison

- **Problem:** If a value was neither a number nor an ISO date, the old code compared the raw strings, so `"abc" >= "10"` passed silently.
- **Decision:** Report such a row as a violation saying the rule could not be evaluated.

## D13 — Full violation counts are part of the result

- **Problem:** `issues` keeps only `max_examples` rows per rule, and `issue_summary` counts those issue entries, not violations. 2,098 negative amounts showed up as "6 high issues".
- **Decision:** Add `rule_violations` (count per rule) and `rows_with_rule_violations` to the result and JSON report. The verifier compares against these.
