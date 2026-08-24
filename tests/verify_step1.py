"""Verification script for Step 1: Synthetic Data Generator.

Verifies schema, currency (INR), field separation (no `is_flagged`),
and asserts that pre-generated stealth cases do NOT trip planned Step 2 rules.
"""

from datetime import datetime, timedelta, timezone
import pandas as pd
from src.generator import generate_synthetic_transactions


def simulate_step2_rules(df: pd.DataFrame) -> dict:
    """Simulates planned Step 2 deterministic rule engine checks.

    Rules:
    1. AMOUNT_ANOMALY: Amount > 3x the user's historical mean amount (computed from preceding normal tx).
    2. VELOCITY_SPIKE: > 2 transactions from the same user in a 10-minute window.
    3. NEW_DEVICE_LOCATION: Device is not in user's historical devices AND City is not user's primary city.

    Returns dict mapping transaction_id -> list of rule names fired.
    """
    df = df.copy()
    df["dt"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(by="dt").reset_index(drop=True)
    fired_rules = {}

    for idx, row in df.iterrows():
        tx_id = row["transaction_id"]
        user_id = row["user_id"]
        curr_time = row["dt"]

        # Historical transactions for this user prior to current transaction
        past_tx = df[(df["user_id"] == user_id) & (df["dt"] < curr_time)]

        rules_triggered = []

        # Rule 1: Amount Anomaly
        if len(past_tx) > 0:
            hist_mean = past_tx["amount"].mean()
            if row["amount"] > 3.0 * hist_mean:
                rules_triggered.append("RULE_AMOUNT_ANOMALY")

        # Rule 2: Velocity Spike (> 2 transactions in last 10 minutes)
        window_start = curr_time - timedelta(minutes=10)
        recent_tx = past_tx[past_tx["dt"] >= window_start]
        if len(recent_tx) + 1 > 2:  # current tx makes it > 2
            rules_triggered.append("RULE_VELOCITY_SPIKE")

        # Rule 3: New Device + City Combo
        if len(past_tx) > 0:
            known_devices = set(past_tx["device_id"])
            primary_city = past_tx["city"].mode()[0] if len(past_tx["city"].mode()) > 0 else past_tx["city"].iloc[0]

            if row["device_id"] not in known_devices and row["city"] != primary_city:
                rules_triggered.append("RULE_NEW_DEVICE_LOCATION")

        fired_rules[tx_id] = rules_triggered

    return fired_rules


def test_step1_verification():
    """Runs rigorous validation on Step 1 synthetic dataset."""
    df = generate_synthetic_transactions(seed=42)

    # 1. Required Schema Columns
    expected_cols = [
        "transaction_id",
        "user_id",
        "timestamp",
        "amount",
        "currency",
        "merchant_category",
        "device_id",
        "ip_address",
        "shipping_address",
        "city",
        "is_fraud",
        "fraud_type",
        "is_stealth",
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing required column: {col}"

    # 2. Field Separation Assertion (Requirement #2)
    assert (
        "is_flagged" not in df.columns
    ), "CRITICAL: Generator output must NOT contain `is_flagged`. Rule flagging belongs exclusively to Step 2."

    # 3. Currency Assertion (Requirement #3)
    assert (df["currency"] == "INR").all(), "All transaction currencies must default to INR."

    # 4. Stealth Cases Presence Check
    stealth_df = df[df["is_stealth"] == True]
    assert len(stealth_df) == 3, f"Expected 3 stealth cases, found {len(stealth_df)}"
    assert (stealth_df["is_fraud"] == True).all(), "All stealth cases must have ground-truth `is_fraud=True`"

    # 5. Critical Stealth Rule Non-Flagging Assertion (Requirement #4 & #5)
    simulated_flags = simulate_step2_rules(df)

    for _, stealth_row in stealth_df.iterrows():
        tx_id = stealth_row["transaction_id"]
        stealth_type = stealth_row["fraud_type"]
        triggered = simulated_flags[tx_id]

        print(
            f"Stealth Tx [{tx_id}] (Type: {stealth_type}): Amount={stealth_row['amount']} INR, "
            f"City={stealth_row['city']}, Rules Triggered={triggered}"
        )

        assert (
            len(triggered) == 0
        ), f"CRITICAL FAILURE: Stealth transaction {tx_id} of type '{stealth_type}' was flagged by static rules {triggered}! Stealth cases must NOT trip single-transaction rules."

    # 6. Verify that obvious non-stealth fraud patterns ARE detected by candidate rules
    amount_anomaly_tx = df[df["fraud_type"] == "amount_anomaly"]["transaction_id"].tolist()
    for tx_id in amount_anomaly_tx:
        assert (
            "RULE_AMOUNT_ANOMALY" in simulated_flags[tx_id]
        ), f"Expected RULE_AMOUNT_ANOMALY for {tx_id}"

    velocity_spike_tx = df[df["fraud_type"] == "velocity_spike"]["transaction_id"].tolist()
    triggered_vel = [tx_id for tx_id in velocity_spike_tx if "RULE_VELOCITY_SPIKE" in simulated_flags[tx_id]]
    assert (
        len(triggered_vel) > 0
    ), f"Expected RULE_VELOCITY_SPIKE to trigger for velocity spike sequence {velocity_spike_tx}"

    new_dev_tx = df[df["fraud_type"] == "new_device_location"]["transaction_id"].tolist()
    for tx_id in new_dev_tx:
        assert (
            "RULE_NEW_DEVICE_LOCATION" in simulated_flags[tx_id]
        ), f"Expected RULE_NEW_DEVICE_LOCATION for {tx_id}"

    print("\n--- STEP 1 VERIFICATION SUCCESSFUL ---")
    print(f"Total Transactions: {len(df)}")
    print(f"Legitimate Transactions: {len(df[~df['is_fraud']])}")
    print(f"Explicit Fraud Transactions: {len(df[df['is_fraud'] & ~df['is_stealth']])}")
    print(f"Stealth Fraud Transactions: {len(stealth_df)}")
    print("All stealth non-flagging assertions passed cleanly.")


if __name__ == "__main__":
    test_step1_verification()
