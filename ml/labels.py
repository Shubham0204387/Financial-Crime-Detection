"""Ground-truth labeling: map parsed laundering patterns onto transactions.

HI-Small_Trans.csv already carries a raw "Is Laundering" flag, but it
doesn't say *which* labeled pattern (or pattern type) a positive
transaction belongs to -- that mapping only exists in HI-Small_Patterns.txt.
This module reconstructs it by matching each transaction against the
flattened transaction rows inside every parsed pattern block, so
evaluate.py can report recall broken down by pattern type.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Every field two transaction rows can be compared on (everything raw
# CSV carries except the label itself). Timestamp + this set is expected
# to be unique per transaction; the per-key occurrence counter below
# guards against the rare case where it isn't.
_MATCH_COLUMNS = [
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
]


def _flatten_pattern_transactions(patterns: pd.DataFrame) -> pd.DataFrame:
    """Explode patterns' nested transaction lists into one row per transaction."""
    records = []
    for pattern_id, pattern_type, txs in zip(
        patterns["pattern_id"], patterns["pattern_type"], patterns["transactions"]
    ):
        for tx in txs:
            record = {col: tx[col] for col in _MATCH_COLUMNS}
            record["pattern_id"] = pattern_id
            record["pattern_type"] = pattern_type
            records.append(record)

    flat = pd.DataFrame(records)
    flat["Timestamp"] = pd.to_datetime(flat["Timestamp"], format="%Y/%m/%d %H:%M")
    flat["Amount Received"] = flat["Amount Received"].astype(float).round(2)
    flat["Amount Paid"] = flat["Amount Paid"].astype(float).round(2)
    return flat


def build_ground_truth(patterns: pd.DataFrame, transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Label each transaction using the parsed pattern blocks from load_patterns.

    Matches every row in transactions_df against the flattened set of
    transactions referenced by all parsed patterns, on the full set of
    shared fields (timestamp, bank/account pair, amounts, currencies,
    payment format) plus an occurrence index within each matching key
    group, so transactions that happen to share identical field values
    are still disambiguated correctly.

    Args:
        patterns: DataFrame as returned by preprocessing.load_patterns.
        transactions_df: DataFrame as returned by preprocessing.load_transactions.

    Returns:
        A copy of transactions_df with two new columns:
        - is_laundering (bool): True if the transaction matched a
          transaction inside any parsed pattern, False otherwise.
        - pattern_type (object, nullable): the pattern type the
          transaction belongs to (e.g. "CYCLE", "STACK"), or None for
          negatives.
    """
    logger.info(
        "Building ground truth from %d parsed patterns against %d transactions",
        len(patterns), len(transactions_df),
    )

    df = transactions_df.copy()
    df["Amount Received"] = df["Amount Received"].round(2)
    df["Amount Paid"] = df["Amount Paid"].round(2)
    df["_occurrence"] = df.groupby(_MATCH_COLUMNS, observed=True).cumcount()

    flat = _flatten_pattern_transactions(patterns)
    flat["_occurrence"] = flat.groupby(_MATCH_COLUMNS).cumcount()

    deduped_flat = flat.drop_duplicates(subset=_MATCH_COLUMNS + ["_occurrence"], keep="first")
    if len(deduped_flat) != len(flat):
        logger.warning(
            "%d pattern transactions collided on identical match key + occurrence index "
            "and were dropped as unresolved duplicates before matching",
            len(flat) - len(deduped_flat),
        )

    merged = df.merge(
        deduped_flat[_MATCH_COLUMNS + ["_occurrence", "pattern_id", "pattern_type"]],
        on=_MATCH_COLUMNS + ["_occurrence"],
        how="left",
    )
    if len(merged) != len(df):
        raise RuntimeError(
            f"Ground-truth merge changed row count ({len(df)} -> {len(merged)}); "
            "match key is not unique enough on the left side"
        )

    merged["is_laundering"] = merged["pattern_id"].notna()
    merged = merged.drop(columns=["_occurrence", "pattern_id"])

    matched = int(merged["is_laundering"].sum())
    total_pattern_tx = len(flat)
    if matched != total_pattern_tx:
        logger.warning(
            "Matched %d of %d pattern transactions into the transaction set (%d unmatched -- "
            "likely rows dropped during load_transactions validation, or dataset duplicates)",
            matched, total_pattern_tx, total_pattern_tx - matched,
        )

    raw_flag_positive = int((df["Is Laundering"] == 1).sum())
    if matched != raw_flag_positive:
        logger.warning(
            "Pattern-matched positive count (%d) differs from the raw 'Is Laundering' "
            "column's positive count (%d) -- treating the pattern match as ground truth "
            "per spec, but this drift is worth investigating",
            matched, raw_flag_positive,
        )

    total = len(merged)
    pct_positive = 100 * matched / total if total else 0.0
    logger.info(
        "Ground truth class balance: %d / %d positive (%.4f%%)", matched, total, pct_positive
    )

    return merged
