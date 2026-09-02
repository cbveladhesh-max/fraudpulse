"""Feature Engineering Pipeline for FraudPulse ML Model.

Extracts statistical, behavioral, and contextual features from transactions
evaluated against historical transaction data.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

CATEGORIES = ["electronics", "groceries", "retail", "travel", "dining", "digital_goods", "digital_services", "luxury_retail"]
CATEGORY_MAP = {cat: i for i, cat in enumerate(CATEGORIES)}

FEATURE_COLUMNS = [
    "amount",
    "amount_to_mean_ratio",
    "amount_z_score",
    "velocity_10m",
    "velocity_1h",
    "is_new_device",
    "is_new_city",
    "is_new_ip",
    "hour_of_day",
    "is_weekend",
    "category_idx",
    "user_prior_disputes",
]


def extract_features(
    tx: Dict[str, Any],
    history_df: pd.DataFrame,
) -> Dict[str, float]:
    """Extracts a feature dictionary for a single transaction.

    Args:
        tx: Target transaction dictionary.
        history_df: DataFrame of historical transactions prior to this transaction.

    Returns:
        Dict mapping feature name to numeric value.
    """
    user_id = tx.get("user_id", "")
    amount = float(tx.get("amount", 0.0))
    category = tx.get("merchant_category", "retail")
    category_idx = float(CATEGORY_MAP.get(category, 0))

    try:
        tx_dt = pd.to_datetime(tx.get("timestamp", datetime.utcnow().isoformat()), format="mixed", utc=True)
    except Exception:
        tx_dt = pd.to_datetime(datetime.utcnow().isoformat(), format="mixed", utc=True)

    # User History Filter
    if len(history_df) > 0 and "timestamp" in history_df.columns:
        try:
            hist_dts = pd.to_datetime(history_df["timestamp"], format="mixed", utc=True)
            user_mask = (history_df["user_id"] == user_id) & (hist_dts < tx_dt)
            user_history = history_df[user_mask]
            user_hist_dts = hist_dts[user_mask]
        except Exception:
            user_history = pd.DataFrame()
            user_hist_dts = pd.Series(dtype="datetime64[ns, UTC]")
    else:
        user_history = pd.DataFrame()
        user_hist_dts = pd.Series(dtype="datetime64[ns, UTC]")

    # 1. Amount Features
    if len(user_history) > 0 and "amount" in user_history.columns:
        mean_amt = float(user_history["amount"].mean())
        std_amt = float(user_history["amount"].std())
        if np.isnan(std_amt) or std_amt == 0:
            std_amt = 1.0
        amount_to_mean_ratio = amount / max(mean_amt, 1.0)
        amount_z_score = (amount - mean_amt) / std_amt
    else:
        amount_to_mean_ratio = 1.0
        amount_z_score = 0.0

    # 2. Velocity Features
    if len(user_history) > 0 and len(user_hist_dts) > 0:
        win_10m = tx_dt - timedelta(minutes=10)
        win_1h = tx_dt - timedelta(hours=1)
        velocity_10m = float((user_hist_dts >= win_10m).sum())
        velocity_1h = float((user_hist_dts >= win_1h).sum())
    else:
        velocity_10m = 0.0
        velocity_1h = 0.0

    # 3. Behavioral Unfamiliarity Features
    device_id = tx.get("device_id", "")
    city = tx.get("city", "")
    ip_addr = tx.get("ip_address", "")
    ip_prefix = ".".join(ip_addr.split(".")[:3]) if ip_addr else ""

    if len(user_history) > 0:
        known_devices = set(user_history["device_id"].dropna()) if "device_id" in user_history.columns else set()
        is_new_device = 0.0 if device_id in known_devices else 1.0

        if "city" in user_history.columns:
            cities_mode = user_history["city"].mode()
            primary_city = cities_mode.iloc[0] if len(cities_mode) > 0 else user_history["city"].iloc[0]
            is_new_city = 0.0 if city == primary_city else 1.0
        else:
            is_new_city = 0.0

        if "ip_address" in user_history.columns:
            known_prefixes = {".".join(str(ip).split(".")[:3]) for ip in user_history["ip_address"].dropna()}
            is_new_ip = 0.0 if ip_prefix in known_prefixes else 1.0
        else:
            is_new_ip = 0.0

        if "is_fraud" in user_history.columns:
            user_prior_disputes = float(user_history["is_fraud"].sum())
        else:
            user_prior_disputes = 0.0
    else:
        is_new_device = 1.0
        is_new_city = 0.0
        is_new_ip = 1.0
        user_prior_disputes = 0.0

    # 4. Temporal Features
    hour_of_day = float(tx_dt.hour if hasattr(tx_dt, "hour") else 12)
    weekday = tx_dt.weekday() if hasattr(tx_dt, "weekday") else 0
    is_weekend = 1.0 if weekday >= 5 else 0.0

    return {
        "amount": round(amount, 2),
        "amount_to_mean_ratio": round(amount_to_mean_ratio, 3),
        "amount_z_score": round(amount_z_score, 3),
        "velocity_10m": velocity_10m,
        "velocity_1h": velocity_1h,
        "is_new_device": is_new_device,
        "is_new_city": is_new_city,
        "is_new_ip": is_new_ip,
        "hour_of_day": hour_of_day,
        "is_weekend": is_weekend,
        "category_idx": category_idx,
        "user_prior_disputes": user_prior_disputes,
    }


def extract_features_df(df: pd.DataFrame) -> pd.DataFrame:
    """Extracts features for an entire chronological dataset DataFrame."""
    feature_rows = []
    # Ensure chronological order
    df_sorted = df.sort_values(by="timestamp").reset_index(drop=True)
    
    for i in range(len(df_sorted)):
        current_tx = df_sorted.iloc[i].to_dict()
        history = df_sorted.iloc[:i]
        features = extract_features(current_tx, history)
        feature_rows.append(features)

    return pd.DataFrame(feature_rows)
