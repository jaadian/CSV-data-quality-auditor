from pathlib import Path

from csv_auditor.config import AuditorConfig, ColumnRule
from csv_auditor.core.auditor import CsvAuditor


def test_full_pipeline_audit(tmp_path: Path):
    csv_file = tmp_path / "orders.csv"
    csv_file.write_text(
        "order_id,quantity,customer_email,price\n"
        "ORD-001,5,cust1@example.com,29.99\n"
        "ORD-002,1,cust2@example.com,9.50\n"
        "ORD-003,NULL,invalid-email,0.00\n"
        "ORD-001,5,cust1@example.com,29.99\n",
        encoding="utf-8",
    )

    config = AuditorConfig(
        columns={
            "order_id": ColumnRule(type="string", required=True, unique=True),
            "quantity": ColumnRule(type="integer", min=1),
            "customer_email": ColumnRule(type="string", format="email"),
            "price": ColumnRule(type="float", min=0.01),
        },
        mask_columns=["customer_email"],
    )

    auditor = CsvAuditor(config=config)
    result = auditor.audit(csv_file)

    assert result.metadata.total_rows == 4
    assert result.metadata.total_columns == 4
    assert result.duplicates.exact_duplicate_rows == 1
    assert result.duplicates.key_duplicates["order_id"] == 1
    assert result.missing["quantity"].missing_count == 1
    assert result.score.overall < 90.0
    assert len(result.issues) > 0
    assert len(result.recommendations) > 0


def test_pipeline_determinism(tmp_path: Path):
    csv_file = tmp_path / "det.csv"
    csv_file.write_text("a,b\n1,x\n2,y\n1,x\n", encoding="utf-8")

    auditor = CsvAuditor()
    res1 = auditor.audit(csv_file)
    res2 = auditor.audit(csv_file)

    assert res1.score.overall == res2.score.overall
    assert res1.score.completeness == res2.score.completeness
    assert res1.score.uniqueness == res2.score.uniqueness
    assert res1.duplicates.exact_duplicate_rows == res2.duplicates.exact_duplicate_rows
    assert len(res1.issues) == len(res2.issues)
