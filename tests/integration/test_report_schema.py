import json
from pathlib import Path

import jsonschema

from csv_auditor.core.auditor import CsvAuditor
from csv_auditor.reporting.json_report import generate_json_report


def test_json_report_conforms_to_schema(tmp_path: Path):
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("col_a,col_b\n1,alpha\n2,beta\n", encoding="utf-8")

    auditor = CsvAuditor()
    result = auditor.audit(csv_file)
    json_str = generate_json_report(result)
    data = json.loads(json_str)

    schema_path = Path(__file__).parent.parent.parent / "docs" / "report_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    jsonschema.validate(instance=data, schema=schema)
