import pandas as pd

from csv_auditor.models import ColumnMissingStats, Issue, Severity


def is_missing_value(value: str, markers: set[str], whitespace_as_missing: bool = True) -> bool:
    """Apply the same missing-value policy to validation and profiling."""
    if value == "":
        return True
    if value.isspace():
        return whitespace_as_missing
    return value.strip().casefold() in markers


class MissingValueChecker:
    def __init__(
        self,
        columns: list[str],
        missing_markers: list[str],
        whitespace_as_missing: bool = True,
        required_columns: set[str] | None = None,
    ) -> None:
        self.columns = columns
        self.missing_markers = {marker.casefold() for marker in missing_markers}
        self.whitespace_as_missing = whitespace_as_missing
        self.required_columns = required_columns or set()
        self.missing_counts: dict[str, int] = {col: 0 for col in columns}
        self.total_rows = 0

    def is_cell_missing(self, val: str) -> bool:
        return is_missing_value(val, self.missing_markers, self.whitespace_as_missing)

    def update(self, chunk: pd.DataFrame) -> None:
        self.total_rows += len(chunk)
        for col in self.columns:
            if col not in chunk.columns:
                self.missing_counts[col] += len(chunk)
                continue
            series = chunk[col]
            missing_in_chunk = 0
            for item in series:
                val_str = str(item)
                if self.is_cell_missing(val_str):
                    missing_in_chunk += 1
            self.missing_counts[col] += missing_in_chunk

    def finalize(self) -> tuple[dict[str, ColumnMissingStats], list[Issue]]:
        stats_map: dict[str, ColumnMissingStats] = {}
        issues: list[Issue] = []

        for col in self.columns:
            count = self.missing_counts[col]
            pct = (count / self.total_rows * 100.0) if self.total_rows > 0 else 0.0

            if pct == 0.0:
                severity = Severity.LOW
            elif pct <= 5.0:
                severity = Severity.LOW
            elif pct <= 20.0:
                severity = Severity.MEDIUM
            else:
                severity = Severity.HIGH

            stats_map[col] = ColumnMissingStats(
                column=col,
                missing_count=count,
                total_count=self.total_rows,
                missing_percentage=round(pct, 2),
                severity=severity,
            )

            if count > 0 and col not in self.required_columns:
                # Without this, a column that is 77% empty (Titanic `Cabin`) produced no
                # issue at all, so `--fail-on` could never react to missing data.
                issues.append(
                    Issue(
                        rule_name="missing_values",
                        column=col,
                        message=f"Column '{col}' has {count} missing value(s) ({pct:.1f}%)",
                        severity=severity,
                    )
                )
            if count > 0 and col in self.required_columns:
                issues.append(
                    Issue(
                        rule_name="required_column_missing",
                        column=col,
                        message=f"Required column '{col}' has {count} missing value(s) ({pct:.1f}%)",
                        severity=Severity.HIGH,
                    )
                )

        return stats_map, issues
