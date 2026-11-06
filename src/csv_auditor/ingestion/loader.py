"""Streaming CSV reader with strict row-width validation.

Using csv.reader rather than pandas.read_csv prevents short rows from being
silently padded and lets us keep precise control over malformed records.
"""

import csv
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from csv_auditor.exceptions import InputFileError
from csv_auditor.ingestion.sniffer import SniffResult


def iter_chunks(
    file_path: str | Path,
    sniff_result: SniffResult,
    chunk_size: int = 50_000,
    on_bad_rows: str = "error",
) -> Iterator[pd.DataFrame]:
    path = Path(file_path)
    if not path.is_file():
        raise InputFileError(f"File not found: {path}")
    if on_bad_rows not in ("error", "skip"):
        raise InputFileError("--on-bad-rows must be 'error' or 'skip'")
    if chunk_size < 1:
        raise InputFileError("chunk_size must be at least 1")

    headers = sniff_result.headers
    expected = len(headers)
    rows: list[list[str]] = []
    try:
        with path.open("r", encoding=sniff_result.encoding, newline="") as stream:
            reader = csv.reader(stream, delimiter=sniff_result.delimiter, strict=True)
            if sniff_result.has_header:
                next(reader, None)
            for row in reader:
                if not row:  # Ignore truly blank physical records, not empty cells.
                    continue
                if len(row) != expected:
                    if on_bad_rows == "error":
                        raise InputFileError(
                            f"Malformed CSV record near physical line {reader.line_num}: "
                            f"expected {expected} fields, found {len(row)}"
                        )
                    continue
                rows.append(row)
                if len(rows) >= chunk_size:
                    yield pd.DataFrame(rows, columns=headers, dtype=str)
                    rows = []
            if rows:
                yield pd.DataFrame(rows, columns=headers, dtype=str)
    except (csv.Error, UnicodeError, OSError) as exc:
        raise InputFileError(f"CSV parsing failed: {exc}") from exc
