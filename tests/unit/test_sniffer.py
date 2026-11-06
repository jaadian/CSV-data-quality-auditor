from pathlib import Path

import pytest

from csv_auditor.exceptions import InputFileError
from csv_auditor.ingestion.sniffer import sniff_csv


def test_empty_file_raises_input_file_error(tmp_path: Path):
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")
    with pytest.raises(InputFileError) as exc_info:
        sniff_csv(empty_csv)
    assert exc_info.value.exit_code == 3


def test_missing_file_raises_input_file_error(tmp_path: Path):
    non_existent = tmp_path / "non_existent.csv"
    with pytest.raises(InputFileError):
        sniff_csv(non_existent)


def test_sniff_utf8_sig_bom(tmp_path: Path):
    bom_file = tmp_path / "bom.csv"
    bom_file.write_bytes(b"\xef\xbb\xbfcol1,col2\nval1,val2\n")
    res = sniff_csv(bom_file)
    assert res.encoding == "utf-8-sig"
    assert res.delimiter == ","
    assert res.headers == ["col1", "col2"]


def test_sniff_utf16_le(tmp_path: Path):
    utf16_file = tmp_path / "utf16.csv"
    content = "col1,col2\nval1,val2\n"
    utf16_file.write_bytes(content.encode("utf-16"))
    res = sniff_csv(utf16_file)
    assert "utf-16" in res.encoding.lower()


def test_sniff_semicolon_and_tab(tmp_path: Path):
    semi_file = tmp_path / "semi.csv"
    semi_file.write_text("a;b;c\n1;2;3\n4;5;6\n", encoding="utf-8")
    res_semi = sniff_csv(semi_file)
    assert res_semi.delimiter == ";"

    tab_file = tmp_path / "tab.tsv"
    tab_file.write_text("x\ty\tz\n10\t20\t30\n", encoding="utf-8")
    res_tab = sniff_csv(tab_file)
    assert res_tab.delimiter == "\t"


def test_sniff_duplicate_headers(tmp_path: Path):
    dup_file = tmp_path / "dup_headers.csv"
    dup_file.write_text("id,name,id\n1,Alice,101\n", encoding="utf-8")
    res = sniff_csv(dup_file)
    assert any("Duplicate column headers" in w for w in res.warnings)


def test_sniff_header_only_file(tmp_path: Path):
    header_file = tmp_path / "header_only.csv"
    header_file.write_text("col1,col2,col3\n", encoding="utf-8")
    res = sniff_csv(header_file)
    assert res.has_header is True
    assert res.headers == ["col1", "col2", "col3"]
    assert len(res.sample_rows) == 0


def test_sniff_ragged_rows(tmp_path: Path):
    ragged_file = tmp_path / "ragged.csv"
    ragged_file.write_text("a,b,c\n1,2,3\n4,5\n6,7,8,9\n", encoding="utf-8")
    res = sniff_csv(ragged_file)
    assert res.ragged_row_count > 0
    assert any("Ragged row widths" in w for w in res.warnings)
