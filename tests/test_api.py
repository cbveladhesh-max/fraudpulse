"""Tests for Step 4 FastAPI endpoints and SQLite audit storage.

Verifies POST /events, GET /alerts, and POST /alerts/{id}/decision endpoints
using FastAPI TestClient.
"""

from datetime import datetime, timezone
import os
from fastapi.testclient import TestClient
from src.db import init_db
from src.main import app

# Use temporary test database for API testing
TEST_DB_PATH = "test_fraudpulse.db"
os.environ["DATABASE_PATH"] = TEST_DB_PATH

client = TestClient(app)


def test_api_endpoints():
    """Tests the full API workflow: POST /events -> GET /alerts -> POST /alerts/{id}/decision."""
    init_db(TEST_DB_PATH)

    with TestClient(app) as client:
        # 1. Test POST /events (Ingest a new transaction event)
        sample_tx = {
            "transaction_id": "tx_api_test_101",
            "user_id": "usr_101",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "amount": 45000.0,  # High amount anomaly
            "currency": "INR",
            "merchant_category": "electronics",
            "device_id": "dev_usr_101",
            "ip_address": "103.21.101.10",
            "shipping_address": "101 MG Road, Bengaluru",
            "city": "Bengaluru",
            "is_fraud": True,
            "fraud_type": "amount_anomaly",
            "is_stealth": False,
        }

        response = client.post("/events", json=sample_tx)
        assert response.status_code == 200, f"POST /events failed: {response.text}"

        data = response.json()
        assert data["transaction_id"] == "tx_api_test_101"
        assert "RULE_AMOUNT_ANOMALY" in data["rule_engine"]["rules_fired"]
        assert data["investigation"]["risk_score"] == 0.40
        assert "recommended_action" in data["investigation"]

        # 2. Test GET /alerts
        get_resp = client.get("/alerts")
        assert get_resp.status_code == 200
        alerts = get_resp.json()
        assert len(alerts) >= 1

        target_alert = None
        for a in alerts:
            if a["transaction_id"] == "tx_api_test_101":
                target_alert = a
                break

        assert target_alert is not None, "Target alert not found in GET /alerts"
        assert target_alert["analyst_decision"] == "PENDING"
        assert "explanation" in target_alert
        assert "raw_prompt" in target_alert

        # 3. Test POST /alerts/{alert_id}/decision
        alert_id = target_alert["alert_id"]
        decision_payload = {"decision": "MARK_FRAUD"}

        dec_resp = client.post(f"/alerts/{alert_id}/decision", json=decision_payload)
        assert dec_resp.status_code == 200, f"POST decision failed: {dec_resp.text}"

        dec_data = dec_resp.json()
        assert dec_data["alert"]["analyst_decision"] == "MARK_FRAUD"
        assert "session_stats" in dec_data
        stats = dec_data["session_stats"]
        assert stats["total_decisions"] >= 1
        assert "agreement_rate_pct" in stats

    print("\n--- STEP 4 FASTAPI ENDPOINTS TEST SUCCESSFUL ---")
    print(f"Ingested Transaction: {data['transaction_id']}")
    print(f"Alert ID Created: {alert_id}")
    print(f"Analyst Decision Set: MARK_FRAUD")
    print(f"Session Stats: {stats}")


if __name__ == "__main__":
    test_api_endpoints()
