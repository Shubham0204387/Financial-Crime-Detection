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
import time
from collections import defaultdict

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


def _time_windows(min_ts: pd.Timestamp, max_ts: pd.Timestamp, window_hours: float):
    """Yield overlapping (start, end) windows covering [min_ts, max_ts].

    Each window spans 2*window_hours and consecutive windows are stepped
    by window_hours (50% overlap). That guarantees any span of
    transactions no wider than window_hours falls entirely inside at
    least one yielded window, regardless of where it starts -- proof: if
    a span's earliest timestamp t satisfies start <= t < start + step for
    some window, and the span is <= window_hours (== step) wide, then its
    latest timestamp is < start + step + window_hours == start + 2*step,
    which is exactly that window's end.
    """
    step = pd.Timedelta(hours=window_hours)
    span = pd.Timedelta(hours=2 * window_hours)
    start = min_ts
    while start <= max_ts:
        yield start, start + span
        start += step


def detect_cycles(
    transactions_df: pd.DataFrame,
    graph: nx.MultiDiGraph | None = None,
    max_hops: int = 6,
    time_window_hours: float = 48,
) -> pd.Series:
    """Flag transactions that are part of a short directed money-flow cycle.

    Searches for account-level cycles (A -> B -> ... -> A) of at most
    max_hops accounts, then requires a concrete chronological instance:
    an actual transaction for each hop, each one's timestamp no earlier
    than the previous hop's, with the whole loop completing within
    time_window_hours. A same-day round-trip is a much stronger
    laundering signal than accounts that happen to be mutually connected
    months apart, so this constraint is load-bearing, not incidental --
    it's also what "flagged as part of a detected cycle" is scoped to:
    only the specific transactions realizing a valid chronological
    instance are flagged, not every transaction between any two accounts
    that happen to sit on a cycle.

    Full-graph cycle enumeration (nx.simple_cycles on the whole 5M-edge
    dataset) is intractable, so this searches window by window: each
    window spans 2*time_window_hours (see _time_windows), which keeps
    every individual cycle search bounded to that window's transactions
    while still guaranteeing full coverage of any genuine
    <= time_window_hours cycle.

    Args:
        transactions_df: Transaction rows to scan (a full split or
            subset), needs Timestamp, From Account, To Account.
        graph: Unused. The search is windowed directly off
            transactions_df rather than the full precomputed graph,
            since transactions_df is typically a time-bounded split and
            the full graph would include edges outside it. Present for
            signature parity with other detectors.
        max_hops: Maximum number of accounts in a candidate cycle.
        time_window_hours: Maximum span, in hours, between a cycle
            instance's first and last transaction for it to count.

    Returns:
        A boolean pd.Series aligned to transactions_df's row order/index,
        True for transactions that are part of at least one detected
        cycle instance.
    """
    start_time = time.monotonic()
    df = transactions_df.reset_index(drop=True)
    flagged = pd.Series(False, index=df.index)

    if df.empty:
        return flagged

    min_ts, max_ts = df["Timestamp"].min(), df["Timestamp"].max()
    windows = list(_time_windows(min_ts, max_ts, time_window_hours))
    logger.info(
        "detect_cycles: scanning %d overlapping %.0fh windows (step %.0fh) over %d transactions",
        len(windows), 2 * time_window_hours, time_window_hours, len(df),
    )

    cycle_instances = 0
    for window_idx, (w_start, w_end) in enumerate(windows):
        window_start_time = time.monotonic()
        window_mask = (df["Timestamp"] >= w_start) & (df["Timestamp"] < w_end)
        window_df = df.loc[window_mask]
        if len(window_df) < 2:
            continue

        topo = nx.DiGraph()
        topo.add_edges_from(zip(window_df["From Account"], window_df["To Account"]))

        # Per (u, v) pair: timestamps + row indices, sorted ascending, so
        # instantiation below can pick the earliest hop >= the running
        # chronological lower bound.
        hop_index: dict[tuple, list[tuple[pd.Timestamp, int]]] = defaultdict(list)
        for row_idx, u, v, ts in zip(
            window_df.index, window_df["From Account"], window_df["To Account"], window_df["Timestamp"]
        ):
            hop_index[(u, v)].append((ts, row_idx))
        for pairs in hop_index.values():
            pairs.sort()

        window_cycle_count = 0
        for cycle in nx.simple_cycles(topo, length_bound=max_hops):
            if len(cycle) < 2:
                continue

            # nx.simple_cycles returns the cycle starting at an arbitrary
            # node, not necessarily the one whose outgoing hop happened
            # first -- try every rotation as the candidate start and take
            # the first one that produces a valid non-decreasing chain of
            # actual transactions all the way around.
            instance = None
            for rotation in range(len(cycle)):
                rotated = cycle[rotation:] + cycle[:rotation]
                hops = list(zip(rotated, rotated[1:] + rotated[:1]))
                candidate = []
                lower_bound = None
                valid = True
                for u, v in hops:
                    chosen = None
                    for ts, row_idx in hop_index.get((u, v), []):
                        if lower_bound is None or ts >= lower_bound:
                            chosen = (ts, row_idx)
                            break
                    if chosen is None:
                        valid = False
                        break
                    lower_bound = chosen[0]
                    candidate.append(chosen)
                if valid:
                    instance = candidate
                    break

            if instance is None:
                continue
            if instance[-1][0] - instance[0][0] > pd.Timedelta(hours=time_window_hours):
                continue

            for _, row_idx in instance:
                flagged.at[row_idx] = True
            window_cycle_count += 1

        cycle_instances += window_cycle_count
        logger.info(
            "  window %d/%d [%s -> %s): %d transactions, %d cycle instances, %.2fs",
            window_idx + 1, len(windows), w_start, w_end,
            len(window_df), window_cycle_count, time.monotonic() - window_start_time,
        )

    elapsed = time.monotonic() - start_time
    logger.info(
        "detect_cycles: flagged %d / %d transactions (%.4f%%) across %d cycle instances in %.2fs",
        int(flagged.sum()), len(df), 100 * flagged.mean() if len(df) else 0.0, cycle_instances, elapsed,
    )
    return flagged


def detect_fan_in_out(
    transactions_df: pd.DataFrame,
    graph: nx.MultiDiGraph | None = None,
    min_fan: int = 5,
    time_window_hours: float = 12,
    hub_degree_cap: int = 30,
) -> pd.Series:
    """Flag transactions where an account fans in/out to many counterparties fast.

    An account that sends to (or receives from) >= min_fan distinct
    counterparties within time_window_hours is flagged, along with every
    transaction that contributed to that count -- a structuring/smurfing
    signal (one source scattering funds to many accounts, or many
    accounts gathering into one).

    Accounts whose TOTAL distinct-counterparty count across all of
    transactions_df (not just one window) exceeds hub_degree_cap are
    excluded entirely, regardless of min_fan. Investigating why an
    unbounded threshold flagged 23% of the test split found this wasn't
    a threshold-sensitivity problem: a small number of accounts (as few
    as 15-108, depending on cap) are payment-processor-style hubs with
    fan counts up to 9,637 in a single window, responsible for tens of
    thousands of transactions with zero overlap with labeled laundering.
    No min_fan/time_window_hours combination separates them from genuine
    bursts -- true FAN-IN/FAN-OUT labels in this dataset have low
    absolute degree (as low as 3), so they sit on top of ordinary
    background activity at that same degree level. hub_degree_cap=30 with
    min_fan=5, time_window_hours=12 is the tuned operating point: it cuts
    the flagged count roughly 5x versus no hub exclusion while lifting
    recall about 11x over the naive amount-threshold baseline.

    Uses fixed, non-overlapping time_window_hours-wide bins, unlike
    detect_cycles' overlapping windows. That's a deliberate simplification:
    fan-in/out is a count threshold, not an exact structural match, so an
    occasional burst split across a bin boundary just becomes two smaller
    (possibly sub-threshold) bursts instead of one -- a soft miss, not a
    correctness bug the way splitting a cycle's hops would be.

    Args:
        transactions_df: Transaction rows to scan (a full split or
            subset), needs Timestamp, From Account, To Account.
        graph: Unused; present for signature parity with other detectors.
        min_fan: Minimum distinct counterparties within a bin to flag an
            account as fanning in/out.
        time_window_hours: Width of each time bin, in hours.
        hub_degree_cap: Accounts with more than this many distinct
            counterparties across the whole of transactions_df are
            treated as infrastructure/hub accounts and never flagged.

    Returns:
        A boolean pd.Series aligned to transactions_df's row order/index.
    """
    start_time = time.monotonic()
    df = transactions_df.reset_index(drop=True)

    if df.empty:
        return pd.Series(False, index=df.index)

    total_out_degree = df.groupby(df["From Account"], observed=True)["To Account"].transform("nunique")
    total_in_degree = df.groupby(df["To Account"], observed=True)["From Account"].transform("nunique")
    is_hub = (total_out_degree > hub_degree_cap) | (total_in_degree > hub_degree_cap)

    bin_id = ((df["Timestamp"] - df["Timestamp"].min()) / pd.Timedelta(hours=time_window_hours)).astype("int64")

    fan_out_counts = df.groupby([bin_id, df["From Account"]], observed=True)["To Account"].transform("nunique")
    fan_in_counts = df.groupby([bin_id, df["To Account"]], observed=True)["From Account"].transform("nunique")

    flagged = ((fan_out_counts >= min_fan) | (fan_in_counts >= min_fan)) & ~is_hub

    elapsed = time.monotonic() - start_time
    logger.info(
        "detect_fan_in_out: excluded %d / %d transactions as hub-account noise (degree > %d); "
        "flagged %d / %d (%.4f%%) in %.2fs (min_fan=%d, time_window_hours=%.0f)",
        int(is_hub.sum()), len(df), hub_degree_cap, int(flagged.sum()), len(df),
        100 * flagged.mean() if len(df) else 0.0, elapsed, min_fan, time_window_hours,
    )
    return flagged


def combined_structural_detector(
    transactions_df: pd.DataFrame,
    graph: nx.MultiDiGraph | None = None,
    max_hops: int = 6,
    cycle_time_window_hours: float = 48,
    min_fan: int = 5,
    fan_time_window_hours: float = 12,
    hub_degree_cap: int = 30,
) -> pd.Series:
    """OR-combine detect_cycles and detect_fan_in_out: flagged if either fires.

    A plain union, not a weighted/learned combination -- enough to see
    whether combining structural signals adds coverage beyond either
    detector alone. Weighting/scoring is future work (see
    score_cycle_match, score_fan_ratio, compute_risk_score below).

    Args:
        transactions_df: Transaction rows to scan.
        graph: Unused; forwarded to both detectors for signature parity.
        max_hops: Forwarded to detect_cycles.
        cycle_time_window_hours: Forwarded to detect_cycles as time_window_hours.
        min_fan: Forwarded to detect_fan_in_out.
        fan_time_window_hours: Forwarded to detect_fan_in_out as time_window_hours.
        hub_degree_cap: Forwarded to detect_fan_in_out.

    Returns:
        A boolean pd.Series aligned to transactions_df's row order/index.
    """
    cycle_flags = detect_cycles(transactions_df, graph, max_hops=max_hops, time_window_hours=cycle_time_window_hours)
    fan_flags = detect_fan_in_out(
        transactions_df, graph, min_fan=min_fan, time_window_hours=fan_time_window_hours, hub_degree_cap=hub_degree_cap
    )
    combined = cycle_flags | fan_flags
    logger.info(
        "combined_structural_detector: cycles=%d, fan_in_out=%d, combined=%d / %d flagged",
        int(cycle_flags.sum()), int(fan_flags.sum()), int(combined.sum()), len(transactions_df),
    )
    return combined


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
