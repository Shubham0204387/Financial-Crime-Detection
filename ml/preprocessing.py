"""Preprocessing pipeline: raw transaction data -> graph-ready structures.

Not implemented yet. Function signatures and docstrings only.
"""

from typing import Any

import networkx as nx
import pandas as pd


def load_transactions(path: str) -> pd.DataFrame:
    """Load raw transaction records from a CSV file.

    Args:
        path: Path to a CSV file with columns such as source_account,
            target_account, amount, timestamp.

    Returns:
        A DataFrame of raw transactions, one row per transfer.
    """
    raise NotImplementedError


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate, drop malformed rows, and normalize dtypes/timezones.

    Args:
        df: Raw transaction DataFrame as returned by load_transactions.

    Returns:
        A cleaned DataFrame safe to build a graph from.
    """
    raise NotImplementedError


def build_transaction_graph(df: pd.DataFrame) -> nx.MultiDiGraph:
    """Build a directed multigraph of accounts and transfers.

    Args:
        df: Cleaned transaction DataFrame.

    Returns:
        A networkx MultiDiGraph where nodes are account ids and edges are
        individual transactions (source -> target) carrying amount and
        timestamp attributes.
    """
    raise NotImplementedError


def compute_account_features(graph: nx.MultiDiGraph) -> pd.DataFrame:
    """Compute per-account features used as detection inputs.

    Expected features include transaction velocity (transfers per unit
    time), fan-in/fan-out ratio, and other graph-derived statistics.

    Args:
        graph: Transaction graph as returned by build_transaction_graph.

    Returns:
        A DataFrame indexed by account id with one column per feature.
    """
    raise NotImplementedError


def to_case_payload(graph: nx.MultiDiGraph, account_ids: list[str]) -> dict[str, Any]:
    """Convert a subgraph around the given accounts into the API's node/edge shape.

    Args:
        graph: Full transaction graph.
        account_ids: Accounts to include in the case (plus their direct
            neighbors, at the implementer's discretion).

    Returns:
        A dict with "nodes" and "edges" keys matching the shapes documented
        in docs/api-contract.md under GET /cases/{case_id}.
    """
    raise NotImplementedError
