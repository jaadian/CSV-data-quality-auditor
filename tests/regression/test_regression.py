from pathlib import Path

from csv_auditor.config import AuditorConfig
from csv_auditor.core.auditor import CsvAuditor
from csv_auditor.reporting.html_report import render_html_report
from csv_auditor.reporting.json_report import generate_json_report


def test_chunk_boundary_duplicates_caught(tmp_path: Path):
    csv_file = tmp_path / "chunk_dup.csv"
    rows = [
        "id,val",
        "1,alpha",
        "2,beta",
        "3,gamma",
        "4,delta",
        "5,epsilon",
        "6,zeta",
        "7,eta",
        "8,theta",
        "9,iota",
        "10,kappa",
        "11,lambda",
        "12,mu",
        "1,alpha",
    ]
    csv_file.write_text("\n".join(rows) + "\n", encoding="utf-8")

    config = AuditorConfig(chunk_size=3)
    auditor = CsvAuditor(config=config)
    result = auditor.audit(csv_file)

    assert result.metadata.total_rows == 13
    assert result.duplicates.exact_duplicate_rows == 1
    assert result.duplicates.unique_rows == 12


def test_leading_zero_not_converted_to_numeric(tmp_path: Path):
    csv_file = tmp_path / "ids.csv"
    csv_file.write_text("account_id,balance\n000123,500\n000456,1200\n", encoding="utf-8")

    auditor = CsvAuditor()
    result = auditor.audit(csv_file)

    assert result.types["account_id"].suggested_type == "string"
    assert result.types["account_id"].has_leading_zeros is True


def test_xss_and_formula_injection_escaped(tmp_path: Path):
    csv_file = tmp_path / "security.csv"
    csv_file.write_text(
        "code,payload\n1,<script>alert(1)</script>\n2,=cmd|' /C calc'!A0\n", encoding="utf-8"
    )

    auditor = CsvAuditor()
    result = auditor.audit(csv_file)

    html_out = render_html_report(result)
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out

    json_out = generate_json_report(result)
    assert "<script>alert(1)</script>" in json_out
