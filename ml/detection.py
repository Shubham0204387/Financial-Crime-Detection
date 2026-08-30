"""Detection logic: graph/account features -> risk scores and pattern classification.

Not implemented yet. Function signatures and docstrings only.
"""

import networkx as nx
import pandas as pd


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
