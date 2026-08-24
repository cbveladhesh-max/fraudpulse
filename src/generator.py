"""Synthetic Transaction Generator for FraudPulse.

Generates realistic payment transaction data with labeled fraud patterns
and explicit stealth cases.
"""

from datetime import datetime, timedelta, timezone
import random
import numpy as np
import pandas as pd


def generate_synthetic_transactions(
    seed: int = 42,
    num_users: int = 20,
    num_tx: int = 150,
) -> pd.DataFrame:
    """Generates synthetic transaction dataset with labeled fraud patterns.

    Ground truth fields included:
    - is_fraud: True for fraudulent transactions, False for legitimate.
    - fraud_type: Categorical string explaining the pattern.
    - is_stealth: True for pre-generated stealth cases designed to bypass single-tx rules.

    NOTE: This generator intentionally does NOT include or simulate an `is_flagged` column.
    Rule engine execution and flagging is handled exclusively in Step 2.
    """
    random.seed(seed)
    np.random.seed(seed)

    cities = ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Chennai", "Pune"]
    categories = ["electronics", "groceries", "retail", "travel", "dining", "digital_goods"]

    base_time = datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Generate User Profiles
    user_profiles = {}
    for i in range(1, num_users + 1):
        user_id = f"usr_{100 + i}"
        home_city = cities[(i - 1) % len(cities)]
        mean_amount = round(float(random.randint(300, 1500)), 2)
        std_amount = round(mean_amount * 0.2, 2)
        primary_device = f"dev_{user_id}"
        primary_ip = f"103.21.{100 + i}.10"
        primary_address = f"{i * 12} MG Road, {home_city}"

        user_profiles[user_id] = {
            "home_city": home_city,
            "mean_amount": mean_amount,
            "std_amount": std_amount,
            "primary_device": primary_device,
            "primary_ip": primary_ip,
            "primary_address": primary_address,
            "known_devices": {primary_device},
            "disputes": 0,
        }

    records = []
    tx_counter = 1000

    # Helper to format transaction
    def create_tx(
        user_id: str,
        dt: datetime,
        amount: float,
        merchant_cat: str,
        device_id: str,
        ip_addr: str,
        shipping_addr: str,
        city: str,
        is_fraud: bool,
        fraud_type: str,
        is_stealth: bool = False,
    ) -> dict:
        nonlocal tx_counter
        tx_counter += 1
        return {
            "transaction_id": f"tx_{tx_counter}",
            "user_id": user_id,
            "timestamp": dt.isoformat(),
            "amount": round(float(amount), 2),
            "currency": "INR",
            "merchant_category": merchant_cat,
            "device_id": device_id,
            "ip_address": ip_addr,
            "shipping_address": shipping_addr,
            "city": city,
            "is_fraud": is_fraud,
            "fraud_type": fraud_type,
            "is_stealth": is_stealth,
        }

    # 2. Generate Legitimate Normal Transactions spread over past 5 days
    for user_id, profile in user_profiles.items():
        # Generate 5-7 normal transactions per user
        num_user_tx = random.randint(5, 7)
        for j in range(num_user_tx):
            hours_offset = random.randint(12, 120)
            minutes_offset = random.randint(0, 59)
            dt = base_time - timedelta(hours=hours_offset, minutes=minutes_offset)
            amount = max(50.0, np.random.normal(profile["mean_amount"], profile["std_amount"]))
            cat = random.choice(categories)

            records.append(
                create_tx(
                    user_id=user_id,
                    dt=dt,
                    amount=amount,
                    merchant_cat=cat,
                    device_id=profile["primary_device"],
                    ip_addr=profile["primary_ip"],
                    shipping_addr=profile["primary_address"],
                    city=profile["home_city"],
                    is_fraud=False,
                    fraud_type="none",
                    is_stealth=False,
                )
            )

    # 3. Add Explicit Labeled Rule-Catchable Fraud Transactions
    # 3a. Amount Anomaly (User usr_101)
    usr1 = "usr_101"
    prof1 = user_profiles[usr1]
    dt_anomaly = base_time - timedelta(hours=6)
    # INR 45,000 vs usr_101 mean of ~INR 500
    records.append(
        create_tx(
            user_id=usr1,
            dt=dt_anomaly,
            amount=45000.00,
            merchant_cat="electronics",
            device_id=prof1["primary_device"],
            ip_addr=prof1["primary_ip"],
            shipping_addr=prof1["primary_address"],
            city=prof1["home_city"],
            is_fraud=True,
            fraud_type="amount_anomaly",
            is_stealth=False,
        )
    )

    # 3b. Velocity Spike (User usr_103)
    usr3 = "usr_103"
    prof3 = user_profiles[usr3]
    dt_vel_base = base_time - timedelta(hours=4)
    for v in range(4):
        records.append(
            create_tx(
                user_id=usr3,
                dt=dt_vel_base + timedelta(minutes=v * 2),
                amount=prof3["mean_amount"],
                merchant_cat="digital_goods",
                device_id=prof3["primary_device"],
                ip_addr=prof3["primary_ip"],
                shipping_addr=prof3["primary_address"],
                city=prof3["home_city"],
                is_fraud=True,
                fraud_type="velocity_spike",
                is_stealth=False,
            )
        )

    # 3c. New Device + City Combo (User usr_104)
    usr4 = "usr_104"
    prof4 = user_profiles[usr4]
    dt_dev_loc = base_time - timedelta(hours=3)
    records.append(
        create_tx(
            user_id=usr4,
            dt=dt_dev_loc,
            amount=prof4["mean_amount"] * 1.1,
            merchant_cat="travel",
            device_id="dev_unknown_hacker_99",
            ip_addr="198.51.100.77",
            shipping_addr="99 Unknown St, Kolkata",
            city="Kolkata",  # Home city is Pune/Delhi
            is_fraud=True,
            fraud_type="new_device_location",
            is_stealth=False,
        )
    )

    # 4. Add 3 Pre-Generated Stealth Fraud Cases
    # Stealth Case 1: Cross-account Device Sharing (User usr_105)
    # usr_105 has clean history. Makes transaction of normal amount, in home city, single tx.
    # BUT shares device `dev_shared_stealth_ring` with fraudulent User usr_102!
    usr5 = "usr_105"
    prof5 = user_profiles[usr5]
    shared_device = "dev_shared_stealth_ring"

    # Seed a prior fraud transaction for usr_102 with this device
    records.append(
        create_tx(
            user_id="usr_102",
            dt=base_time - timedelta(hours=24),
            amount=25000.00,
            merchant_cat="electronics",
            device_id=shared_device,
            ip_addr="103.21.102.10",
            shipping_addr=user_profiles["usr_102"]["primary_address"],
            city=user_profiles["usr_102"]["home_city"],
            is_fraud=True,
            fraud_type="amount_anomaly",
            is_stealth=False,
        )
    )
    # Register this shared device in usr_105's profile so it is NOT considered a "new device" for usr_105
    prof5["known_devices"].add(shared_device)

    dt_stealth1 = base_time - timedelta(hours=2)
    records.append(
        create_tx(
            user_id=usr5,
            dt=dt_stealth1,
            amount=prof5["mean_amount"],  # Genuine normal amount for usr_105
            merchant_cat="retail",
            device_id=shared_device,  # Device shared with fraudulent usr_102
            ip_addr=prof5["primary_ip"],
            shipping_addr=prof5["primary_address"],
            city=prof5["home_city"],  # Home city (Bengaluru)
            is_fraud=True,
            fraud_type="stealth_shared_device",
            is_stealth=True,
        )
    )

    # Stealth Case 2: Cross-account IP / Address Ring (User usr_108)
    # usr_108 places a completely normal transaction in home city with known device.
    # BUT shares IP `103.50.111.99` and shipping address with multiple newly flagged accounts.
    usr8 = "usr_108"
    prof8 = user_profiles[usr8]
    stealth_ip = "103.50.111.99"
    stealth_address = "Flat 404, Fraud Syndicate Plaza, Mumbai"

    # Seed transactions from suspicious linked account usr_115 with same IP/Address
    records.append(
        create_tx(
            user_id="usr_115",
            dt=base_time - timedelta(hours=10),
            amount=18000.00,
            merchant_cat="electronics",
            device_id="dev_usr_115",
            ip_addr=stealth_ip,
            shipping_addr=stealth_address,
            city="Mumbai",
            is_fraud=True,
            fraud_type="amount_anomaly",
            is_stealth=False,
        )
    )

    dt_stealth2 = base_time - timedelta(hours=1)
    records.append(
        create_tx(
            user_id=usr8,
            dt=dt_stealth2,
            amount=prof8["mean_amount"],  # Normal amount
            merchant_cat="groceries",
            device_id=prof8["primary_device"],  # Known primary device
            ip_addr=stealth_ip,  # Shared IP ring
            shipping_addr=stealth_address,
            city=prof8["home_city"],  # Home city
            is_fraud=True,
            fraud_type="stealth_shared_ip",
            is_stealth=True,
        )
    )

    # Stealth Case 3: Prior Dispute History (User usr_112)
    # usr_112 has prior chargeback disputes recorded on past transactions, but current transaction
    # has normal amount, primary device, home city, normal velocity.
    usr12 = "usr_112"
    prof12 = user_profiles[usr12]
    # Add a past disputed transaction in usr_112's history
    records.append(
        create_tx(
            user_id=usr12,
            dt=base_time - timedelta(days=3),
            amount=prof12["mean_amount"] * 0.9,
            merchant_cat="digital_goods",
            device_id=prof12["primary_device"],
            ip_addr=prof12["primary_ip"],
            shipping_addr=prof12["primary_address"],
            city=prof12["home_city"],
            is_fraud=True,
            fraud_type="historical_dispute",
            is_stealth=False,
        )
    )

    dt_stealth3 = base_time - timedelta(minutes=30)
    records.append(
        create_tx(
            user_id=usr12,
            dt=dt_stealth3,
            amount=prof12["mean_amount"],  # Genuine normal amount
            merchant_cat="dining",
            device_id=prof12["primary_device"],  # Known device
            ip_addr=prof12["primary_ip"],
            shipping_addr=prof12["primary_address"],
            city=prof12["home_city"],  # Home city
            is_fraud=True,
            fraud_type="stealth_prior_dispute",
            is_stealth=True,
        )
    )

    df = pd.DataFrame(records)
    # Sort chronologically by timestamp
    df = df.sort_values(by="timestamp").reset_index(drop=True)
    return df


if __name__ == "__main__":
    df_data = generate_synthetic_transactions()
    print(f"Generated {len(df_data)} synthetic transactions.")
    print("Fraud distribution:")
    print(df_data["fraud_type"].value_counts())
