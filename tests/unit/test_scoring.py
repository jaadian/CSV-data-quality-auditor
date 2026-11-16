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


def test_floor2_absorbs_float_noise_but_still_floors_real_defects():
    from csv_auditor.scoring.quality_score import _floor2

    # Float noise from summing weights must not cost a clean dataset its 100.
    assert _floor2(99.99999999999999) == 100.0
    assert _floor2(56.99999999999999) == 57.0
    # A real defect, however small, still rounds down (3 bad rows in 23,412).
    assert _floor2(99.996) == 99.99
    assert _floor2(100.0 * (1 - 3 / 23412)) == 99.98


@pytest.mark.parametrize(
    "weights",
    [
        ScoreWeights(),
        ScoreWeights(completeness=0.1, uniqueness=0.2, validity=0.3, consistency=0.4),
        ScoreWeights(completeness=0.7, uniqueness=0.1, validity=0.1, consistency=0.1),
    ],
)
def test_perfect_dataset_scores_exactly_100_regardless_of_weights(weights):
    """Regression: on Python 3.11 renormalised weights summed to 0.9999... -> 99.99."""
    stats = {
        "c": ColumnMissingStats(
            column="c",
            missing_count=0,
            total_count=10,
            missing_percentage=0.0,
            severity=Severity.LOW,
        )
    }
    types = {
        "c": InferredColumnType(suggested_type="integer", confidence=1.0, dominant_type_share=1.0)
    }
    calc = QualityScoreCalculator(weights)
    for has_rules, violations in ((False, None), (True, 0)):
        score = calc.calculate(
            missing_stats=stats,
            total_rows=10,
            duplicate_rows=0,
            inferred_types=types,
            rows_with_rule_violations=violations,
            has_rules=has_rules,
        )
        assert score.overall == 100.0
