import codecs
import csv
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path

import charset_normalizer

from csv_auditor.exceptions import EncodingError, InputFileError


@dataclass
class SniffResult:
    encoding: str
    delimiter: str
    has_header: bool
    headers: list[str]
    warnings: list[str] = field(default_factory=list)
    sample_rows: list[list[str]] = field(default_factory=list)
    ragged_row_count: int = 0
    ragged_row_examples: list[dict[str, int]] = field(default_factory=list)
    file_size_bytes: int = 0


def detect_encoding(file_path: Path, sample_bytes: bytes, user_encoding: str | None = None) -> str:
    if user_encoding:
        try:
            codecs.lookup(user_encoding)
        except LookupError as exc:
            raise EncodingError(f"Unknown encoding '{user_encoding}': {exc}") from exc
        # Decode through the text stream below: a fixed byte sample may end
        # halfway through an otherwise valid multibyte character.
        return user_encoding

    if sample_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if sample_bytes.startswith(b"\xff\xfe"):
        return "utf-16"
    if sample_bytes.startswith(b"\xfe\xff"):
        return "utf-16"

    if sample_bytes.count(b"\x00") > 0:
        for enc in ("utf-16-le", "utf-16-be", "utf-16"):
            try:
                sample_bytes.decode(enc)
                return enc
            except UnicodeDecodeError:
                pass

    try:
        sample_bytes.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError as exc:
        # A fixed byte sample can end in the middle of a valid UTF-8 character.
        if file_path.stat().st_size > len(sample_bytes) and exc.start >= len(sample_bytes) - 4:
            sample_bytes[:-4].decode("utf-8")
            return "utf-8"

    match = charset_normalizer.from_bytes(sample_bytes).best()
    if match and match.encoding:
        return match.encoding

    try:
        sample_bytes.decode("windows-1252")
        return "windows-1252"
    except UnicodeDecodeError as exc:
        raise EncodingError(
            f"Unable to safely determine encoding for {file_path}. Please provide --encoding: {exc}"
        ) from exc


def sniff_csv(
    file_path: str | Path,
    user_encoding: str | None = None,
    user_delimiter: str | None = None,
    has_header: bool | None = None,
    custom_columns: list[str] | None = None,
    max_size_mb: float | None = None,
) -> SniffResult:
    path = Path(file_path)
    if not path.exists():
        raise InputFileError(f"Input file not found: {path}")
    if not path.is_file():
        raise InputFileError(f"Target path is not a regular file: {path}")

    file_size = path.stat().st_size
    if file_size == 0:
        raise InputFileError(f"Input file is empty (0 bytes): {path}")

    if max_size_mb is not None:
        max_bytes = int(max_size_mb * 1024 * 1024)
        if file_size > max_bytes:
            raise InputFileError(
                f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds allowed limit of {max_size_mb} MB"
            )

    read_sample_size = min(file_size, 256 * 1024)
    with open(path, "rb") as raw_f:
        sample_bytes = raw_f.read(read_sample_size)

    encoding = detect_encoding(path, sample_bytes, user_encoding)

    try:
        # Text-mode reading avoids cutting a multibyte character at the byte sample boundary.
        with path.open("r", encoding=encoding, newline="") as sample_file:
            decoded_sample = sample_file.read(256 * 1024)
    except (UnicodeError, LookupError) as exc:
        raise EncodingError(f"Failed to decode {path} using encoding '{encoding}': {exc}") from exc

    warnings: list[str] = []
    delimiter = user_delimiter

    if not delimiter:
        sniffer = csv.Sniffer()
        try:
            sample_for_sniff = "\n".join(decoded_sample.splitlines()[:25])
            dialect = sniffer.sniff(sample_for_sniff, delimiters=";,|\t")
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ","
            warnings.append("Delimiter detection was inconclusive; defaulted to comma (',')")

    if len(delimiter) != 1 or delimiter in ("\r", "\n", '"'):
        raise InputFileError("CSV delimiter must be one non-newline, non-quote character")
    if delimiter not in [",", ";", "\t", "|"]:
        warnings.append(f"Using non-standard delimiter '{delimiter}'")

    sample_lines = decoded_sample.splitlines()
    if not sample_lines:
        return SniffResult(
            encoding=encoding,
            delimiter=delimiter,
            has_header=False,
            headers=[],
            warnings=warnings,
            file_size_bytes=file_size,
        )

    parsed_rows: list[list[str]] = []
    try:
        with path.open("r", encoding=encoding, newline="") as sample_file:
            reader = csv.reader(sample_file, delimiter=delimiter, strict=True)
            for row in islice(reader, 101):
                if row:
                    parsed_rows.append(row)
    except (csv.Error, UnicodeError, OSError) as exc:
        raise InputFileError(f"Cannot parse CSV sample: {exc}") from exc

    if not parsed_rows:
        return SniffResult(
            encoding=encoding,
            delimiter=delimiter,
            has_header=False,
            headers=[],
            warnings=warnings,
            file_size_bytes=file_size,
        )

    if custom_columns:
        headers = custom_columns
        inferred_has_header = False
    elif has_header is False:
        headers = [f"col_{i}" for i in range(len(parsed_rows[0]))]
        inferred_has_header = False
    else:
        inferred_has_header = True
        headers = parsed_rows[0]

    # pandas `to_csv()` with its default index writes a blank first header. Aborting on
    # that is unhelpful, so blank names get a positional name and a visible warning.
    # Duplicate names are still rejected later: there is no safe way to guess intent.
    headers = list(headers)
    renamed: list[str] = []
    taken = {h.strip() for h in headers}
    for idx, header in enumerate(headers):
        if header.strip():
            continue
        candidate = f"unnamed_{idx}"
        while candidate in taken:
            candidate += "_"
        taken.add(candidate)
        headers[idx] = candidate
        renamed.append(candidate)
    if renamed:
        warnings.append(f"Renamed blank column header(s): {', '.join(renamed)}")

    seen_headers: set[str] = set()
    duplicate_headers: list[str] = []
    empty_header_count = 0
    for _idx, header in enumerate(headers):
        stripped = header.strip()
        if not stripped:
            empty_header_count += 1
        if stripped in seen_headers:
            duplicate_headers.append(stripped)
        seen_headers.add(stripped)

    if duplicate_headers:
        warnings.append(
            f"Duplicate column headers detected: {', '.join(sorted(set(duplicate_headers)))}"
        )
    if empty_header_count > 0:
        warnings.append(f"Detected {empty_header_count} empty column header name(s)")

    expected_cols = len(headers)
    ragged_count = 0
    ragged_examples: list[dict[str, int]] = []
    data_sample_rows = parsed_rows[1:] if inferred_has_header else parsed_rows

    for row_idx, row in enumerate(data_sample_rows, start=2 if inferred_has_header else 1):
        if len(row) != expected_cols:
            ragged_count += 1
            if len(ragged_examples) < 5:
                ragged_examples.append(
                    {"line": row_idx, "expected": expected_cols, "actual": len(row)}
                )

    if ragged_count > 0:
        warnings.append(
            f"Ragged row widths observed in sample: {ragged_count} line(s) did not match header width ({expected_cols})"
        )

    return SniffResult(
        encoding=encoding,
        delimiter=delimiter,
        has_header=inferred_has_header,
        headers=headers,
        warnings=warnings,
        sample_rows=data_sample_rows[:10],
        ragged_row_count=ragged_count,
        ragged_row_examples=ragged_examples,
        file_size_bytes=file_size,
    )
