"""Preprocessing pipeline: raw transaction data -> graph-ready structures.

Source data (ml/data/, IBM AML "HI-Small" dataset):
    HI-Small_Trans.csv      raw transactions (~5.08M rows)
    HI-Small_accounts.csv   account/entity metadata
    HI-Small_Patterns.txt   labeled laundering attempts (ground truth)
"""

import logging
import pickle
import re
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd

logger = logging.getLogger(__name__)

# Raw transaction CSV header has "Account" twice (sender, receiver); we read
# it positionally and assign these unambiguous names ourselves.
TRANSACTION_COLUMNS = [
    "Timestamp",
    "From Bank",
    "From Account",
    "To Bank",
    "To Account",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
]

TRANSACTION_DTYPES = {
    "From Bank": "category",
    "From Account": "category",
    "To Bank": "category",
    "To Account": "category",
    "Amount Received": "float64",
    "Receiving Currency": "category",
    "Amount Paid": "float64",
    "Payment Currency": "category",
    "Payment Format": "category",
    "Is Laundering": "int8",
}

# Published stats for this dataset release; used only to warn on drift, not
# to validate correctness -- actual counts are always logged regardless.
EXPECTED_TRANSACTION_ROWS = 5_078_345
EXPECTED_NODE_COUNT = 515_088
EXPECTED_EDGE_COUNT = 5_078_345
_DRIFT_TOLERANCE = 0.01

PATTERN_BEGIN_RE = re.compile(r"^BEGIN LAUNDERING ATTEMPT - ([A-Z-]+)\s*:?\s*(.*)$")
PATTERN_END_RE = re.compile(r"^END LAUNDERING ATTEMPT - ([A-Z-]+)\s*$")


def _warn_on_drift(label: str, actual: int, expected: int) -> None:
    if expected == 0:
        return
    drift = abs(actual - expected) / expected
    if drift > _DRIFT_TOLERANCE:
        logger.warning(
            "%s count %d differs from expected ~%d by %.1f%% (tolerance %.0f%%)",
            label, actual, expected, drift * 100, _DRIFT_TOLERANCE * 100,
        )
    else:
        logger.info("%s count %d is within expected range (~%d)", label, actual, expected)


def load_transactions(path: str) -> pd.DataFrame:
    """Load and validate raw transaction records from HI-Small_Trans.csv.

    Reads the CSV positionally (the source header repeats "Account" for
    both sender and receiver columns, which pandas cannot disambiguate by
    name), validates for missing account ids/timestamps and duplicate
    rows, drops any offending rows, and logs the counts of everything it
    found and dropped.

    Args:
        path: Path to HI-Small_Trans.csv.

    Returns:
        A cleaned DataFrame of transactions with columns:
        Timestamp, From Bank, From Account, To Bank, To Account,
        Amount Received, Receiving Currency, Amount Paid, Payment Currency,
        Payment Format, Is Laundering.
    """
    logger.info("Loading transactions from %s", path)
    df = pd.read_csv(
        path,
        header=0,
        names=TRANSACTION_COLUMNS,
        dtype=TRANSACTION_DTYPES,
        parse_dates=["Timestamp"],
        date_format="%Y/%m/%d %H:%M",
    )

    row_count = len(df)
    logger.info("Loaded %d raw transaction rows", row_count)
    _warn_on_drift("Transaction row", row_count, EXPECTED_TRANSACTION_ROWS)

    missing_account_mask = df["From Account"].isna() | df["To Account"].isna()
    missing_account_count = int(missing_account_mask.sum())
    if missing_account_count:
        logger.warning(
            "Dropping %d rows with missing sender/receiver account id", missing_account_count
        )
        df = df[~missing_account_mask]

    missing_ts_count = int(df["Timestamp"].isna().sum())
    if missing_ts_count:
        logger.warning("Dropping %d rows with missing timestamp", missing_ts_count)
        df = df.dropna(subset=["Timestamp"])

    dup_mask = df.duplicated()
    dup_count = int(dup_mask.sum())
    if dup_count:
        logger.warning("Dropping %d duplicate transaction rows", dup_count)
        df = df[~dup_mask]

    df = df.reset_index(drop=True)
    logger.info("Transactions after validation: %d rows", len(df))
    return df


def load_accounts(path: str) -> pd.DataFrame:
    """Load and validate account/entity metadata from HI-Small_accounts.csv.

    Validates for missing account numbers and duplicate rows, drops any
    offending rows, and logs the counts of everything it found and
    dropped.

    Args:
        path: Path to HI-Small_accounts.csv.

    Returns:
        A cleaned DataFrame with columns: Bank Name, Bank ID,
        Account Number, Entity ID, Entity Name.
    """
    logger.info("Loading accounts from %s", path)
    df = pd.read_csv(path, dtype=str)

    row_count = len(df)
    logger.info("Loaded %d raw account rows", row_count)

    missing_count = int(df["Account Number"].isna().sum())
    if missing_count:
        logger.warning("Dropping %d rows with missing Account Number", missing_count)
        df = df.dropna(subset=["Account Number"])

    dup_mask = df.duplicated()
    dup_count = int(dup_mask.sum())
    if dup_count:
        logger.warning("Dropping %d duplicate account rows", dup_count)
        df = df[~dup_mask]

    df = df.reset_index(drop=True)
    logger.info("Accounts after validation: %d rows", len(df))
    return df


def load_patterns(path: str) -> pd.DataFrame:
    """Parse labeled laundering attempts from HI-Small_Patterns.txt.

    The file is a sequence of blocks:
        BEGIN LAUNDERING ATTEMPT - <TYPE>:  <description>
        <transaction row>
        ...
        END LAUNDERING ATTEMPT - <TYPE>
    where each transaction row is a raw, headerless CSV line in the same
    column order as HI-Small_Trans.csv. This is the ground-truth label
    source used by ml/evaluate.py.

    Args:
        path: Path to HI-Small_Patterns.txt.

    Returns:
        A DataFrame with one row per labeled attempt, columns:
        pattern_id, pattern_type (e.g. "CYCLE", "FAN-OUT", "SCATTER-GATHER"),
        description, num_transactions, num_accounts, accounts (list of
        account ids involved), transactions (list of dicts, each a parsed
        transaction row keyed by TRANSACTION_COLUMNS).
    """
    logger.info("Parsing labeled patterns from %s", path)
    patterns: list[dict[str, Any]] = []
    current_type: str | None = None
    current_desc: str | None = None
    current_rows: list[dict[str, str]] = []
    pattern_id = 0

    with open(path) as f:
        for line_num, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue

            begin_match = PATTERN_BEGIN_RE.match(line)
            if begin_match:
                if current_type is not None:
                    logger.warning(
                        "Line %d: new BEGIN before previous END (type=%s); discarding incomplete block",
                        line_num, current_type,
                    )
                current_type = begin_match.group(1)
                current_desc = begin_match.group(2).strip()
                current_rows = []
                continue

            end_match = PATTERN_END_RE.match(line)
            if end_match:
                if current_type is None:
                    logger.warning("Line %d: END with no matching BEGIN; ignoring", line_num)
                    continue
                if end_match.group(1) != current_type:
                    logger.warning(
                        "Line %d: END type %s does not match BEGIN type %s",
                        line_num, end_match.group(1), current_type,
                    )
                accounts = sorted({tx["From Account"] for tx in current_rows} | {tx["To Account"] for tx in current_rows})
                patterns.append({
                    "pattern_id": pattern_id,
                    "pattern_type": current_type,
                    "description": current_desc,
                    "num_transactions": len(current_rows),
                    "num_accounts": len(accounts),
                    "accounts": accounts,
                    "transactions": current_rows,
                })
                pattern_id += 1
                current_type = None
                current_desc = None
                current_rows = []
                continue

            if current_type is not None:
                fields = line.split(",")
                if len(fields) != len(TRANSACTION_COLUMNS):
                    logger.warning(
                        "Line %d: expected %d fields, got %d; skipping malformed row",
                        line_num, len(TRANSACTION_COLUMNS), len(fields),
                    )
                    continue
                current_rows.append(dict(zip(TRANSACTION_COLUMNS, fields)))
            else:
                logger.warning("Line %d: content outside any BEGIN/END block; ignoring: %r", line_num, line)

    if current_type is not None:
        logger.warning("File ended with an unterminated block (type=%s); discarding", current_type)

    result = pd.DataFrame(
        patterns,
        columns=["pattern_id", "pattern_type", "description", "num_transactions", "num_accounts", "accounts", "transactions"],
    )
    logger.info("Parsed %d labeled laundering patterns", len(result))
    if len(result):
        for pattern_type, count in result["pattern_type"].value_counts().sort_index().items():
            logger.info("  %s: %d", pattern_type, count)

    return result


def build_graph(transactions_df: pd.DataFrame) -> nx.MultiDiGraph:
    """Build a directed multigraph of accounts and transfers.

    A MultiDiGraph is used (not a simple DiGraph) because the same
    (sender, receiver) account pair frequently transacts more than once,
    and collapsing those into a single edge would lose per-transaction
    amount/timestamp/label information needed downstream.

    Args:
        transactions_df: Cleaned transaction DataFrame as returned by
            load_transactions.

    Returns:
        A networkx MultiDiGraph where nodes are account ids and each edge
        is one transaction carrying "amount", "timestamp", and
        "is_laundering" attributes.
    """
    logger.info("Building transaction graph from %d transactions", len(transactions_df))
    edge_df = transactions_df.rename(columns={
        "From Account": "source",
        "To Account": "target",
        "Amount Paid": "amount",
        "Timestamp": "timestamp",
        "Is Laundering": "is_laundering",
    })
    graph = nx.from_pandas_edgelist(
        edge_df,
        source="source",
        target="target",
        edge_attr=["amount", "timestamp", "is_laundering"],
        create_using=nx.MultiDiGraph(),
    )

    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()
    logger.info("Graph built: %d nodes, %d edges", node_count, edge_count)
    _warn_on_drift("Graph node", node_count, EXPECTED_NODE_COUNT)
    _warn_on_drift("Graph edge", edge_count, EXPECTED_EDGE_COUNT)

    return graph


def time_based_split(
    transactions_df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split transactions into train/val/test strictly by timestamp order.

    Sorts by Timestamp ascending and slices by position, so the earliest
    transactions land in train and the latest in test. This is NOT a
    random split -- shuffling would leak future transaction patterns into
    training, which is unrealistic for a fraud/AML setting where the
    model must generalize forward in time.

    Args:
        transactions_df: Cleaned transaction DataFrame as returned by
            load_transactions.
        train_frac: Fraction of rows (by position, after time-sorting) to
            assign to the train split.
        val_frac: Fraction of rows to assign to the val split. The
            remainder goes to test.

    Returns:
        (train_df, val_df, test_df), each sorted by Timestamp ascending.
    """
    if not 0 < train_frac < 1 or not 0 <= val_frac < 1 or train_frac + val_frac >= 1:
        raise ValueError(
            f"Invalid split fractions: train_frac={train_frac}, val_frac={val_frac} "
            "(require 0 < train_frac < 1, 0 <= val_frac < 1, train_frac + val_frac < 1)"
        )

    sorted_df = transactions_df.sort_values("Timestamp", kind="mergesort").reset_index(drop=True)
    n = len(sorted_df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    train_df = sorted_df.iloc[:train_end].reset_index(drop=True)
    val_df = sorted_df.iloc[train_end:val_end].reset_index(drop=True)
    test_df = sorted_df.iloc[val_end:].reset_index(drop=True)

    for name, split in (("train", train_df), ("val", val_df), ("test", test_df)):
        if len(split):
            logger.info(
                "%s split: %d rows, %s -> %s",
                name, len(split), split["Timestamp"].min(), split["Timestamp"].max(),
            )
        else:
            logger.warning("%s split is empty", name)

    return train_df, val_df, test_df


def cache_graph(graph: nx.MultiDiGraph, path: str) -> None:
    """Serialize a built graph to disk so it doesn't need to be rebuilt every run.

    Args:
        graph: Graph as returned by build_graph.
        path: Destination file path (parent directories are created if
            needed), conventionally under ml/data/processed/.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        pickle.dump(graph, f, protocol=pickle.HIGHEST_PROTOCOL)
    logger.info(
        "Cached graph (%d nodes, %d edges) to %s",
        graph.number_of_nodes(), graph.number_of_edges(), out_path,
    )


def load_cached_graph(path: str) -> nx.MultiDiGraph:
    """Deserialize a graph previously written by cache_graph.

    Args:
        path: Path to the cached graph file.

    Returns:
        The cached MultiDiGraph.
    """
    in_path = Path(path)
    with in_path.open("rb") as f:
        graph = pickle.load(f)
    logger.info(
        "Loaded cached graph (%d nodes, %d edges) from %s",
        graph.number_of_nodes(), graph.number_of_edges(), in_path,
    )
    return graph


def compute_account_features(graph: nx.MultiDiGraph) -> pd.DataFrame:
    """Compute per-account features used as detection inputs.

    Expected features include transaction velocity (transfers per unit
    time), fan-in/fan-out ratio, and other graph-derived statistics.

    Args:
        graph: Transaction graph as returned by build_graph.

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_dir = Path(__file__).resolve().parent / "data"
    trans_path = data_dir / "HI-Small_Trans.csv"
    accounts_path = data_dir / "HI-Small_accounts.csv"
    patterns_path = data_dir / "HI-Small_Patterns.txt"
    cache_path = data_dir / "processed" / "graph.pkl"

    transactions = load_transactions(str(trans_path))
    accounts = load_accounts(str(accounts_path))
    patterns = load_patterns(str(patterns_path))

    graph = build_graph(transactions)
    train_df, val_df, test_df = time_based_split(transactions)
    cache_graph(graph, str(cache_path))

    print("\n=== Pipeline summary ===")
    print(f"Transactions loaded (post-validation): {len(transactions):,}")
    print(f"Accounts loaded (post-validation):      {len(accounts):,}")
    print(f"Graph:                                  {graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges")
    print(f"Train split: {len(train_df):,} rows, {train_df['Timestamp'].min()} -> {train_df['Timestamp'].max()}")
    print(f"Val split:   {len(val_df):,} rows, {val_df['Timestamp'].min()} -> {val_df['Timestamp'].max()}")
    print(f"Test split:  {len(test_df):,} rows, {test_df['Timestamp'].min()} -> {test_df['Timestamp'].max()}")
    print(f"Labeled laundering patterns parsed: {len(patterns):,}")
    if len(patterns):
        print(patterns["pattern_type"].value_counts().sort_index().to_string())
    print(f"\nCached graph at: {cache_path}")
