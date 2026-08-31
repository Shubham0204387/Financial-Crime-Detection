"""Case grouping and risk scoring: detector instances -> scored, explainable cases.

find_cycle_instances and find_fan_clusters (ml/detection.py) each already
identify one detected structure at a time -- a single closed loop, or a
single hub's fan-in/out burst in one time bin. group_into_cases turns
each one directly into exactly one case, tightly scoped to only the
accounts/transactions that make up that specific instance (1 cycle
instance = 1 case; 1 fan cluster = 1 case; never merged, even if they
share an account -- see group_into_cases' docstring for why). The scoring
functions below turn each case into the explainable sub_scores /
risk_score / risk_tier / evidence_text shape docs/api-contract.md
requires for GET /cases/{case_id}.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import networkx as nx
import pandas as pd

from ml.detection import find_cycle_instances, find_fan_clusters

logger = logging.getLogger(__name__)


def _add_working_days(start: datetime, working_days: int) -> datetime:
    """Add `working_days` weekdays (Mon-Fri) to `start`, skipping weekends."""
    current = start
    added = 0
    while added < working_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current

# A case with more nodes than this gets capped (see _cap_fan_case) --
# past this size a subgraph stops being visually/analytically useful for
# a human reviewer. Cycle instances are naturally bounded by max_hops
# (default 6) and never need capping; only fan clusters can exceed it.
MAX_CASE_NODES = 20

# Mirrors find_cycle_instances' / find_fan_clusters' own time_window_hours
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


def _finalize_case(
    case_id: str, case_txs: pd.DataFrame, accounts: set[str], pattern_type: str, truncation_note: str | None
) -> dict[str, Any]:
    start_time = case_txs["Timestamp"].min()
    end_time = case_txs["Timestamp"].max()
    case: dict[str, Any] = {
        "case_id": case_id,
        "accounts": accounts,
        "transactions": case_txs,
        "pattern_type": pattern_type,
        "start_time": start_time,
        "end_time": end_time,
        "time_span": end_time - start_time,
    }
    if truncation_note:
        case["truncation_note"] = truncation_note
    return case


def _cap_fan_case(
    case_txs: pd.DataFrame, hub_account: str, direction: str, max_nodes: int
) -> tuple[pd.DataFrame, set[str], str]:
    """Cap an oversized fan cluster to its top (max_nodes - 1) neighbors by transaction amount.

    Ranks each neighbor by its largest single transaction with the hub
    (a simple, explainable ranking: "show the biggest transfers first"),
    keeps the top max_nodes - 1 of them (leaving one node slot for the
    hub itself), and drops every transaction to/from the rest.
    """
    neighbor_col = "To Account" if direction == "out" else "From Account"
    neighbor_rank = case_txs.groupby(neighbor_col)["Amount Paid"].max().sort_values(ascending=False)
    total_neighbors = len(neighbor_rank)
    keep_neighbors = set(neighbor_rank.head(max_nodes - 1).index)

    capped_txs = case_txs[case_txs[neighbor_col].isin(keep_neighbors)]
    capped_accounts = {hub_account} | keep_neighbors
    verb = "fan-out" if direction == "out" else "fan-in"
    note = f"showing largest {len(capped_txs)} of {len(case_txs)} {verb} transfers ({len(keep_neighbors)} of {total_neighbors} accounts)"
    return capped_txs, capped_accounts, note


def group_into_cases(
    transactions_df: pd.DataFrame,
    graph: nx.MultiDiGraph | None = None,
    max_hops: int = 6,
    cycle_time_window_hours: float = 48,
    min_fan: int = 5,
    fan_time_window_hours: float = 12,
    hub_degree_cap: int = 30,
    max_case_nodes: int = MAX_CASE_NODES,
) -> list[dict[str, Any]]:
    """Turn each detected cycle instance / fan cluster directly into one case.

    Each case is scoped to exactly one detector-found motif instance --
    NOT a connected component over all flagged activity. An earlier
    version grouped by connectivity, which let unrelated clusters that
    happened to share one account merge into a single oversized,
    entangled case (one observed case had 57 nodes and ~130 edges, most
    unrelated to the motif that actually triggered the flag) -- unusable
    for subgraph visualization and misleading as evidence. This version
    calls find_cycle_instances and find_fan_clusters directly (rather
    than detect_cycles/detect_fan_in_out's flattened boolean flags,
    which lose the per-instance grouping) and builds one case per
    instance/cluster:
    - A cycle case contains ONLY that cycle's own accounts and hop
      transactions (find_cycle_instances already returns exactly that).
    - A fan case contains ONLY the hub account and its direct 1-hop
      fan-in/out neighbors within the triggering time bin -- no further
      expansion outward.
    If the same account appears in both a cycle instance and a separate
    fan cluster, that produces TWO separate cases, not one merged case --
    this also keeps pattern_type single-valued per case, matching
    docs/api-contract.md's enum ("cycle" | "scatter_gather" |
    "unclassified" -- never a combination).

    A fan case that would still exceed max_case_nodes (e.g. a hub with a
    very high but still-flagged fan count) is capped: see _cap_fan_case.

    Args:
        transactions_df: The split to detect on (e.g. a test split).
        graph: Unused; accepted for consistency with the detector functions.
        max_hops: Forwarded to find_cycle_instances.
        cycle_time_window_hours: Forwarded to find_cycle_instances as time_window_hours.
        min_fan: Forwarded to find_fan_clusters.
        fan_time_window_hours: Forwarded to find_fan_clusters as time_window_hours.
        hub_degree_cap: Forwarded to find_fan_clusters.
        max_case_nodes: Cases with more accounts than this are capped
            (fan cases only; cycle instances are already bounded by max_hops).

    Returns:
        A list of case dicts, each with:
        - case_id: "CASE-0001", "CASE-0002", ... (sequential).
        - accounts: set of account ids in the case (<= max_case_nodes).
        - transactions: DataFrame slice of this case's transactions.
        - pattern_type: "cycle" or "scatter_gather".
        - start_time / end_time / time_span: this case's transactions'
          Timestamp range.
        - truncation_note: present only if the case was capped; a string
          like "showing largest 19 of 34 fan-out transfers (19 of 34
          accounts)", meant to be folded into evidence_text.
    """
    df = transactions_df.reset_index(drop=True)

    cycle_instances = find_cycle_instances(df, max_hops=max_hops, time_window_hours=cycle_time_window_hours)
    fan_clusters = find_fan_clusters(
        df, min_fan=min_fan, time_window_hours=fan_time_window_hours, hub_degree_cap=hub_degree_cap
    )
    logger.info(
        "group_into_cases: %d cycle instances, %d fan clusters -> %d cases",
        len(cycle_instances), len(fan_clusters), len(cycle_instances) + len(fan_clusters),
    )

    cases = []
    case_num = 1

    for instance in cycle_instances:
        case_txs = df.loc[instance["row_indices"]]
        accounts = set(instance["accounts"])
        cases.append(_finalize_case(f"CASE-{case_num:04d}", case_txs, accounts, "cycle", None))
        case_num += 1

    for cluster in fan_clusters:
        case_txs = df.loc[cluster["row_indices"]]
        hub_account = cluster["hub_account"]
        neighbor_col = "To Account" if cluster["direction"] == "out" else "From Account"
        accounts = {hub_account} | set(case_txs[neighbor_col])

        truncation_note = None
        if len(accounts) > max_case_nodes:
            case_txs, accounts, truncation_note = _cap_fan_case(
                case_txs, hub_account, cluster["direction"], max_case_nodes
            )

        cases.append(_finalize_case(f"CASE-{case_num:04d}", case_txs, accounts, "scatter_gather", truncation_note))
        case_num += 1

    node_counts = sorted(len(c["accounts"]) for c in cases)
    logger.info(
        "group_into_cases: node counts across %d cases -- min=%d, median=%d, max=%d, over_cap(>%d)=%d",
        len(cases),
        node_counts[0] if node_counts else 0,
        node_counts[len(node_counts) // 2] if node_counts else 0,
        node_counts[-1] if node_counts else 0,
        max_case_nodes,
        sum(1 for n in node_counts if n > max_case_nodes),
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

    cycle_match: 100 if the case's pattern_type is "cycle" (i.e.
        find_cycle_instances already confirmed a chronologically valid
        closed loop for this case -- group_into_cases only builds
        "cycle" cases from confirmed instances). Otherwise (a
        "scatter_gather" case), 100 * (size of the largest topological
        directed cycle among the case's accounts, ignoring timestamp
        order / the detector's time window) / (total accounts in the
        case) -- partial credit for a structure that could close a loop
        even though it wasn't a confirmed instance. 0 if no cyclic
        structure exists at all (e.g. a pure fan-out star, the common case).

    Args:
        case: A case dict as returned by group_into_cases (always a
            single pattern_type -- "cycle" or "scatter_gather" -- so
            case["transactions"] is already scoped to just that motif's
            own transactions with no other pattern's noise mixed in).

    Returns:
        {"velocity": float, "fan_ratio": float, "cycle_match": float},
        each in [0, 100].
    """
    case_txs = case["transactions"]
    is_cycle = case["pattern_type"] == "cycle"

    reference_hours = CYCLE_REFERENCE_WINDOW_HOURS if is_cycle else FAN_REFERENCE_WINDOW_HOURS
    time_span_hours = case["time_span"] / pd.Timedelta(hours=1)
    velocity = 100.0 * max(0.0, min(1.0, 1.0 - time_span_hours / reference_hours))

    _, hub_out, hub_in = _hub_account_degrees(case_txs)
    fan_ratio = 100.0 * abs(hub_out - hub_in) / (hub_out + hub_in) if (hub_out + hub_in) else 0.0

    cycle_match = 100.0 if is_cycle else 100.0 * _largest_topological_cycle_fraction(case)

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
    time span), not a generic template. Since group_into_cases now scopes
    every case to exactly one pattern_type, this is a straight branch on
    that field rather than a multi-pattern merge -- case["transactions"]
    is already exactly the cycle's hops, or exactly the fan cluster's
    transfers, with nothing else mixed in.

    Args:
        case: A case dict as returned by group_into_cases.

    Returns:
        A plain-language evidence string. If the case was capped by
        group_into_cases (case["truncation_note"] set), that's appended
        as a parenthetical.
    """
    def fmt_span(hours: float) -> str:
        if hours < 1:
            return f"{hours * 60:.0f} minutes"
        return f"{hours:.1f} hours"

    case_txs = case["transactions"].sort_values("Timestamp")
    span_hours = case["time_span"] / pd.Timedelta(hours=1)

    if case["pattern_type"] == "cycle":
        account_count = len(case["accounts"])
        first_amount = float(case_txs["Amount Paid"].iloc[0])
        last_amount = float(case_txs["Amount Paid"].iloc[-1])
        retention_pct = 100.0 * last_amount / first_amount if first_amount else 0.0
        text = (
            f"${first_amount:,.2f} entered a closed {account_count}-account cycle and returned to "
            f"the originating account within {fmt_span(span_hours)}, retaining {retention_pct:.0f}% "
            f"of its original value across {len(case_txs)} hops."
        )
    else:
        total_amount = float(case_txs["Amount Paid"].sum())
        hub_account, hub_out, hub_in = _hub_account_degrees(case_txs)
        if hub_out >= hub_in:
            text = (
                f"${total_amount:,.2f} total was scattered from account {hub_account} out to "
                f"{hub_out} distinct accounts within {fmt_span(span_hours)}."
            )
        else:
            text = (
                f"${total_amount:,.2f} total was gathered into account {hub_account} from "
                f"{hub_in} distinct accounts within {fmt_span(span_hours)}."
            )

    if case.get("truncation_note"):
        text += f" ({case['truncation_note']}.)"

    return text


def case_to_api_detail(
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
    # PMLA/FIU-IND requires filing within 7 working days. The dataset is
    # historical (Sept 2022), so the deadline is relative to real wall-clock
    # time (when the pipeline runs), not any timestamp from the dataset --
    # otherwise every str_ready case's deadline would already be in the past.
    str_deadline = _add_working_days(datetime.now(timezone.utc), 7).replace(tzinfo=None).isoformat() + "Z"

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
    from pathlib import Path

    from ml.labels import build_ground_truth
    from ml.preprocessing import load_patterns, load_transactions, time_based_split

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_dir = Path(__file__).resolve().parent / "data"
    transactions = load_transactions(str(data_dir / "HI-Small_Trans.csv"))
    patterns = load_patterns(str(data_dir / "HI-Small_Patterns.txt"))
    labeled = build_ground_truth(patterns, transactions)
    _, _, test_df = time_based_split(labeled)

    features = test_df.drop(columns=["is_laundering", "pattern_type"])
    cases = group_into_cases(features, None)

    scored_cases = []
    for case in cases:
        sub_scores = compute_sub_scores(case)
        risk_score = compute_risk_score(sub_scores)
        risk_tier = assign_risk_tier(risk_score)
        evidence_text = generate_evidence_text(case)
        scored_cases.append((case, sub_scores, risk_score, risk_tier, evidence_text))

    node_counts = pd.Series([len(c["accounts"]) for c, _, _, _, _ in scored_cases])
    risk_scores = pd.Series([rs for _, _, rs, _, _ in scored_cases])
    tier_counts = pd.Series([rt for _, _, _, rt, _ in scored_cases]).value_counts()
    over_cap = int((node_counts > MAX_CASE_NODES).sum())

    print(f"\n=== Case scoring summary -- test split ===")
    print(f"total cases: {len(scored_cases):,}")

    print(f"\nnode-count distribution (cap={MAX_CASE_NODES}):")
    print(f"  min={node_counts.min()}  median={node_counts.median():.0f}  max={node_counts.max()}")
    print(f"  cases exceeding {MAX_CASE_NODES} nodes: {over_cap}")

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
    truncated = [e for e in scored_cases if e[0].get("truncation_note")]
    if truncated:
        examples.append(truncated[0])
    else:
        cycle_examples = [e for e in scored_cases if e[0]["pattern_type"] == "cycle" and e not in examples]
        if cycle_examples:
            examples.append(cycle_examples[0])

    for case, sub_scores, risk_score, risk_tier, evidence_text in examples[:4]:
        detail = case_to_api_detail(case, sub_scores, risk_score, risk_tier, evidence_text)
        note = f", {case['truncation_note']}" if case.get("truncation_note") else ""
        print(
            f"\n--- {detail['case_id']} ({risk_tier}, pattern_type={case['pattern_type']}, "
            f"nodes={len(case['accounts'])}{note}) ---"
        )
        print(json.dumps(detail, indent=2))
