"""Check the auditor against an independent reference on the ten evaluation datasets.

Usage:
    python scripts/download_datasets.py
    python scripts/generate_synthetic.py
    python scripts/verify_datasets.py

The reference below reads each file with Python's csv module in one pass and
recomputes row/column counts, exact duplicates, missing values, numeric min/max,
unique-key duplicates and every configured rule. It does not import any of the
auditor's checking code, so a bug in the auditor shows up as a mismatch here.

Results are written to docs/verification_results.json.
"""

import csv
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

from csv_auditor.config import load_config
from csv_auditor.core.auditor import CsvAuditor

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "datasets" / "manifests"
RAW = ROOT / "datasets" / "raw"
OUT = ROOT / "docs" / "verification_results.json"

INT_RE = re.compile(r"^[-+]?\d+$")
FLOAT_RE = re.compile(r"^[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?$")


def read_reference(path: Path, meta: dict) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.reader(handle, strict=True) if row]
    if meta.get("no_header"):
        headers = list(meta["columns"])
    else:
        headers, rows = rows[0], rows[1:]
        headers = [h if h.strip() else f"unnamed_{i}" for i, h in enumerate(headers)]
    return headers, rows


def is_missing(value: str, markers: set[str], whitespace: bool) -> bool:
    if value == "":
        return True
    if value.isspace():
        return whitespace
    return value.strip().casefold() in markers


def first_violation(col: str, value: str, rule) -> str | None:
    """Return the rule name the auditor should report for this cell (first failure only)."""
    v = value.strip()
    if rule.type == "integer" and not INT_RE.match(v):
        return f"{col}_type_integer"
    if rule.type == "float" and not FLOAT_RE.match(v):
        return f"{col}_type_float"
    if rule.type == "date" and rule.format:
        try:
            datetime.strptime(v, rule.format)
        except ValueError:
            return f"{col}_date_format"
    if rule.min is not None or rule.max is not None:
        try:
            number = float(v)
        except ValueError:
            number = None
        if number is not None:
            if rule.min is not None and number < rule.min:
                return f"{col}_min_bound"
            if rule.max is not None and number > rule.max:
                return f"{col}_max_bound"
    if rule.allowed is not None and v not in {str(a) for a in rule.allowed}:
        return f"{col}_allowed_values"
    return None


def compare(left: str, right: str, op: str) -> bool:
    try:
        a, b = float(left), float(right)
    except ValueError:
        try:
            a, b = datetime.fromisoformat(left.strip()), datetime.fromisoformat(right.strip())
        except ValueError:
            return False
    return {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b, "==": a == b, "!=": a != b}[op]


def reference(headers: list[str], rows: list[list[str]], config) -> dict:
    markers = {m.casefold() for m in config.missing_markers}
    ws = config.whitespace_as_missing
    missing = {h: 0 for h in headers}
    numeric: dict[str, list[float]] = {h: [] for h in headers}
    violations: dict[str, int] = {}
    keys = [col for col, rule in config.columns.items() if rule.unique]
    key_seen: dict[str, set[str]] = {k: set() for k in keys}
    key_dups = {k: 0 for k in keys}
    index = {h: i for i, h in enumerate(headers)}
    cross = []
    for spec in config.cross_column:
        left, op, right = re.fullmatch(r"(.*?)\s*(>=|<=|!=|==|>|<)\s*(.*)", spec.rule).groups()
        cross.append((spec.name, index[left.strip()], op, index[right.strip()]))

    for row in rows:
        for h, value in zip(headers, row, strict=True):
            if is_missing(value, markers, ws):
                missing[h] += 1
            else:
                try:
                    number = float(value)
                    if math.isfinite(number):
                        numeric[h].append(number)
                except ValueError:
                    pass
        for col, rule in config.columns.items():
            value = row[index[col]]
            if not is_missing(value, markers, ws):
                name = first_violation(col, value, rule)
                if name:
                    violations[name] = violations.get(name, 0) + 1
        for name, li, op, ri in cross:
            left, right = row[li], row[ri]
            if is_missing(left, markers, ws) or is_missing(right, markers, ws):
                continue
            if not compare(left, right, op):
                violations[name] = violations.get(name, 0) + 1
        for k in keys:
            value = row[index[k]]
            if value in key_seen[k]:
                key_dups[k] += 1
            key_seen[k].add(value)

    return {
        "rows": len(rows),
        "columns": len(headers),
        "exact_duplicates": len(rows) - len({tuple(r) for r in rows}),
        "missing": missing,
        "min_max": {h: (min(v), max(v)) for h, v in numeric.items() if v},
        "violations": violations,
        "key_duplicates": key_dups,
    }


def check(manifest: Path) -> dict:
    meta = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    name = meta["name"]
    path = RAW / f"{name}.csv"
    if not path.exists():
        hint = "generate_synthetic.py" if "generator" in meta else "download_datasets.py"
        raise SystemExit(f"{name}: {path} not found. Run scripts/{hint} first.")
    config = load_config(ROOT / meta["config"])

    result = CsvAuditor(config).audit(
        path,
        has_header=False if meta.get("no_header") else None,
        custom_columns=meta.get("columns"),
    )
    headers, rows = read_reference(path, meta)
    ref = reference(headers, rows, config)

    problems = []

    def expect(label, got, want):
        if got != want:
            problems.append(f"{label}: auditor={got} reference={want}")

    expect("rows", result.metadata.total_rows, ref["rows"])
    expect("columns", result.metadata.total_columns, ref["columns"])
    expect("exact duplicates", result.duplicates.exact_duplicate_rows, ref["exact_duplicates"])
    for col, count in ref["missing"].items():
        expect(f"missing[{col}]", result.missing[col].missing_count, count)
    for col, (lo, hi) in ref["min_max"].items():
        stats = result.profiling[col].get("numeric")
        if stats and (abs(stats["min"] - lo) > 1e-4 or abs(stats["max"] - hi) > 1e-4):
            problems.append(
                f"min/max[{col}]: auditor=({stats['min']}, {stats['max']}) reference=({lo}, {hi})"
            )
    expect("rule violations", result.rule_violations, dict(sorted(ref["violations"].items())))
    for key, count in ref["key_duplicates"].items():
        expect(f"key duplicates[{key}]", result.duplicates.key_duplicates.get(key), count)

    truth_file = meta.get("ground_truth")
    if truth_file:
        truth = json.loads((ROOT / truth_file).read_text(encoding="utf-8"))
        expect(
            "truth: duplicates",
            result.duplicates.exact_duplicate_rows,
            truth["injected_cross_chunk_duplicates"],
        )
        expect(
            "truth: negative amounts",
            result.rule_violations.get("amount_min_bound", 0),
            truth["injected_negative_amounts"],
        )
        expect(
            "truth: invalid dates",
            result.rule_violations.get("created_at_date_format", 0),
            truth["injected_invalid_dates"],
        )
        expect(
            "truth: missing notes",
            result.missing["notes"].missing_count,
            truth["injected_missing_notes"],
        )

    return {
        "name": name,
        "rows": ref["rows"],
        "columns": ref["columns"],
        "exact_duplicates": ref["exact_duplicates"],
        "missing_cells": sum(ref["missing"].values()),
        "rule_violations": sum(ref["violations"].values()),
        "key_duplicates": sum(ref["key_duplicates"].values()),
        "quality_score": result.score.overall,
        "status": "pass" if not problems else "fail",
        "problems": problems,
    }


def main() -> None:
    results = [check(m) for m in sorted(MANIFESTS.glob("*.yaml"))]
    print(f"{'dataset':<18}{'rows':>8}{'dups':>6}{'missing':>9}{'violations':>12}  status")
    for r in results:
        print(
            f"{r['name']:<18}{r['rows']:>8}{r['exact_duplicates']:>6}{r['missing_cells']:>9}"
            f"{r['rule_violations']:>12}  {r['status']}"
        )
        for p in r["problems"]:
            print(f"    {p}")
    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    failed = [r["name"] for r in results if r["status"] != "pass"]
    print(f"\n{len(results) - len(failed)}/{len(results)} datasets match the reference.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
