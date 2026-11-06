import re
from datetime import datetime
from typing import Any

import pandas as pd

from csv_auditor.checks.missing import is_missing_value
from csv_auditor.config import AuditorConfig, ColumnRule, CrossColumnRule
from csv_auditor.models import Issue

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
INT_REGEX = re.compile(r"^[-+]?\d+$")
FLOAT_REGEX = re.compile(r"^[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?$")
OP_REGEX = re.compile(r"^(.*?)\s*(>=|<=|!=|==|>|<)\s*(.*?)$")


class RuleEngine:
    def __init__(self, config: AuditorConfig) -> None:
        self.config = config
        self.mask_columns = set(config.mask_columns)
        self.max_examples = config.max_examples
        self.missing_markers = {marker.casefold() for marker in config.missing_markers}

        self.violation_counts: dict[str, int] = {}
        self.violation_examples: dict[str, list[Issue]] = {}
        self.rows_with_violations_count = 0
        self.total_rows = 0

    def _mask_value(self, column: str, value: str) -> str:
        if column in self.mask_columns:
            return "***"
        return value

    def _is_missing(self, val: str) -> bool:
        return is_missing_value(val, self.missing_markers, self.config.whitespace_as_missing)

    def _check_column_rule(
        self,
        col: str,
        val: str,
        rule: ColumnRule,
        row_idx: int,
    ) -> Issue | None:
        if self._is_missing(val):
            return None

        val_stripped = val.strip()

        if rule.type == "integer":
            if not INT_REGEX.match(val_stripped):
                return Issue(
                    rule_name=f"{col}_type_integer",
                    column=col,
                    row_index=row_idx,
                    message=f"Value '{self._mask_value(col, val_stripped)}' is not a valid integer",
                    severity=rule.severity,
                    sample_value=self._mask_value(col, val_stripped),
                )
        elif rule.type == "float":
            if not FLOAT_REGEX.match(val_stripped):
                return Issue(
                    rule_name=f"{col}_type_float",
                    column=col,
                    row_index=row_idx,
                    message=f"Value '{self._mask_value(col, val_stripped)}' is not a valid float",
                    severity=rule.severity,
                    sample_value=self._mask_value(col, val_stripped),
                )
        elif rule.type == "boolean":
            if val_stripped.lower() not in {"true", "false", "yes", "no", "1", "0", "t", "f"}:
                return Issue(
                    rule_name=f"{col}_type_boolean",
                    column=col,
                    row_index=row_idx,
                    message=f"Value '{self._mask_value(col, val_stripped)}' is not a recognized boolean",
                    severity=rule.severity,
                    sample_value=self._mask_value(col, val_stripped),
                )
        elif rule.type == "date" and rule.format:
            try:
                datetime.strptime(val_stripped, rule.format)
            except ValueError:
                return Issue(
                    rule_name=f"{col}_date_format",
                    column=col,
                    row_index=row_idx,
                    message=f"Date '{self._mask_value(col, val_stripped)}' does not match format '{rule.format}'",
                    severity=rule.severity,
                    sample_value=self._mask_value(col, val_stripped),
                )

        if rule.format == "email":
            if not EMAIL_REGEX.match(val_stripped):
                return Issue(
                    rule_name=f"{col}_email_format",
                    column=col,
                    row_index=row_idx,
                    message=f"Value '{self._mask_value(col, val_stripped)}' is not a valid email address",
                    severity=rule.severity,
                    sample_value=self._mask_value(col, val_stripped),
                )

        if rule.regex:
            if not re.search(rule.regex, val):
                return Issue(
                    rule_name=f"{col}_regex_match",
                    column=col,
                    row_index=row_idx,
                    message=f"Value '{self._mask_value(col, val)}' did not match pattern '{rule.regex}'",
                    severity=rule.severity,
                    sample_value=self._mask_value(col, val),
                )

        if rule.min is not None or rule.max is not None:
            try:
                num = float(val_stripped)
                if rule.min is not None and num < rule.min:
                    return Issue(
                        rule_name=f"{col}_min_bound",
                        column=col,
                        row_index=row_idx,
                        message=f"Value {self._mask_value(col, val_stripped)} is less than configured minimum {rule.min}",
                        severity=rule.severity,
                        sample_value=self._mask_value(col, val_stripped),
                    )
                if rule.max is not None and num > rule.max:
                    return Issue(
                        rule_name=f"{col}_max_bound",
                        column=col,
                        row_index=row_idx,
                        message=f"Value {self._mask_value(col, val_stripped)} is greater than configured maximum {rule.max}",
                        severity=rule.severity,
                        sample_value=self._mask_value(col, val_stripped),
                    )
            except ValueError:
                pass

        if rule.min_length is not None and len(val) < rule.min_length:
            return Issue(
                rule_name=f"{col}_min_length",
                column=col,
                row_index=row_idx,
                message=f"Length {len(val)} is shorter than minimum length {rule.min_length}",
                severity=rule.severity,
                sample_value=self._mask_value(col, val),
            )

        if rule.max_length is not None and len(val) > rule.max_length:
            return Issue(
                rule_name=f"{col}_max_length",
                column=col,
                row_index=row_idx,
                message=f"Length {len(val)} exceeds maximum length {rule.max_length}",
                severity=rule.severity,
                sample_value=self._mask_value(col, val),
            )

        if rule.allowed is not None:
            allowed_strings = {str(a) for a in rule.allowed}
            if val_stripped not in allowed_strings:
                return Issue(
                    rule_name=f"{col}_allowed_values",
                    column=col,
                    row_index=row_idx,
                    message=f"Value '{self._mask_value(col, val_stripped)}' is not in allowed set {rule.allowed}",
                    severity=rule.severity,
                    sample_value=self._mask_value(col, val_stripped),
                )

        return None

    def _evaluate_cross_column(
        self,
        rule_spec: CrossColumnRule,
        row_dict: dict[str, Any],
        row_idx: int,
    ) -> Issue | None:
        match = OP_REGEX.match(rule_spec.rule)
        if not match:
            return None

        left_expr, op, right_expr = match.groups()
        left_col = left_expr.strip()
        right_col = right_expr.strip()

        if left_col not in row_dict or right_col not in row_dict:
            return None

        val_left = str(row_dict[left_col])
        val_right = str(row_dict[right_col])

        if self._is_missing(val_left) or self._is_missing(val_right):
            return None

        val_left_parsed: Any
        val_right_parsed: Any
        try:
            val_left_parsed = float(val_left)
            val_right_parsed = float(val_right)
        except ValueError:
            try:
                val_left_parsed = datetime.fromisoformat(val_left.strip())
                val_right_parsed = datetime.fromisoformat(val_right.strip())
            except ValueError:
                # Falling back to string comparison made "abc" >= "10" pass silently.
                # A value we cannot compare is reported, not guessed.
                return Issue(
                    rule_name=rule_spec.name,
                    row_index=row_idx,
                    message=(
                        f"Cross-column condition '{rule_spec.rule}' could not be evaluated: "
                        f"{left_col}='{self._mask_value(left_col, val_left)}' and "
                        f"{right_col}='{self._mask_value(right_col, val_right)}' are not both "
                        "numbers or ISO dates"
                    ),
                    severity=rule_spec.severity,
                )

        try:
            if op == ">=":
                condition = val_left_parsed >= val_right_parsed
            elif op == "<=":
                condition = val_left_parsed <= val_right_parsed
            elif op == "==":
                condition = val_left_parsed == val_right_parsed
            elif op == "!=":
                condition = val_left_parsed != val_right_parsed
            elif op == ">":
                condition = val_left_parsed > val_right_parsed
            elif op == "<":
                condition = val_left_parsed < val_right_parsed
            else:
                condition = True
        except TypeError:
            condition = False

        if not condition:
            return Issue(
                rule_name=rule_spec.name,
                row_index=row_idx,
                message=f"Cross-column condition '{rule_spec.rule}' failed ({left_col}='{self._mask_value(left_col, val_left)}', {right_col}='{self._mask_value(right_col, val_right)}')",
                severity=rule_spec.severity,
            )
        return None

    def update(self, chunk: pd.DataFrame, start_row_idx: int) -> None:
        chunk_len = len(chunk)
        self.total_rows += chunk_len
        if not self.config.columns and not self.config.cross_column:
            return

        for offset, (_, row) in enumerate(chunk.iterrows()):
            current_row_idx = start_row_idx + offset
            row_has_violation = False
            row_dict: dict[str, Any] = {str(k): v for k, v in row.items()}

            for col_name, rule in self.config.columns.items():
                if col_name in row_dict:
                    val = str(row_dict[col_name])
                    issue = self._check_column_rule(col_name, val, rule, current_row_idx)
                    if issue:
                        row_has_violation = True
                        r_name = issue.rule_name
                        self.violation_counts[r_name] = self.violation_counts.get(r_name, 0) + 1
                        if len(self.violation_examples.setdefault(r_name, [])) < self.max_examples:
                            self.violation_examples[r_name].append(issue)

            for cc_rule in self.config.cross_column:
                cc_issue = self._evaluate_cross_column(cc_rule, row_dict, current_row_idx)
                if cc_issue:
                    row_has_violation = True
                    r_name = cc_issue.rule_name
                    self.violation_counts[r_name] = self.violation_counts.get(r_name, 0) + 1
                    if len(self.violation_examples.setdefault(r_name, [])) < self.max_examples:
                        self.violation_examples[r_name].append(cc_issue)

            if row_has_violation:
                self.rows_with_violations_count += 1

    def finalize(self) -> tuple[list[Issue], dict[str, int], int]:
        all_issues: list[Issue] = []
        for r_name, examples in self.violation_examples.items():
            all_issues.extend(examples)
            excess = self.violation_counts[r_name] - len(examples)
            if excess > 0:
                all_issues.append(
                    Issue(
                        rule_name=r_name,
                        message=f"... and {excess} additional violation(s) for rule '{r_name}'",
                        severity=examples[0].severity,
                    )
                )

        return all_issues, self.violation_counts, self.rows_with_violations_count
