import pytest

from csv_auditor.config import ScoreWeights
from csv_auditor.models import ColumnMissingStats, InferredColumnType, Severity
from csv_auditor.scoring.quality_score import QualityScoreCalculator


def test_invalid_weights_sum_raises_validation_error():
    with pytest.raises(ValueError):
        ScoreWeights(completeness=0.5, uniqueness=0.5, validity=0.5, consistency=0.0)


def test_score_calculation_with_and_without_rules():
    calc = QualityScoreCalculator()

    missing_stats = {
        "col1": ColumnMissingStats(
            column="col1",
            missing_count=0,
            total_count=100,
            missing_percentage=0.0,
            severity=Severity.LOW,
        )
    }
    inferred_types = {
        "col1": InferredColumnType(
            suggested_type="integer",
            confidence=1.0,
            dominant_type_share=1.0,
        )
    }

    score_no_rules = calc.calculate(
        missing_stats=missing_stats,
        total_rows=100,
        duplicate_rows=0,
        inferred_types=inferred_types,
        has_rules=False,
    )
    assert score_no_rules.overall == 100.0
    assert score_no_rules.validity is None
    assert "validity" not in score_no_rules.dimensions_used
    assert score_no_rules.rating == "Excellent"

    score_with_rules = calc.calculate(
        missing_stats=missing_stats,
        total_rows=100,
        duplicate_rows=0,
        inferred_types=inferred_types,
        rows_with_rule_violations=10,
        has_rules=True,
    )
    assert score_with_rules.validity == 90.0
    assert "validity" in score_with_rules.dimensions_used
    assert score_with_rules.overall == 97.0
