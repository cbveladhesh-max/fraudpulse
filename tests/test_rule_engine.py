"""Tests for Step 2 Deterministic Rule Engine.

Verifies exact rule thresholds, dataset-wide evaluation,
and asserts stealth cases remain unflagged by static rules.
"""

from datetime import datetime, timedelta, timezone
import pandas as pd
from src.generator import generate_synthetic_transactions
from src.rule_engine import RuleEngine


def test_individual_rules():
    """Unit tests for each individual rule logic."""
    base_dt = datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Historical setup for user usr_test
    history_records = [
        {
            "transaction_id": "tx_h1",
            "user_id": "usr_test",
            "timestamp": (base_dt - timedelta(hours=5)).isoformat(),
            "amount": 1000.0,
            "currency": "INR",
            "merchant_category": "retail",
            "device_id": "dev_primary",
            "ip_address": "103.21.1.10",
            "shipping_address": "100 MG Road",
            "city": "Bengaluru",
        },
        {
            "transaction_id": "tx_h2",
            "user_id": "usr_test",
            "timestamp": (base_dt - timedelta(hours=3)).isoformat(),
            "amount": 1000.0,
            "currency": "INR",
            "merchant_category": "retail",
            "device_id": "dev_primary",
            "ip_address": "103.21.1.10",
            "shipping_address": "100 MG Road",
            "city": "Bengaluru",
        },
    ]
    history_df = pd.DataFrame(history_records)

    # Test Amount Anomaly (mean = 1000, threshold = 3000)
    tx_normal_amount = {
        "user_id": "usr_test",
        "timestamp": base_dt.isoformat(),
        "amount": 2500.0,
        "device_id": "dev_primary",
        "city": "Bengaluru",
    }
    res_normal = RuleEngine.evaluate_transaction(tx_normal_amount, history_df)
    assert RuleEngine.RULE_AMOUNT_ANOMALY not in res_normal["rules_fired"]

    tx_high_amount = {
        "user_id": "usr_test",
        "timestamp": base_dt.isoformat(),
        "amount": 3500.0,
        "device_id": "dev_primary",
        "city": "Bengaluru",
    }
    res_high = RuleEngine.evaluate_transaction(tx_high_amount, history_df)
    assert RuleEngine.RULE_AMOUNT_ANOMALY in res_high["rules_fired"]
    assert res_high["is_flagged"] is True

    # Test Velocity Spike
    # Add tx at t-5m and t-2m, then current tx at t-0m -> total 3 tx in 10m window
    vel_history = history_records + [
        {
            "transaction_id": "tx_v1",
            "user_id": "usr_test",
            "timestamp": (base_dt - timedelta(minutes=5)).isoformat(),
            "amount": 1000.0,
            "currency": "INR",
            "merchant_category": "retail",
            "device_id": "dev_primary",
            "ip_address": "103.21.1.10",
            "shipping_address": "100 MG Road",
            "city": "Bengaluru",
        },
        {
            "transaction_id": "tx_v2",
            "user_id": "usr_test",
            "timestamp": (base_dt - timedelta(minutes=2)).isoformat(),
            "amount": 1000.0,
            "currency": "INR",
            "merchant_category": "retail",
            "device_id": "dev_primary",
            "ip_address": "103.21.1.10",
            "shipping_address": "100 MG Road",
            "city": "Bengaluru",
        },
    ]
    vel_history_df = pd.DataFrame(vel_history)

    tx_vel = {
        "user_id": "usr_test",
        "timestamp": base_dt.isoformat(),
        "amount": 1000.0,
        "device_id": "dev_primary",
        "city": "Bengaluru",
    }
    res_vel = RuleEngine.evaluate_transaction(tx_vel, vel_history_df)
    assert RuleEngine.RULE_VELOCITY_SPIKE in res_vel["rules_fired"]

    # Test New Device + City Combo
    tx_new_dev_city = {
        "user_id": "usr_test",
        "timestamp": base_dt.isoformat(),
        "amount": 1000.0,
        "device_id": "dev_hacker_unknown",
        "city": "Kolkata",  # Primary city is Bengaluru
    }
    res_dev_loc = RuleEngine.evaluate_transaction(tx_new_dev_city, history_df)
    assert RuleEngine.RULE_NEW_DEVICE_LOCATION in res_dev_loc["rules_fired"]


def test_full_dataset_evaluation():
    """Tests RuleEngine.evaluate_dataset on generated synthetic data."""
    raw_df = generate_synthetic_transactions(seed=42)
    evaluated_df = RuleEngine.evaluate_dataset(raw_df)

    # Check new columns present
    for col in ["is_flagged", "rules_fired", "risk_score"]:
        assert col in evaluated_df.columns

    # Stealth cases MUST NOT be flagged by rule engine
    stealth_rows = evaluated_df[evaluated_df["is_stealth"] == True]
    assert len(stealth_rows) == 3

    for _, s_row in stealth_rows.iterrows():
        tx_id = s_row["transaction_id"]
        fraud_type = s_row["fraud_type"]
        is_flagged = s_row["is_flagged"]
        rules = s_row["rules_fired"]

        print(f"Stealth [{tx_id}] ({fraud_type}): is_flagged={is_flagged}, rules={rules}")
        assert is_flagged is False, f"Stealth case {tx_id} must NOT be flagged by rule engine!"
        assert len(rules) == 0, f"Stealth case {tx_id} must have empty rules_fired list!"

    # Explicit rule-catchable fraud MUST be flagged
    anomaly_rows = evaluated_df[evaluated_df["fraud_type"] == "amount_anomaly"]
    for _, a_row in anomaly_rows.iterrows():
        assert a_row["is_flagged"] is True
        assert RuleEngine.RULE_AMOUNT_ANOMALY in a_row["rules_fired"]

    new_dev_rows = evaluated_df[evaluated_df["fraud_type"] == "new_device_location"]
    for _, n_row in new_dev_rows.iterrows():
        assert n_row["is_flagged"] is True
        assert RuleEngine.RULE_NEW_DEVICE_LOCATION in n_row["rules_fired"]

    print("\n--- STEP 2 RULE ENGINE TEST SUCCESSFUL ---")
    print(f"Total Transactions Evaluated: {len(evaluated_df)}")
    print(f"Total Flagged Alerts: {len(evaluated_df[evaluated_df['is_flagged']])}")
    print(f"Unflagged Stealth Cases: {len(stealth_rows)} (All clean)")


if __name__ == "__main__":
    test_individual_rules()
    test_full_dataset_evaluation()
