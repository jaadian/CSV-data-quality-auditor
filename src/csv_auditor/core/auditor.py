from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from csv_auditor import __version__
from csv_auditor.checks.duplicates import DuplicateChecker
from csv_auditor.checks.missing import MissingValueChecker
from csv_auditor.checks.rules import OP_REGEX, RuleEngine
from csv_auditor.config import AuditorConfig
from csv_auditor.exceptions import ConfigError, InputFileError
from csv_auditor.ingestion.loader import iter_chunks
from csv_auditor.ingestion.sniffer import SniffResult, sniff_csv
from csv_auditor.models import (
    AuditResult,
    DatasetMetadata,
    DuplicateReport,
    Issue,
    Recommendation,
    Severity,
)
from csv_auditor.profiling.profiler import DatasetProfiler
from csv_auditor.scoring.quality_score import QualityScoreCalculator


class CsvAuditor:
    def __init__(self, config: AuditorConfig | None = None) -> None:
        self.config = config or AuditorConfig()

    def audit(
        self,
        file_path: str | Path,
        user_encoding: str | None = None,
        user_delimiter: str | None = None,
        unique_keys: list[list[str]] | None = None,
        on_bad_rows: str = "error",
        max_size_mb: float | None = None,
        has_header: bool | None = None,
        custom_columns: list[str] | None = None,
    ) -> AuditResult:
        path = Path(file_path)
        sniff_result: SniffResult = sniff_csv(
            path,
            user_encoding=user_encoding,
            user_delimiter=user_delimiter,
            max_size_mb=max_size_mb,
            has_header=has_header,
            custom_columns=custom_columns,
        )

        stripped_headers = [name.strip() for name in sniff_result.headers]
        if len(set(stripped_headers)) != len(stripped_headers):
            raise InputFileError(
                "CSV headers must be unique; rename duplicate columns before auditing"
            )
        if not sniff_result.headers:
            raise InputFileError("CSV contains no usable header columns")
        cross_columns: set[str] = set()
        for rule in self.config.cross_column:
            match = OP_REGEX.fullmatch(rule.rule)
            if match is None or not match.group(1).strip() or not match.group(3).strip():
                raise ConfigError(f"Invalid cross-column rule: {rule.rule}")
            cross_columns.update((match.group(1).strip(), match.group(3).strip()))
        unknown = (set(self.config.columns) | cross_columns) - set(sniff_result.headers)
        if unknown:
            raise ConfigError(
                f"Validation rules refer to unknown columns: {', '.join(sorted(unknown))}"
            )

        all_unique_keys: list[list[str]] = []
        if unique_keys:
            all_unique_keys.extend(unique_keys)
        for col_name, col_rule in self.config.columns.items():
            if col_rule.unique and [col_name] not in all_unique_keys:
                all_unique_keys.append([col_name])

        for keys in all_unique_keys:
            unknown_keys = set(keys) - set(sniff_result.headers)
            if unknown_keys:
                raise ConfigError(f"Unknown unique-key columns: {', '.join(sorted(unknown_keys))}")

        required_cols = {col for col, r in self.config.columns.items() if r.required}

        missing_checker = MissingValueChecker(
            columns=sniff_result.headers,
            missing_markers=self.config.missing_markers,
            whitespace_as_missing=self.config.whitespace_as_missing,
            required_columns=required_cols,
        )

        duplicate_checker = DuplicateChecker(
            key_columns=all_unique_keys,
            max_tracked_rows=self.config.max_tracked_rows,
            max_examples=self.config.max_examples,
            mask_columns=set(self.config.mask_columns),
        )

        profiler = DatasetProfiler(
            columns=sniff_result.headers,
            missing_markers=self.config.missing_markers,
        )

        rule_engine = RuleEngine(self.config)

        total_row_count = 0
        for chunk in iter_chunks(
            path,
            sniff_result=sniff_result,
            chunk_size=self.config.chunk_size,
            on_bad_rows=on_bad_rows,
        ):
            chunk_rows = len(chunk)
            missing_checker.update(chunk)
            duplicate_checker.update(chunk)
            profiler.update(chunk)
            rule_engine.update(chunk, start_row_idx=total_row_count + 1)
            total_row_count += chunk_rows

        missing_stats, missing_issues = missing_checker.finalize()
        duplicate_report, duplicate_issues = duplicate_checker.finalize()
        inferred_types, profiling_results = profiler.finalize()
        rule_issues, violation_counts, rows_with_rule_violations = rule_engine.finalize()

        has_rules = bool(self.config.columns or self.config.cross_column)
        score_calc = QualityScoreCalculator(self.config.score_weights)
        score = score_calc.calculate(
            missing_stats=missing_stats,
            total_rows=total_row_count,
            duplicate_rows=duplicate_report.exact_duplicate_rows,
            inferred_types=inferred_types,
            rows_with_rule_violations=rows_with_rule_violations,
            has_rules=has_rules,
        )

        all_issues: list[Issue] = []
        if on_bad_rows == "skip":
            all_issues.append(
                Issue(
                    rule_name="ingestion_skip_policy",
                    message="Malformed rows may have been discarded because skip mode was selected; totals only include accepted rows",
                    severity=Severity.HIGH,
                )
            )
        for warn in sniff_result.warnings:
            all_issues.append(
                Issue(
                    rule_name="ingestion_warning",
                    message=warn,
                    severity=Severity.HIGH
                    if "Duplicate column" in warn or "Ragged" in warn
                    else Severity.MEDIUM
                    if "Renamed blank" in warn
                    else Severity.LOW,
                )
            )

        all_issues.extend(missing_issues)
        all_issues.extend(duplicate_issues)
        all_issues.extend(rule_issues)

        issue_summary: dict[str, int] = {
            "high": sum(1 for i in all_issues if i.severity == Severity.HIGH),
            "medium": sum(1 for i in all_issues if i.severity == Severity.MEDIUM),
            "low": sum(1 for i in all_issues if i.severity == Severity.LOW),
        }

        recommendations = self._generate_recommendations(
            sniff_result=sniff_result,
            missing_stats=missing_stats,
            duplicate_report=duplicate_report,
            inferred_types=inferred_types,
            all_issues=all_issues,
            rule_violations=violation_counts,
        )

        # Mask at the data boundary, not only in rule-error messages. The sample and
        # categorical top-values would otherwise expose protected data in both reports.
        masked = set(self.config.mask_columns)
        for col in masked:
            if col in profiling_results:
                profiling_results[col]["categorical"]["top_values"] = {}
        # Sniffer sample rows may be ragged (they are reported, not rejected), so the
        # zip is deliberately non-strict here.
        safe_samples = [
            [
                "***" if header in masked else value
                for header, value in zip(sniff_result.headers, row, strict=False)
            ]
            for row in sniff_result.sample_rows
        ]
        metadata = DatasetMetadata(
            file_path=path.name,  # Reports must not disclose the caller's directory structure.
            file_size_bytes=sniff_result.file_size_bytes,
            encoding=sniff_result.encoding,
            delimiter=sniff_result.delimiter,
            total_rows=total_row_count,
            total_columns=len(sniff_result.headers),
            column_names=sniff_result.headers,
            sample_rows=safe_samples,
            sniff_warnings=sniff_result.warnings,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            auditor_version=__version__,
        )

        return AuditResult(
            metadata=metadata,
            score=score,
            missing=missing_stats,
            duplicates=duplicate_report,
            types=inferred_types,
            profiling=profiling_results,
            issues=all_issues,
            issue_summary=issue_summary,
            rule_violations=dict(sorted(violation_counts.items())),
            rows_with_rule_violations=rows_with_rule_violations,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        sniff_result: SniffResult,
        missing_stats: dict[str, Any],
        duplicate_report: DuplicateReport,
        inferred_types: dict[str, Any],
        all_issues: list[Issue],
        rule_violations: dict[str, int],
    ) -> list[Recommendation]:
        recommendations: list[Recommendation] = []

        if duplicate_report.exact_duplicate_rows > 0:
            recommendations.append(
                Recommendation(
                    category="Uniqueness",
                    issue=f"Encountered {duplicate_report.exact_duplicate_rows} duplicate row(s)",
                    suggested_action="Deduplicate dataset before downstream loading; consider primary key constraints",
                )
            )

        high_missing_cols = [col for col, s in missing_stats.items() if s.missing_percentage > 20.0]
        if high_missing_cols:
            recommendations.append(
                Recommendation(
                    category="Completeness",
                    issue=f"Columns with >20% missing values: {', '.join(high_missing_cols)}",
                    suggested_action="Review data capture pipeline for missing attributes or evaluate imputation strategies",
                )
            )

        leading_zero_cols = [col for col, inf in inferred_types.items() if inf.has_leading_zeros]
        if leading_zero_cols:
            recommendations.append(
                Recommendation(
                    category="Type Safety",
                    issue=f"Columns with numeric text containing leading zeros: {', '.join(leading_zero_cols)}",
                    suggested_action="Ensure schema explicitly defines these as string/varchar to prevent numeric truncation",
                )
            )

        if sniff_result.ragged_row_count > 0:
            recommendations.append(
                Recommendation(
                    category="Ingestion Integrity",
                    issue=f"Ragged rows observed ({sniff_result.ragged_row_count} sample lines)",
                    suggested_action="Check upstream CSV export quotation escaping or field separators",
                )
            )

        # Count configured-rule violations only. Counting every high issue made Titanic
        # (no rule broken, one column 77% empty) report "1 high-severity validation failure".
        total_violations = sum(rule_violations.values())
        if total_violations:
            recommendations.append(
                Recommendation(
                    category="Schema Validation",
                    issue=(
                        f"{total_violations} rule violation(s) across "
                        f"{len(rule_violations)} rule(s)"
                    ),
                    suggested_action="Quarantine defective records or patch pipeline transformations",
                )
            )

        return recommendations
