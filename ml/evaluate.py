"""Evaluation: compare detection model output against labeled ground truth.

compare_to_baseline and load_ground_truth (CSV/JSON case-level ground
truth for the eventual API /metrics endpoint) are not implemented yet --
signatures and docstrings only. compute_metrics and evaluate_on_split are
transaction-level and fully implemented: they're what the __main__ block
below uses to score the naive baseline against the patterns-derived
labels from labels.py.
"""

import logging
import time
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def load_ground_truth(path: str) -> pd.DataFrame:
    """Load labeled cases (known true positives/negatives) for evaluation.

    Args:
        path: Path to a CSV/JSON file with columns such as case_id and
            is_suspicious (bool).

    Returns:
        A DataFrame of labeled cases.
    """
    raise NotImplementedError


def _pr_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Area under the precision-recall curve, via trapezoidal integration.

    Implemented by hand (rather than sklearn.metrics.average_precision_score)
    to avoid adding a new dependency for one metric; scikit-learn isn't
    otherwise used anywhere in this pipeline.
    """
    order = np.argsort(-scores, kind="mergesort")
    y_sorted = y_true[order]

    tp_cumsum = np.cumsum(y_sorted)
    fp_cumsum = np.cumsum(~y_sorted)
    total_positives = y_true.sum()

    if total_positives == 0:
        return float("nan")

    precision = tp_cumsum / (tp_cumsum + fp_cumsum)
    recall = tp_cumsum / total_positives

    # Prepend the (recall=0, precision=1) point, standard for PR-AUC.
    precision = np.concatenate(([1.0], precision))
    recall = np.concatenate(([0.0], recall))

    return float(np.trapz(precision, recall))


def compute_metrics(y_true, y_pred) -> dict[str, float]:
    """Compute precision, recall, f1 (and PR-AUC, if scores are given).

    Accuracy is deliberately not included: with a heavily imbalanced
    positive class, a detector that flags nothing scores high accuracy
    while catching zero laundering, so it would misrepresent detection
    quality as a headline number. It's logged as a side note instead.

    Args:
        y_true: Boolean (or 0/1) ground-truth labels.
        y_pred: Either boolean/0-1 hard predictions, or continuous risk
            scores. Hard predictions are used as-is. Continuous scores
            are thresholded at 0.5 for precision/recall/f1 and also used
            to compute PR-AUC, which a fixed hard prediction can't provide.

    Returns:
        A dict with keys "precision", "recall", "f1", and "pr_auc" (only
        present when y_pred was continuous scores rather than hard labels).
    """
    y_true_arr = np.asarray(y_true).astype(bool)
    y_pred_arr = np.asarray(y_pred)

    is_hard_labels = y_pred_arr.dtype == bool or set(np.unique(y_pred_arr)).issubset({0, 1})
    hard_pred = y_pred_arr.astype(bool) if is_hard_labels else (y_pred_arr >= 0.5)

    tp = int(np.sum(y_true_arr & hard_pred))
    fp = int(np.sum(~y_true_arr & hard_pred))
    fn = int(np.sum(y_true_arr & ~hard_pred))
    tn = int(np.sum(~y_true_arr & ~hard_pred))

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    metrics: dict[str, float] = {"precision": precision, "recall": recall, "f1": f1}

    if not is_hard_labels:
        metrics["pr_auc"] = _pr_auc(y_true_arr, y_pred_arr.astype(float))

    n = len(y_true_arr)
    if n:
        accuracy = (tp + tn) / n
        positive_rate = y_true_arr.mean()
        logger.info(
            "accuracy=%.4f (not reported as a metric: positive class is %.4f%% of this data, "
            "so a detector that flags nothing would already score %.4f%% accuracy)",
            accuracy, 100 * positive_rate, 100 * (1 - positive_rate),
        )

    return metrics


def evaluate_on_split(
    split_df: pd.DataFrame,
    ground_truth_df: pd.DataFrame,
    detector_fn: Callable[[pd.DataFrame], "pd.Series | np.ndarray"],
) -> dict:
    """Run a detector on a split and score it against ground truth.

    split_df and ground_truth_df must be row-aligned (same length, same
    row order) -- the intended usage is a features-only view and a
    labels-only view sliced from the same labeled DataFrame (e.g. one of
    the splits from preprocessing.time_based_split, run on the output of
    labels.build_ground_truth), so the detector never sees the label
    columns it's being scored against.

    Args:
        split_df: The transaction rows to run detection on. Passed
            directly to detector_fn.
        ground_truth_df: Row-aligned labels for split_df, with
            "is_laundering" (bool) and "pattern_type" (nullable) columns,
            as produced by labels.build_ground_truth.
        detector_fn: A callable taking split_df and returning a boolean
            or float array/Series aligned to split_df's row order (e.g.
            detection.baseline_naive_threshold with graph/threshold
            already bound via a lambda or functools.partial).

    Returns:
        The dict from compute_metrics, plus a "per_pattern_type_recall"
        key: a dict mapping each pattern_type seen in ground_truth_df to
        the detector's recall restricted to that type's transactions.
    """
    if len(split_df) != len(ground_truth_df):
        raise ValueError(
            f"split_df ({len(split_df)} rows) and ground_truth_df ({len(ground_truth_df)} rows) "
            "are not row-aligned"
        )

    y_pred = pd.Series(detector_fn(split_df)).reset_index(drop=True)
    y_true = ground_truth_df["is_laundering"].reset_index(drop=True)
    pattern_type = ground_truth_df["pattern_type"].reset_index(drop=True)

    metrics = compute_metrics(y_true, y_pred)

    hard_pred = y_pred.astype(bool)
    per_pattern_type_recall = {}
    for ptype in sorted(pattern_type.dropna().unique()):
        mask = pattern_type == ptype
        type_true = y_true[mask]
        type_pred = hard_pred[mask]
        per_pattern_type_recall[ptype] = (
            float((type_true & type_pred).sum() / len(type_true)) if len(type_true) else float("nan")
        )

    metrics["per_pattern_type_recall"] = per_pattern_type_recall
    return metrics


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


if __name__ == "__main__":
    from ml.detection import (
        baseline_naive_threshold,
        combined_structural_detector,
        compute_percentile_threshold,
        detect_cycles,
    )
    from ml.labels import build_ground_truth
    from ml.preprocessing import load_cached_graph, load_patterns, load_transactions, time_based_split

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_dir = Path(__file__).resolve().parent / "data"
    trans_path = data_dir / "HI-Small_Trans.csv"
    patterns_path = data_dir / "HI-Small_Patterns.txt"
    cache_path = data_dir / "processed" / "graph.pkl"

    transactions = load_transactions(str(trans_path))
    patterns = load_patterns(str(patterns_path))
    graph = load_cached_graph(str(cache_path))

    labeled = build_ground_truth(patterns, transactions)
    train_df, val_df, test_df = time_based_split(labeled)

    # Fit the threshold on train only -- computing it from val/test would
    # leak evaluation-set information into the "learned" parameter.
    threshold = compute_percentile_threshold(train_df)

    label_cols = ["is_laundering", "pattern_type"]
    test_features = test_df.drop(columns=label_cols)
    test_labels = test_df[label_cols]

    detectors = {
        "naive baseline (p99 amount)": lambda df: baseline_naive_threshold(
            df, graph=graph, threshold_amount=threshold
        ),
        "cycle-only": lambda df: detect_cycles(df, graph),
        "combined (cycle + fan-in/out)": lambda df: combined_structural_detector(df, graph),
    }

    results = {}
    for name, detector in detectors.items():
        run_start = time.monotonic()
        results[name] = evaluate_on_split(test_features, test_labels, detector)
        results[name]["_runtime_s"] = time.monotonic() - run_start

    print(f"\n=== Detector comparison -- test split ({len(test_df):,} transactions) ===")
    for name, metrics in results.items():
        print(f"\n--- {name} ---")
        print(f"runtime:   {metrics['_runtime_s']:.2f}s")
        print(f"precision: {metrics['precision']:.4f}")
        print(f"recall:    {metrics['recall']:.4f}")
        print(f"f1:        {metrics['f1']:.4f}")
        print("per-pattern-type recall (fraction of that type's transactions flagged):")
        for ptype, recall in sorted(metrics["per_pattern_type_recall"].items()):
            print(f"  {ptype:<16} {recall:.4f}")
