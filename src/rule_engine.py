"""Deterministic Rule Engine for FraudPulse.

Evaluates payment transactions against historical transaction data
using exact pure-Python rules.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List
import pandas as pd


class RuleEngine:
    """Pure-Python deterministic rule engine for fraud flagging."""

    RULE_AMOUNT_ANOMALY = "RULE_AMOUNT_ANOMALY"
    RULE_VELOCITY_SPIKE = "RULE_VELOCITY_SPIKE"
    RULE_NEW_DEVICE_LOCATION = "RULE_NEW_DEVICE_LOCATION"

    @classmethod
    def evaluate_transaction(
        cls,
        tx: Dict[str, Any],
        history_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """Evaluates a single transaction against prior history.

        Exact Thresholds:
        - RULE_AMOUNT_ANOMALY: amount > 3.0 * user historical mean amount.
        - RULE_VELOCITY_SPIKE: > 2 transactions from same user in trailing 10 minutes.
        - RULE_NEW_DEVICE_LOCATION: unrecognized device AND unfamiliar city.

        Args:
            tx: Dict representing the target transaction.
            history_df: DataFrame containing prior transactions up to (excluding) target transaction timestamp.

        Returns:
            Dict containing `rules_fired` (List[str]), `is_flagged` (bool), and `risk_score` (float).
        """
        user_id = tx["user_id"]
        tx_dt = pd.to_datetime(tx["timestamp"], format="ISO8601")

        if len(history_df) > 0:
            hist_dts = pd.to_datetime(history_df["timestamp"], format="ISO8601")
            user_history = history_df[
                (history_df["user_id"] == user_id) & (hist_dts < tx_dt)
            ]
        else:
            user_history = pd.DataFrame()

        rules_fired: List[str] = []

        # 1. Amount Anomaly: amount > 3.0 * user historical mean
        if len(user_history) > 0:
            hist_mean = float(user_history["amount"].mean())
            if tx["amount"] > 3.0 * hist_mean:
                rules_fired.append(cls.RULE_AMOUNT_ANOMALY)

        # 2. Velocity Spike: > 2 transactions from same user in trailing 10 minutes
        if len(user_history) > 0:
            window_start = tx_dt - timedelta(minutes=10)
            user_hist_dts = hist_dts[
                (history_df["user_id"] == user_id) & (hist_dts < tx_dt)
            ]
            recent_tx = user_history[user_hist_dts >= window_start]
            if len(recent_tx) + 1 > 2:
                rules_fired.append(cls.RULE_VELOCITY_SPIKE)

        # 3. New Device + Location Combo: unrecognized device AND unfamiliar city
        if len(user_history) > 0:
            known_devices = set(user_history["device_id"])
            cities_mode = user_history["city"].mode()
            primary_city = (
                cities_mode.iloc[0] if len(cities_mode) > 0 else user_history["city"].iloc[0]
            )

            if tx["device_id"] not in known_devices and tx["city"] != primary_city:
                rules_fired.append(cls.RULE_NEW_DEVICE_LOCATION)

        is_flagged = len(rules_fired) > 0

        # Deterministic weighted additive risk score calculation:
        # Base score 0.0 + fixed weight per triggered rule, capped at 1.0.
        rule_weights = {
            cls.RULE_AMOUNT_ANOMALY: 0.40,
            cls.RULE_VELOCITY_SPIKE: 0.35,
            cls.RULE_NEW_DEVICE_LOCATION: 0.35,
        }

        raw_score = sum(rule_weights.get(r, 0.0) for r in rules_fired)
        risk_score = round(min(1.0, raw_score), 2)

        return {
            "rules_fired": rules_fired,
            "is_flagged": is_flagged,
            "risk_score": risk_score,
        }

    @classmethod
    def evaluate_dataset(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Evaluates a full transaction DataFrame in chronological order.

        Adds `is_flagged`, `rules_fired`, and `risk_score` columns to the DataFrame.
        """
        df_sorted = df.copy()
        df_sorted["dt"] = pd.to_datetime(df_sorted["timestamp"], format="ISO8601")
        df_sorted = df_sorted.sort_values(by="dt").reset_index(drop=True)

        is_flagged_list = []
        rules_fired_list = []
        risk_score_list = []

        for idx, row in df_sorted.iterrows():
            history_df = df_sorted.iloc[:idx]
            res = cls.evaluate_transaction(row.to_dict(), history_df)

            is_flagged_list.append(res["is_flagged"])
            rules_fired_list.append(res["rules_fired"])
            risk_score_list.append(res["risk_score"])

        df_sorted["is_flagged"] = is_flagged_list
        df_sorted["rules_fired"] = rules_fired_list
        df_sorted["risk_score"] = risk_score_list
        df_sorted = df_sorted.drop(columns=["dt"])

        return df_sorted
