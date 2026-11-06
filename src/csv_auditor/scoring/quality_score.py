import math

from csv_auditor.config import ScoreWeights
from csv_auditor.models import ColumnMissingStats, InferredColumnType, QualityScore


def _floor2(value: float) -> float:
    """Round down to 2 decimals so a dataset with any problem never shows 100.00.

    round() turned 99.996 (3 bad dates in 23,412 rows) into a perfect 100.0.
    """
    return math.floor(value * 100) / 100


class QualityScoreCalculator:
    def __init__(self, weights: ScoreWeights | None = None) -> None:
        self.weights = weights or ScoreWeights()

    def calculate(
        self,
        missing_stats: dict[str, ColumnMissingStats],
        total_rows: int,
        duplicate_rows: int,
        inferred_types: dict[str, InferredColumnType],
        rows_with_rule_violations: int | None = None,
        has_rules: bool = False,
    ) -> QualityScore:
        if total_rows == 0:
            return QualityScore(
                overall=0.0,
                rating="Poor",
                completeness=0.0,
                uniqueness=0.0,
                validity=0.0 if has_rules else None,
                consistency=0.0,
                weights_used={},
                dimensions_used=[],
            )

        total_cols = len(missing_stats)
        total_cells = total_rows * total_cols if total_cols > 0 else 1
        total_missing_cells = sum(s.missing_count for s in missing_stats.values())
        completeness = max(0.0, min(100.0, 100.0 * (1.0 - (total_missing_cells / total_cells))))

        uniqueness = max(0.0, min(100.0, 100.0 * (1.0 - (duplicate_rows / total_rows))))

        if inferred_types:
            shares = [inf.dominant_type_share for inf in inferred_types.values()]
            avg_share = sum(shares) / len(shares)
        else:
            avg_share = 1.0
        consistency = max(0.0, min(100.0, 100.0 * avg_share))

        validity: float | None = None
        if has_rules and rows_with_rule_violations is not None:
            validity = max(
                0.0, min(100.0, 100.0 * (1.0 - (rows_with_rule_violations / total_rows)))
            )

        dim_scores: dict[str, float] = {
            "completeness": completeness,
            "uniqueness": uniqueness,
            "consistency": consistency,
        }
        dim_weights: dict[str, float] = {
            "completeness": self.weights.completeness,
            "uniqueness": self.weights.uniqueness,
            "consistency": self.weights.consistency,
        }

        if validity is not None:
            dim_scores["validity"] = validity
            dim_weights["validity"] = self.weights.validity

        total_weight = sum(dim_weights.values())
        if total_weight > 0:
            renormalized_weights = {k: v / total_weight for k, v in dim_weights.items()}
            overall = sum(dim_scores[k] * renormalized_weights[k] for k in dim_scores)
        else:
            renormalized_weights = {}
            overall = 0.0

        overall = _floor2(max(0.0, min(100.0, overall)))

        if overall >= 90.0:
            rating = "Excellent"
        elif overall >= 75.0:
            rating = "Good"
        elif overall >= 60.0:
            rating = "Needs Improvement"
        else:
            rating = "Poor"

        return QualityScore(
            overall=overall,
            rating=rating,
            completeness=_floor2(completeness),
            uniqueness=_floor2(uniqueness),
            validity=_floor2(validity) if validity is not None else None,
            consistency=_floor2(consistency),
            weights_used={k: round(v, 4) for k, v in renormalized_weights.items()},
            dimensions_used=sorted(dim_scores.keys()),
        )
