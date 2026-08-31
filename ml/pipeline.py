"""End-to-end pipeline entrypoint: raw data -> scored, API-contract-shaped cases + metrics.

A single function, run_full_pipeline(), meant to be called ONCE at
backend startup (see backend/app/main.py's lifespan handler) -- not per
request. It takes tens of seconds (data load + graph build/load +
detection + scoring + evaluation), matching the runtimes already logged
by ml/scoring.py's and ml/evaluate.py's own __main__ blocks.

It wires together every ml/ module already built and validated
independently, without duplicating any of their logic:
    preprocessing.py -> load + validate transactions/patterns, build/cache graph
    labels.py        -> ground truth from parsed patterns
    scoring.py        -> group_into_cases, compute_sub_scores, compute_risk_score,
                         assign_risk_tier, generate_evidence_text, case_to_api_detail
    detection.py      -> the naive baseline and combined structural detector
                         (via evaluate.py), for the /metrics comparison
    evaluate.py        -> compute_metrics / evaluate_on_split, reused as-is
                         for the baseline-vs-candidate numbers GET /metrics needs
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ml.detection import baseline_naive_threshold, combined_structural_detector, compute_percentile_threshold
from ml.evaluate import evaluate_on_split
from ml.labels import build_ground_truth
from ml.preprocessing import (
    build_graph,
    cache_graph,
    load_cached_graph,
    load_patterns,
    load_transactions,
    time_based_split,
)
from ml.scoring import (
    assign_risk_tier,
    case_to_api_detail,
    compute_risk_score,
    compute_sub_scores,
    generate_evidence_text,
    group_into_cases,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
TRANSACTIONS_PATH = DATA_DIR / "HI-Small_Trans.csv"
PATTERNS_PATH = DATA_DIR / "HI-Small_Patterns.txt"
GRAPH_CACHE_PATH = DATA_DIR / "processed" / "graph.pkl"


def _score_case(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Score one case (from group_into_cases) into its list-view summary and full detail."""
    sub_scores = compute_sub_scores(case)
    risk_score = compute_risk_score(sub_scores)
    risk_tier = assign_risk_tier(risk_score)
    evidence_text = generate_evidence_text(case)
    detail = case_to_api_detail(case, sub_scores, risk_score, risk_tier, evidence_text)

    summary = {
        "case_id": case["case_id"],
        "risk_tier": risk_tier,
        "risk_score": risk_score,
        "account_count": len(case["accounts"]),
        # When the case's evidence became complete, not "now" -- this
        # dataset is historical, so wall-clock time at pipeline-run isn't
        # meaningful here.
        "flagged_at": case["end_time"].isoformat() + "Z",
    }
    return summary, detail


def run_full_pipeline() -> dict[str, Any]:
    """Run the full ml/ pipeline and return API-contract-shaped cases + metrics.

    Detection/case-scoring runs on the held-out test split (the same
    split every other ml/ module's __main__ has been validated against
    so far), not train+val+test combined -- consistent with how the
    3,435-case, 0-cases-over-20-nodes result reported earlier was produced.

    Returns:
        {
          "cases": [ {case_id, risk_tier, risk_score, account_count, flagged_at}, ... ],
          "case_details": { case_id: { ...full GET /cases/{id} shape... }, ... },
          "metrics": { "baseline": {precision, recall, f1}, "candidate": {precision, recall, f1} },
          "tier_counts": {"monitor": int, "review": int, "str_ready": int},
        }
    """
    logger.info("run_full_pipeline: starting")

    transactions = load_transactions(str(TRANSACTIONS_PATH))
    patterns = load_patterns(str(PATTERNS_PATH))

    try:
        graph = load_cached_graph(str(GRAPH_CACHE_PATH))
    except FileNotFoundError:
        logger.info("run_full_pipeline: no cached graph at %s, building one", GRAPH_CACHE_PATH)
        graph = build_graph(transactions)
        cache_graph(graph, str(GRAPH_CACHE_PATH))

    labeled = build_ground_truth(patterns, transactions)
    train_df, _val_df, test_df = time_based_split(labeled)

    label_cols = ["is_laundering", "pattern_type"]
    test_features = test_df.drop(columns=label_cols)
    test_labels = test_df[label_cols]

    # --- cases: detect + group + score on the test split ---
    cases = group_into_cases(test_features, graph)
    logger.info("run_full_pipeline: scoring %d cases", len(cases))

    case_summaries = []
    case_details = {}
    tier_counts = {"monitor": 0, "review": 0, "str_ready": 0}
    for case in cases:
        summary, detail = _score_case(case)
        case_summaries.append(summary)
        case_details[summary["case_id"]] = detail
        tier_counts[summary["risk_tier"]] = tier_counts.get(summary["risk_tier"], 0) + 1

    logger.info(
        "run_full_pipeline: %d cases -- monitor=%d, review=%d, str_ready=%d",
        len(case_summaries), tier_counts["monitor"], tier_counts["review"], tier_counts["str_ready"],
    )

    # --- metrics: naive baseline vs combined structural detector, same
    # methodology as evaluate.py's own __main__ (threshold fit on train,
    # both detectors scored on test) -- reused via evaluate_on_split, not
    # reimplemented here.
    threshold = compute_percentile_threshold(train_df)
    baseline_metrics = evaluate_on_split(
        test_features, test_labels, lambda df: baseline_naive_threshold(df, graph=graph, threshold_amount=threshold)
    )
    candidate_metrics = evaluate_on_split(
        test_features, test_labels, lambda df: combined_structural_detector(df, graph)
    )
    metrics = {
        "baseline": {k: baseline_metrics[k] for k in ("precision", "recall", "f1")},
        "candidate": {k: candidate_metrics[k] for k in ("precision", "recall", "f1")},
    }
    logger.info(
        "run_full_pipeline: metrics -- baseline f1=%.4f, candidate f1=%.4f",
        metrics["baseline"]["f1"], metrics["candidate"]["f1"],
    )

    logger.info("run_full_pipeline: done")
    return {
        "cases": case_summaries,
        "case_details": case_details,
        "metrics": metrics,
        "tier_counts": tier_counts,
    }


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run_full_pipeline()
    print(f"\ncases: {len(result['cases']):,}")
    print(f"tier_counts: {result['tier_counts']}")
    print(f"metrics:\n{json.dumps(result['metrics'], indent=2)}")
