"""Detection logic: graph/account features -> risk scores and pattern classification.

Detector functions (baseline_naive_threshold and, later, a structural
heuristic) share a common (transactions_df, graph) signature and return
a boolean pd.Series aligned to transactions_df's row order, so they're
directly interchangeable in evaluate.evaluate_on_split without any
caller-side branching. Everything below detect_cycles onward is not
implemented yet -- signatures and docstrings only.
"""

from __future__ import annotations

import logging

import networkx as nx
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD_PERCENTILE = 99.0


def compute_percentile_threshold(
    transactions_df: pd.DataFrame,
    percentile: float = DEFAULT_THRESHOLD_PERCENTILE,
    amount_column: str = "Amount Paid",
) -> float:
    """Compute a data-driven flagging threshold from the amount distribution.

    Args:
        transactions_df: Transaction DataFrame containing amount_column.
        percentile: Percentile (0-100) to use as the threshold. Defaults
            to p99 -- a round-number threshold like "$10,000" would be
            arbitrary given this dataset's amounts span many orders of
            magnitude across currencies.
        amount_column: Which amount column to compute the percentile over.

    Returns:
        The dollar (or currency-unit) value at the given percentile.
    """
    value = float(transactions_df[amount_column].quantile(percentile / 100))
    logger.info("p%.1f of '%s' = %.2f", percentile, amount_column, value)
    return value


def baseline_naive_threshold(
    transactions_df: pd.DataFrame,
    graph: nx.MultiDiGraph | None = None,
    threshold_amount: float | None = None,
) -> pd.Series:
    """Flag any single transaction whose amount exceeds a threshold.

    This is the naive baseline: it looks at each transaction in
    isolation and ignores graph structure entirely (graph is accepted
    only so this function's signature matches other detectors and can be
    swapped in/out of evaluate.evaluate_on_split without special-casing).

    Args:
        transactions_df: Transaction DataFrame (a full split or subset)
            with an "Amount Paid" column.
        graph: Unused by this detector; present for signature parity with
            future structural detectors.
        threshold_amount: Dollar amount above which a transaction is
            flagged. If None, defaults to compute_percentile_threshold's
            p99 of transactions_df's own "Amount Paid" column -- callers
            that want to avoid fitting the threshold on evaluation data
            should compute it on a train split and pass it in explicitly.

    Returns:
        A boolean pd.Series aligned to transactions_df's row order/index,
        True where the transaction is flagged.
    """
    if threshold_amount is None:
        threshold_amount = compute_percentile_threshold(transactions_df)
        logger.info(
            "No threshold_amount given; defaulting to p%.1f of this data's own Amount Paid: %.2f",
            DEFAULT_THRESHOLD_PERCENTILE, threshold_amount,
        )

    flags = transactions_df["Amount Paid"] > threshold_amount
    logger.info(
        "Naive threshold baseline (Amount Paid > %.2f): flagged %d / %d transactions (%.4f%%)",
        threshold_amount, int(flags.sum()), len(transactions_df),
        100 * flags.mean() if len(flags) else 0.0,
    )
    return flags


def detect_cycles(graph: nx.MultiDiGraph, max_length: int = 6) -> list[list[str]]:
    """Find closed transfer cycles up to a given length.

    Args:
        graph: Transaction graph as built by preprocessing.build_transaction_graph.
        max_length: Maximum number of accounts in a cycle to consider.

    Returns:
        A list of cycles, each a list of account ids in traversal order.
    """
    raise NotImplementedError


def detect_scatter_gather(graph: nx.MultiDiGraph) -> list[dict]:
    """Find fan-out/fan-in (scatter-gather) structures, e.g. structuring patterns.

    Args:
        graph: Transaction graph as built by preprocessing.build_transaction_graph.

    Returns:
        A list of dicts, each describing one scatter-gather subgraph found
        (origin account, intermediate accounts, destination account(s)).
    """
    raise NotImplementedError


def score_velocity(features: pd.DataFrame) -> pd.Series:
    """Score each account 0-100 on transaction velocity relative to peers.

    Args:
        features: Per-account feature DataFrame from
            preprocessing.compute_account_features.

    Returns:
        A Series indexed by account id with velocity sub-scores (0-100).
    """
    raise NotImplementedError


def score_fan_ratio(features: pd.DataFrame) -> pd.Series:
    """Score each account 0-100 on fan-in/fan-out imbalance.

    Args:
        features: Per-account feature DataFrame from
            preprocessing.compute_account_features.

    Returns:
        A Series indexed by account id with fan_ratio sub-scores (0-100).
    """
    raise NotImplementedError


def score_cycle_match(graph: nx.MultiDiGraph, cycles: list[list[str]]) -> pd.Series:
    """Score each account 0-100 on how closely it matches known cycle patterns.

    Args:
        graph: Transaction graph.
        cycles: Cycles detected by detect_cycles.

    Returns:
        A Series indexed by account id with cycle_match sub-scores (0-100).
    """
    raise NotImplementedError


def classify_pattern(cycles: list[list[str]], scatter_gathers: list[dict]) -> str:
    """Classify the dominant pattern type for a case.

    Args:
        cycles: Cycles detected by detect_cycles.
        scatter_gathers: Structures detected by detect_scatter_gather.

    Returns:
        One of "cycle", "scatter_gather", or "unclassified", matching the
        pattern_type field documented in docs/api-contract.md.
    """
    raise NotImplementedError


def compute_risk_score(sub_scores: dict[str, float]) -> int:
    """Combine sub-scores into a single overall risk score.

    Args:
        sub_scores: Dict with keys "velocity", "fan_ratio", "cycle_match",
            each 0-100.

    Returns:
        An overall risk score 0-100, matching the risk_score field
        documented in docs/api-contract.md.
    """
    raise NotImplementedError


def assign_risk_tier(risk_score: int) -> str:
    """Map an overall risk score to a risk tier.

    Args:
        risk_score: Overall risk score 0-100.

    Returns:
        One of "monitor", "review", or "str_ready", matching the risk_tier
        field documented in docs/api-contract.md.
    """
    raise NotImplementedError
