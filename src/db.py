"""SQLite Database & Audit Storage Layer for FraudPulse.

Persists raw transactions, rule engine outputs, LLM investigation trails,
and analyst decisions.
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional
import pandas as pd

DB_PATH = "fraudpulse.db"


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Returns sqlite3 connection with Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Initializes SQLite tables for transactions and alerts."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Transactions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                merchant_category TEXT,
                device_id TEXT,
                ip_address TEXT,
                shipping_address TEXT,
                city TEXT,
                is_fraud BOOLEAN,
                fraud_type TEXT,
                is_stealth BOOLEAN
            )
            """
        )

        # Alerts & Audit log table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                city TEXT,
                device_id TEXT,
                ip_address TEXT,
                shipping_address TEXT,
                risk_score REAL NOT NULL,
                rules_fired TEXT NOT NULL,
                is_flagged BOOLEAN NOT NULL,
                recommended_action TEXT NOT NULL,
                confidence TEXT NOT NULL,
                top_signals TEXT NOT NULL,
                explanation TEXT NOT NULL,
                is_fallback BOOLEAN NOT NULL,
                raw_prompt TEXT,
                raw_response TEXT,
                analyst_decision TEXT DEFAULT 'PENDING',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id)
            )
            """
        )

        conn.commit()


def save_transaction(tx: Dict[str, Any], db_path: str = DB_PATH) -> None:
    """Inserts a single transaction record into the database."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO transactions (
                transaction_id, user_id, timestamp, amount, currency,
                merchant_category, device_id, ip_address, shipping_address,
                city, is_fraud, fraud_type, is_stealth
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx["transaction_id"],
                tx["user_id"],
                tx["timestamp"],
                float(tx["amount"]),
                tx.get("currency", "INR"),
                tx.get("merchant_category", "retail"),
                tx.get("device_id", ""),
                tx.get("ip_address", ""),
                tx.get("shipping_address", ""),
                tx.get("city", ""),
                bool(tx.get("is_fraud", False)),
                tx.get("fraud_type", "none"),
                bool(tx.get("is_stealth", False)),
            ),
        )
        conn.commit()


def save_alert(alert_dict: Dict[str, Any], db_path: str = DB_PATH) -> None:
    """Inserts an alert record with full audit trail into database."""
    rules_fired_str = (
        json.dumps(alert_dict.get("rules_fired", []))
        if isinstance(alert_dict.get("rules_fired"), list)
        else alert_dict.get("rules_fired", "[]")
    )
    top_signals_str = (
        json.dumps(alert_dict.get("top_signals", []))
        if isinstance(alert_dict.get("top_signals"), list)
        else alert_dict.get("top_signals", "[]")
    )

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO alerts (
                alert_id, transaction_id, user_id, timestamp, amount, currency,
                city, device_id, ip_address, shipping_address, risk_score,
                rules_fired, is_flagged, recommended_action, confidence,
                top_signals, explanation, is_fallback, raw_prompt, raw_response,
                analyst_decision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_dict["alert_id"],
                alert_dict["transaction_id"],
                alert_dict["user_id"],
                alert_dict["timestamp"],
                float(alert_dict["amount"]),
                alert_dict.get("currency", "INR"),
                alert_dict.get("city", ""),
                alert_dict.get("device_id", ""),
                alert_dict.get("ip_address", ""),
                alert_dict.get("shipping_address", ""),
                float(alert_dict["risk_score"]),
                rules_fired_str,
                bool(alert_dict["is_flagged"]),
                alert_dict["recommended_action"],
                alert_dict["confidence"],
                top_signals_str,
                alert_dict["explanation"],
                bool(alert_dict["is_fallback"]),
                alert_dict.get("raw_prompt", ""),
                alert_dict.get("raw_response", ""),
                alert_dict.get("analyst_decision", "PENDING"),
            ),
        )
        conn.commit()


def get_all_alerts(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Returns list of all alert records from database."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM alerts ORDER BY timestamp DESC
            """
        )
        rows = cursor.fetchall()

    alerts = []
    for row in rows:
        d = dict(row)
        d["rules_fired"] = json.loads(d["rules_fired"]) if d["rules_fired"] else []
        d["top_signals"] = json.loads(d["top_signals"]) if d["top_signals"] else []
        alerts.append(d)

    return alerts


def update_analyst_decision(
    alert_id: str, decision: str, db_path: str = DB_PATH
) -> Optional[Dict[str, Any]]:
    """Updates analyst decision for an alert and returns updated record."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE alerts SET analyst_decision = ? WHERE alert_id = ?
            """,
            (decision, alert_id),
        )
        conn.commit()

        cursor.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,))
        row = cursor.fetchone()

    if not row:
        return None

    d = dict(row)
    d["rules_fired"] = json.loads(d["rules_fired"]) if d["rules_fired"] else []
    d["top_signals"] = json.loads(d["top_signals"]) if d["top_signals"] else []
    return d


def calculate_session_stats(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Calculates live agreement rate stat between LLM recommendation and analyst decision."""
    alerts = get_all_alerts(db_path)
    decided_alerts = [a for a in alerts if a["analyst_decision"] in ("MARK_FRAUD", "MARK_OK")]

    total_decisions = len(decided_alerts)
    if total_decisions == 0:
        return {
            "total_decisions": 0,
            "agreements": 0,
            "agreement_rate_pct": 0.0,
        }

    agreements = 0
    for a in decided_alerts:
        decision = a["analyst_decision"]
        rec_action = a["recommended_action"]

        if decision == "MARK_FRAUD" and rec_action in ("BLOCK", "MANUAL_REVIEW"):
            agreements += 1
        elif decision == "MARK_OK" and rec_action == "ALLOW":
            agreements += 1

    rate = round((agreements / total_decisions) * 100.0, 1)

    return {
        "total_decisions": total_decisions,
        "agreements": agreements,
        "agreement_rate_pct": rate,
    }


def get_all_transactions_df(db_path: str = DB_PATH) -> pd.DataFrame:
    """Loads all transactions into a pandas DataFrame."""
    with get_connection(db_path) as conn:
        df = pd.read_sql_query("SELECT * FROM transactions", conn)
    return df
