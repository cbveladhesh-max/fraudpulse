"""Deterministic tools for FraudPulse Investigator Agent.

Provides user history lookup and cross-account attribute matching
using deterministic pandas queries.
"""

from typing import Any, Dict, List
import pandas as pd


def get_user_history(user_id: str, dataset_df: pd.DataFrame) -> Dict[str, Any]:
    """Queries transaction and dispute history for a given user.

    Args:
        user_id: Target user identifier (e.g. "usr_105").
        dataset_df: Transaction dataset DataFrame.

    Returns:
        Dict containing user spending stats, known devices/cities, and dispute history.
    """
    user_tx = dataset_df[dataset_df["user_id"] == user_id].copy()

    if len(user_tx) == 0:
        return {
            "user_id": user_id,
            "total_transactions": 0,
            "mean_amount": 0.0,
            "known_devices": [],
            "known_cities": [],
            "past_disputes": 0,
            "past_fraud_types": [],
        }

    dispute_count = int(
        (user_tx["fraud_type"] == "historical_dispute").sum()
        + (user_tx["fraud_type"] == "stealth_prior_dispute").sum()
    )

    past_fraud_types = [ft for ft in user_tx["fraud_type"].unique() if ft != "none"]

    return {
        "user_id": user_id,
        "total_transactions": len(user_tx),
        "mean_amount": round(float(user_tx["amount"].mean()), 2),
        "min_amount": round(float(user_tx["amount"].min()), 2),
        "max_amount": round(float(user_tx["amount"].max()), 2),
        "known_devices": sorted(user_tx["device_id"].unique().tolist()),
        "known_cities": sorted(user_tx["city"].unique().tolist()),
        "past_disputes": dispute_count,
        "past_fraud_types": past_fraud_types,
    }


def find_related_transactions(
    attribute: str,
    value: str,
    window_hours: int = 48,
    dataset_df: pd.DataFrame = None,
) -> List[Dict[str, Any]]:
    """Deterministically queries shared attributes (device_id, ip_address, shipping_address) across accounts.

    NOTE: This is a pure pandas deterministic query. The LLM agent only reads and narrates the output.

    Args:
        attribute: Attribute column name ('device_id', 'ip_address', or 'shipping_address').
        value: Target attribute value to search for.
        window_hours: Time window filter in hours (default 48).
        dataset_df: Transaction dataset DataFrame.

    Returns:
        List of matching transaction dicts across user accounts.
    """
    if dataset_df is None or dataset_df.empty:
        return []

    valid_attrs = ["device_id", "ip_address", "shipping_address"]
    if attribute not in valid_attrs:
        return []

    matches = dataset_df[dataset_df[attribute] == value].copy()

    results = []
    for _, row in matches.iterrows():
        results.append(
            {
                "transaction_id": row["transaction_id"],
                "user_id": row["user_id"],
                "timestamp": row["timestamp"],
                "amount": float(row["amount"]),
                "currency": row.get("currency", "INR"),
                "city": row["city"],
                "device_id": row["device_id"],
                "ip_address": row["ip_address"],
                "shipping_address": row["shipping_address"],
                "is_fraud": bool(row.get("is_fraud", False)),
                "fraud_type": row.get("fraud_type", "none"),
                "rules_fired": row.get("rules_fired", []),
            }
        )

    return results
