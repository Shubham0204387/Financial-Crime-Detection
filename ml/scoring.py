"""Case grouping and risk scoring: detector flags -> scored, explainable cases.

detect_cycles and detect_fan_in_out (ml/detection.py) return a boolean
flag per transaction, with no notion of which flagged transactions
belong together as one detected structure. This module bridges that gap:
group_into_cases clusters flagged transactions into cases by connectivity,
and the scoring functions below turn each case into the explainable
sub_scores / risk_score / risk_tier / evidence_text shape docs/api-contract.md
requires for GET /cases/{case_id}.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import networkx as nx
import pandas as pd

logger = logging.getLogger(__name__)

# Mirrors detect_cycles' / detect_fan_in_out's own time_window_hours
# defaults (ml/detection.py) -- the maximum span either detector allows
# before it stops considering something a match. Used as the reference
# scale for compute_sub_scores' velocity score: "how much of the allowed
# window did this case actually use", not an arbitrary hour count.
CYCLE_REFERENCE_WINDOW_HOURS = 48.0
FAN_REFERENCE_WINDOW_HOURS = 12.0

# compute_risk_score's weights. cycle_match is weighted highest because
# evaluate.py's own three-way comparison (see ml/evaluate.py __main__)
# found cycle-only detection empirically far more precise (0.1081) than
# fan-based signals (combined detector precision 0.0053) on the test
# split -- a confirmed closed loop is the single most reliable structural
# signal available, so it should dominate the blend.
RISK_WEIGHTS = {"cycle_match": 0.45, "fan_ratio": 0.30, "velocity": 0.25}


def group_into_cases(
    transactions_df: pd.DataFrame,
    graph: nx.MultiDiGraph | None,
    cycle_flags: pd.Series,
    fan_flags: pd.Series,
) -> list[dict[str, Any]]:
    """Cluster flagged transactions into cases by account connectivity.

    Neither detect_cycles nor detect_fan_in_out records which flagged
    transactions belong to the same detected structure -- both return a
    flat boolean flag per transaction. This recovers that grouping via
    connected components: build an undirected graph over the accounts
    touched by any flagged transaction, and treat each connected
    component as one case. A genuine cycle instance's accounts form a
    tight closed loop (one component); a genuine fan-in/out burst's
    accounts form a star around its hub (one component). Two clusters
    that happen to share an account (e.g. a fan-out target that's also
    on an unrelated detected cycle) merge into a single case tagged with
    both pattern types -- a deliberate simplification for this v1, not a
    guarantee that every case corresponds to exactly one detector event.

    Args:
        transactions_df: The full split the flags were computed on (same
            frame passed to detect_cycles/detect_fan_in_out).
        graph: Unused; accepted for consistency with the detector
            functions this consumes.
        cycle_flags: Boolean Series aligned to transactions_df's row
            order, as returned by detect_cycles.
        fan_flags: Boolean Series aligned to transactions_df's row order,
            as returned by detect_fan_in_out.

    Returns:
        A list of case dicts, each with:
        - case_id: "CASE-0001", "CASE-0002", ... (sequential).
        - accounts: set of account ids in the case.
        - transactions: DataFrame slice of this case's transactions.
        - detected_patterns: frozenset subset of {"cycle", "fan_in_out"}.
        - pattern_type: API-contract enum derived from detected_patterns
          ("cycle" if cycle evidence is present, else "scatter_gather").
        - start_time / end_time / time_span: this case's transactions'
          Timestamp range.
    """
    df = transactions_df.reset_index(drop=True)
    cycle_flags = pd.Series(cycle_flags).reset_index(drop=True)
    fan_flags = pd.Series(fan_flags).reset_index(drop=True)

    flagged_mask = cycle_flags | fan_flags
    flagged_df = df.loc[flagged_mask]
    logger.info(
        "group_into_cases: clustering %d flagged transactions (%d cycle, %d fan_in_out)",
        len(flagged_df), int(cycle_flags.sum()), int(fan_flags.sum()),
    )

    if flagged_df.empty:
        return []

    account_graph = nx.Graph()
    account_graph.add_edges_from(zip(flagged_df["From Account"], flagged_df["To Account"]))

    components = list(nx.connected_components(account_graph))
    account_to_component: dict[str, int] = {}
    for component_id, accounts in enumerate(components):
        for account in accounts:
            account_to_component[account] = component_id

    rows_by_component: dict[int, list[int]] = defaultdict(list)
    for row_idx, from_account in zip(flagged_df.index, flagged_df["From Account"]):
        rows_by_component[account_to_component[from_account]].append(row_idx)

    cases = []
    for case_num, (component_id, row_indices) in enumerate(sorted(rows_by_component.items()), start=1):
        case_txs = df.loc[row_indices]
        accounts = set(case_txs["From Account"]) | set(case_txs["To Account"])

        has_cycle = bool(cycle_flags.loc[row_indices].any())
        has_fan = bool(fan_flags.loc[row_indices].any())
        detected_patterns = frozenset(
            p for p, present in (("cycle", has_cycle), ("fan_in_out", has_fan)) if present
        )
        pattern_type = "cycle" if "cycle" in detected_patterns else "scatter_gather"

        start_time = case_txs["Timestamp"].min()
        end_time = case_txs["Timestamp"].max()

        cases.append({
            "case_id": f"CASE-{case_num:04d}",
            "accounts": accounts,
            "transactions": case_txs,
            # Connected components can merge an unrelated cycle cluster and
            # fan cluster into one case (they share an account). These
            # pattern-specific slices let compute_sub_scores and
            # generate_evidence_text reason about "the cycle's" or "the fan
            # burst's" own amounts/timing without being contaminated by the
            # other pattern's unrelated transactions in a merged case.
            "cycle_transactions": case_txs.loc[cycle_flags.loc[row_indices]],
            "fan_transactions": case_txs.loc[fan_flags.loc[row_indices]],
            "detected_patterns": detected_patterns,
            "pattern_type": pattern_type,
            "start_time": start_time,
            "end_time": end_time,
            "time_span": end_time - start_time,
        })

    component_sizes = sorted((len(c["accounts"]) for c in cases), reverse=True)
    logger.info(
        "group_into_cases: %d cases from %d connected components (largest: %d accounts, "
        "median: %d accounts)",
        len(cases), len(components), component_sizes[0] if component_sizes else 0,
        component_sizes[len(component_sizes) // 2] if component_sizes else 0,
    )
    return cases


def _hub_account_degrees(case_txs: pd.DataFrame) -> tuple[str, int, int]:
    """Find the case's central account and its distinct in/out counterparty counts."""
    out_deg = case_txs.groupby("From Account")["To Account"].nunique()
    in_deg = case_txs.groupby("To Account")["From Account"].nunique()
    total_deg = out_deg.add(in_deg, fill_value=0)
    hub_account = total_deg.idxmax()
    return hub_account, int(out_deg.get(hub_account, 0)), int(in_deg.get(hub_account, 0))


def _largest_topological_cycle_fraction(case: dict[str, Any]) -> float:
    """Fraction of a case's accounts that sit on its largest directed cycle, ignoring timing.

    Used only for cases without a chronologically-confirmed cycle (i.e.
    detect_cycles didn't flag them): even an unconfirmed topological loop
    (accounts that could form a cycle, whether or not the transactions
    happened in a valid order) is partial evidence, scaled by how much of
    the case's structure it actually covers.
    """
    case_txs = case["transactions"]
    topo = nx.DiGraph()
    topo.add_edges_from(zip(case_txs["From Account"], case_txs["To Account"]))

    largest = 0
    for cycle in nx.simple_cycles(topo, length_bound=len(case["accounts"])):
        largest = max(largest, len(cycle))

    total_accounts = len(case["accounts"])
    return largest / total_accounts if total_accounts else 0.0


def compute_sub_scores(case: dict[str, Any]) -> dict[str, float]:
    """Compute velocity, fan_ratio, and cycle_match sub-scores (each 0-100) for a case.

    velocity: 100 * (1 - time_span / reference_window), clipped to
        [0, 100]. reference_window is CYCLE_REFERENCE_WINDOW_HOURS (48h)
        if the case has cycle evidence, else FAN_REFERENCE_WINDOW_HOURS
        (12h) -- the same time_window_hours the relevant detector used to
        even consider this case a match. A case that closed in 2 hours
        out of a possible 48 used up little of its allowed window (high
        velocity, more suspicious); one that took nearly the full window
        used almost all of it (velocity near 0).

    fan_ratio: 100 * |out_degree - in_degree| / (out_degree + in_degree)
        for the case's hub account (the account with the most distinct
        counterparties within this case's own transactions), where
        out_degree/in_degree count DISTINCT counterparties (matching the
        definition detect_fan_in_out itself uses). A pure scatter (funds
        out to many, none back) or pure gather (funds in from many, none
        out) scores 100; a pass-through account with one counterparty on
        each side (typical of a pure cycle hop) scores 0.

    cycle_match: 100 if "cycle" is in the case's detected_patterns (i.e.
        detect_cycles already confirmed a chronologically valid closed
        loop for this case). Otherwise, 100 * (size of the largest
        topological directed cycle among the case's accounts, ignoring
        timestamp order / the detector's time window) / (total accounts
        in the case) -- partial credit for a structure that could close a
        loop even though it wasn't a confirmed instance. 0 if no cyclic
        structure exists at all (e.g. a pure fan-out star).

    Args:
        case: A case dict as returned by group_into_cases.

    Returns:
        {"velocity": float, "fan_ratio": float, "cycle_match": float},
        each in [0, 100].
    """
    case_txs = case["transactions"]

    reference_hours = CYCLE_REFERENCE_WINDOW_HOURS if "cycle" in case["detected_patterns"] else FAN_REFERENCE_WINDOW_HOURS
    time_span_hours = case["time_span"] / pd.Timedelta(hours=1)
    velocity = 100.0 * max(0.0, min(1.0, 1.0 - time_span_hours / reference_hours))

    # Use the fan-specific transaction slice for the hub's degree, not the
    # full case: a merged cycle+fan case would otherwise have its fan
    # imbalance diluted (or distorted) by unrelated cycle hops through the
    # same account. Pure-cycle cases have no fan_transactions, so fall back
    # to the full (all-cycle) set, which correctly yields low imbalance.
    fan_source = case["fan_transactions"] if len(case["fan_transactions"]) else case_txs
    _, hub_out, hub_in = _hub_account_degrees(fan_source)
    fan_ratio = 100.0 * abs(hub_out - hub_in) / (hub_out + hub_in) if (hub_out + hub_in) else 0.0

    if "cycle" in case["detected_patterns"]:
        cycle_match = 100.0
    else:
        cycle_match = 100.0 * _largest_topological_cycle_fraction(case)

    return {"velocity": velocity, "fan_ratio": fan_ratio, "cycle_match": cycle_match}


def compute_risk_score(sub_scores: dict[str, float]) -> int:
    """Combine sub-scores into a single 0-100 risk score via a weighted average.

    A simple, documented linear blend (RISK_WEIGHTS) -- not a trained
    model, deliberately, so the number stays explainable: risk_score =
    round(0.45*cycle_match + 0.30*fan_ratio + 0.25*velocity). See
    RISK_WEIGHTS' docstring comment for why cycle_match is weighted
    highest.

    Args:
        sub_scores: Dict with keys "velocity", "fan_ratio", "cycle_match",
            each 0-100 (e.g. from compute_sub_scores).

    Returns:
        An integer risk score, 0-100.
    """
    score = sum(RISK_WEIGHTS[key] * sub_scores[key] for key in RISK_WEIGHTS)
    return round(max(0.0, min(100.0, score)))


# Tier cutoffs, derived from the actual risk_score distribution observed
# across all 2,411 cases detected on the test split (see ml/scoring.py
# __main__ output). That distribution is bimodal with a valley between
# it: a ~30s hump (975 cases), a valley at 40-49 (441 cases, the
# distribution's lowest point between two peaks), a ~50s hump (731
# cases), then a sharp drop-off past 59 (only 112 of 2,411 cases score
# >= 60, i.e. p95 == 58). The cutoffs sit exactly at that valley and that
# drop-off, not round numbers -- they split the population into
# monitor=1,127 (46.7%), review=1,172 (48.6%), str_ready=112 (4.6%).
MONITOR_REVIEW_CUTOFF = 40
REVIEW_STR_READY_CUTOFF = 60


def assign_risk_tier(
    risk_score: int,
    monitor_review_cutoff: int = MONITOR_REVIEW_CUTOFF,
    review_str_ready_cutoff: int = REVIEW_STR_READY_CUTOFF,
) -> str:
    """Map a risk score to a tier using data-derived cutoffs.

    Args:
        risk_score: 0-100, as returned by compute_risk_score.
        monitor_review_cutoff: Scores strictly below this are "monitor".
        review_str_ready_cutoff: Scores strictly below this (and >=
            monitor_review_cutoff) are "review"; scores at or above it
            are "str_ready".

    Returns:
        One of "monitor", "review", "str_ready".
    """
    if risk_score < monitor_review_cutoff:
        return "monitor"
    if risk_score < review_str_ready_cutoff:
        return "review"
    return "str_ready"


def generate_evidence_text(case: dict[str, Any]) -> str:
    """Build a plain-language evidence string from a case's actual data.

    Follows the style used in backend/mock_data/cases_mock.json: a
    concrete, numbers-first description (amounts, account/hop counts,
    time span), not a generic template -- branches on whether the case
    has confirmed cycle evidence, fan-in/out evidence, or both.

    Args:
        case: A case dict as returned by group_into_cases.

    Returns:
        A plain-language evidence string.
    """
    def fmt_span(hours: float) -> str:
        if hours < 1:
            return f"{hours * 60:.0f} minutes"
        return f"{hours:.1f} hours"

    parts = []

    if "cycle" in case["detected_patterns"]:
        # Scoped to cycle_transactions specifically, not the full (possibly
        # merged-with-an-unrelated-fan-cluster) case -- otherwise "first"/
        # "last" amount can come from two unconnected transactions and
        # produce a nonsensical retention percentage.
        cycle_txs = case["cycle_transactions"].sort_values("Timestamp")
        cycle_accounts = set(cycle_txs["From Account"]) | set(cycle_txs["To Account"])
        cycle_span_hours = (cycle_txs["Timestamp"].max() - cycle_txs["Timestamp"].min()) / pd.Timedelta(hours=1)
        first_amount = float(cycle_txs["Amount Paid"].iloc[0])
        last_amount = float(cycle_txs["Amount Paid"].iloc[-1])
        retention_pct = 100.0 * last_amount / first_amount if first_amount else 0.0
        parts.append(
            f"${first_amount:,.2f} entered a closed {len(cycle_accounts)}-account cycle and returned to "
            f"the originating account within {fmt_span(cycle_span_hours)}, retaining {retention_pct:.0f}% "
            f"of its original value across {len(cycle_txs)} hops."
        )

    if "fan_in_out" in case["detected_patterns"]:
        fan_txs = case["fan_transactions"]
        fan_amount = float(fan_txs["Amount Paid"].sum())
        fan_span_hours = (fan_txs["Timestamp"].max() - fan_txs["Timestamp"].min()) / pd.Timedelta(hours=1)
        hub_account, hub_out, hub_in = _hub_account_degrees(fan_txs)
        if hub_out >= hub_in:
            parts.append(
                f"${fan_amount:,.2f} total was scattered from account {hub_account} out to "
                f"{hub_out} distinct accounts within {fmt_span(fan_span_hours)}."
            )
        else:
            parts.append(
                f"${fan_amount:,.2f} total was gathered into account {hub_account} from "
                f"{hub_in} distinct accounts within {fmt_span(fan_span_hours)}."
            )

    if not parts:
        case_txs = case["transactions"]
        total_amount = float(case_txs["Amount Paid"].sum())
        account_count = len(case["accounts"])
        span_hours = case["time_span"] / pd.Timedelta(hours=1)
        parts.append(
            f"${total_amount:,.2f} moved across {account_count} accounts in {len(case_txs)} transactions "
            f"within {fmt_span(span_hours)}; no confirmed cycle or fan-in/out structure was matched."
        )

    return " ".join(parts)


def _case_to_api_detail(
    case: dict[str, Any], sub_scores: dict[str, float], risk_score: int, risk_tier: str, evidence_text: str
) -> dict[str, Any]:
    """Shape a scored case into the GET /cases/{case_id} response, per docs/api-contract.md."""
    case_txs = case["transactions"]
    nodes = [{"id": account, "label": f"Account {account}"} for account in sorted(case["accounts"])]
    edges = [
        {
            "source": row["From Account"],
            "target": row["To Account"],
            "amount": round(float(row["Amount Paid"]), 2),
            "timestamp": row["Timestamp"].isoformat() + "Z",
        }
        for _, row in case_txs.sort_values("Timestamp").iterrows()
    ]
    # No regulatory deadline data exists in this dataset; 30 days from the
    # case's last transaction is a placeholder consistent with typical
    # STR filing windows, not a derived/observed value.
    str_deadline = (case["end_time"] + pd.Timedelta(days=30)).isoformat() + "Z"

    return {
        "case_id": case["case_id"],
        "risk_tier": risk_tier,
        "risk_score": risk_score,
        "sub_scores": {k: round(v, 1) for k, v in sub_scores.items()},
        "pattern_type": case["pattern_type"],
        "nodes": nodes,
        "edges": edges,
        "evidence_text": evidence_text,
        "str_deadline": str_deadline,
    }


if __name__ == "__main__":
    import json

    from ml.detection import detect_cycles, detect_fan_in_out
    from ml.labels import build_ground_truth
    from ml.preprocessing import load_patterns, load_transactions, time_based_split

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_dir = __import__("pathlib").Path(__file__).resolve().parent / "data"
    transactions = load_transactions(str(data_dir / "HI-Small_Trans.csv"))
    patterns = load_patterns(str(data_dir / "HI-Small_Patterns.txt"))
    labeled = build_ground_truth(patterns, transactions)
    _, _, test_df = time_based_split(labeled)

    features = test_df.drop(columns=["is_laundering", "pattern_type"])
    cycle_flags = detect_cycles(features, None)
    fan_flags = detect_fan_in_out(features, None)

    cases = group_into_cases(features, None, cycle_flags, fan_flags)

    scored_cases = []
    for case in cases:
        sub_scores = compute_sub_scores(case)
        risk_score = compute_risk_score(sub_scores)
        risk_tier = assign_risk_tier(risk_score)
        evidence_text = generate_evidence_text(case)
        scored_cases.append((case, sub_scores, risk_score, risk_tier, evidence_text))

    risk_scores = pd.Series([rs for _, _, rs, _, _ in scored_cases])
    tier_counts = pd.Series([rt for _, _, _, rt, _ in scored_cases]).value_counts()

    print(f"\n=== Case scoring summary -- test split ===")
    print(f"total cases: {len(scored_cases):,}")
    print("\nrisk_score distribution:")
    print(risk_scores.describe().to_string())
    print("\ntier distribution:")
    for tier in ["monitor", "review", "str_ready"]:
        count = int(tier_counts.get(tier, 0))
        print(f"  {tier:<10} {count:>6,} ({100 * count / len(scored_cases):.1f}%)")

    print("\n=== Example case objects (API contract shape) ===")
    by_tier = {"monitor": [], "review": [], "str_ready": []}
    for entry in scored_cases:
        by_tier[entry[3]].append(entry)

    examples = []
    if by_tier["str_ready"]:
        examples.append(max(by_tier["str_ready"], key=lambda e: e[2]))
    if by_tier["review"]:
        examples.append(sorted(by_tier["review"], key=lambda e: e[2])[len(by_tier["review"]) // 2])
    if by_tier["monitor"]:
        examples.append(sorted(by_tier["monitor"], key=lambda e: e[2])[len(by_tier["monitor"]) // 2])
    both_pattern = [e for e in scored_cases if len(e[0]["detected_patterns"]) > 1]
    if both_pattern:
        examples.append(both_pattern[0])

    for case, sub_scores, risk_score, risk_tier, evidence_text in examples[:4]:
        detail = _case_to_api_detail(case, sub_scores, risk_score, risk_tier, evidence_text)
        print(f"\n--- {detail['case_id']} ({risk_tier}, detected_patterns={sorted(case['detected_patterns'])}) ---")
        print(json.dumps(detail, indent=2))
