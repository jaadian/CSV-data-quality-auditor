import json
import math
from typing import Any

from csv_auditor.models import AuditResult


def _sanitize_for_json(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {
            str(k): _sanitize_for_json(v) for k, v in sorted(obj.items(), key=lambda x: str(x[0]))
        }
    if isinstance(obj, list):
        return [_sanitize_for_json(x) for x in obj]
    return obj


def generate_json_report(audit_result: AuditResult, indent: int = 2) -> str:
    raw_dict = audit_result.model_dump()
    sanitized = _sanitize_for_json(raw_dict)
    return json.dumps(sanitized, indent=indent, sort_keys=True, allow_nan=False)
