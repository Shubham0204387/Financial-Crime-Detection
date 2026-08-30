"""Evaluation: compare detection model output against labeled ground truth.

Not implemented yet. Function signatures and docstrings only.
"""

import pandas as pd


def load_ground_truth(path: str) -> pd.DataFrame:
    """Load labeled cases (known true positives/negatives) for evaluation.

    Args:
        path: Path to a CSV/JSON file with columns such as case_id and
            is_suspicious (bool).

    Returns:
        A DataFrame of labeled cases.
    """
    raise NotImplementedError


def compute_precision_recall_f1(
    predictions: pd.DataFrame, ground_truth: pd.DataFrame
) -> dict[str, float]:
    """Compute precision, recall, and f1 for a set of predictions.

    Args:
        predictions: DataFrame with columns case_id and predicted_suspicious
            (bool), as produced by the detection pipeline.
        ground_truth: DataFrame as returned by load_ground_truth.

    Returns:
        A dict with keys "precision", "recall", "f1", matching the
        MetricSet shape documented in docs/api-contract.md under GET /metrics.
    """
    raise NotImplementedError


def compare_to_baseline(
    baseline_predictions: pd.DataFrame,
    candidate_predictions: pd.DataFrame,
    ground_truth: pd.DataFrame,
) -> dict[str, dict[str, float]]:
    """Compute metrics for a naive baseline and a candidate model side by side.

    Args:
        baseline_predictions: Predictions from a simple rule-based baseline.
        candidate_predictions: Predictions from the candidate detection model.
        ground_truth: DataFrame as returned by load_ground_truth.

    Returns:
        A dict with keys "baseline" and "candidate", each a MetricSet dict,
        matching the response shape documented in docs/api-contract.md
        under GET /metrics.
    """
    raise NotImplementedError
