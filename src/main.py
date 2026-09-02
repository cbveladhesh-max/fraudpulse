"""FastAPI Backend Application for FraudPulse.

Provides API endpoints for transaction ingestion, alert querying,
and analyst decisions with live agreement rate calculation.
"""

import os
from dotenv import load_dotenv

load_dotenv()
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import pandas as pd

from src.agent import InvestigatorAgent
from src.db import (
    DB_PATH,
    calculate_session_stats,
    get_all_alerts,
    get_all_transactions_df,
    init_db,
    save_alert,
    save_transaction,
    update_analyst_decision,
)
from src.generator import generate_synthetic_transactions
from src.ml.model import get_fraud_model

app = FastAPI(
    title="FraudPulse API & Dashboard",
    description="AI-Assisted Fraud Investigation Copilot Backend & Dashboard",
    version="1.0.0",
)

# Initialize ML Model & Investigator Agent
fraud_model = get_fraud_model()
agent = InvestigatorAgent()

# Mount static files directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def read_root():
    """Serves the main HTML5 Analyst Dashboard."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "FraudPulse API Running. Dashboard index.html not found."}



class TransactionEvent(BaseModel):
    transaction_id: str
    user_id: str
    timestamp: str
    amount: float
    currency: str = "INR"
    merchant_category: str = "retail"
    device_id: str
    ip_address: str
    shipping_address: str
    city: str
    is_fraud: Optional[bool] = False
    fraud_type: Optional[str] = "none"
    is_stealth: Optional[bool] = False


class DecisionPayload(BaseModel):
    decision: str = Field(
        ...,
        description="Analyst decision: 'MARK_FRAUD' or 'MARK_OK'",
    )


@app.on_event("startup")
def startup_event():
    """Initializes SQLite database and populates baseline synthetic data if empty."""
    import time
    init_db()
    
    # Ensure baseline transactions are stored
    existing_tx = get_all_transactions_df()
    if len(existing_tx) == 0:
        df_gen = generate_synthetic_transactions(seed=42)
        for _, row in df_gen.iterrows():
            save_transaction(row.to_dict())

    # Ensure baseline alerts are populated if alerts table is empty
    existing_alerts = get_all_alerts()
    if len(existing_alerts) == 0:
        df_history = get_all_transactions_df()
        df_eval = RuleEngine.evaluate_dataset(df_history)

        # Filter only flagged or stealth transactions for investigation
        target_rows = [row.to_dict() for _, row in df_eval.iterrows() if row.get("is_flagged") or row.get("is_stealth")]

        for idx, tx_dict in enumerate(target_rows):
            # Throttle startup requests with 2-second sleep to prevent Groq API rate limit hits
            if idx > 0:
                time.sleep(2.5)

            audit = agent.investigate(tx_dict, df_eval)
            rec = audit["recommendation"]
            alert_dict = {
                "alert_id": f"alt_{tx_dict['transaction_id']}",
                "transaction_id": tx_dict["transaction_id"],
                "user_id": tx_dict["user_id"],
                "timestamp": tx_dict["timestamp"],
                "amount": tx_dict["amount"],
                "currency": tx_dict.get("currency", "INR"),
                "city": tx_dict.get("city", ""),
                "device_id": tx_dict.get("device_id", ""),
                "ip_address": tx_dict.get("ip_address", ""),
                "shipping_address": tx_dict.get("shipping_address", ""),
                "risk_score": tx_dict["risk_score"],
                "rules_fired": tx_dict["rules_fired"],
                "is_flagged": tx_dict["is_flagged"],
                "recommended_action": rec.recommended_action.value
                if hasattr(rec.recommended_action, "value")
                else str(rec.recommended_action),
                "confidence": rec.confidence.value
                if hasattr(rec.confidence, "value")
                else str(rec.confidence),
                "top_signals": rec.top_signals,
                "explanation": rec.explanation,
                "is_fallback": audit.get("is_fallback", False),
                "raw_prompt": audit.get("raw_prompt", ""),
                "raw_response": audit.get("raw_response", ""),
                "analyst_decision": "PENDING",
            }
            save_alert(alert_dict)


@app.post("/alerts/{alert_id}/reinvestigate")
def reinvestigate_alert(
    alert_id: str = Path(..., description="Target alert ID to re-run LLM investigation"),
) -> Dict[str, Any]:
    """Re-runs the LLM Investigator Agent live for a specific alert and updates SQLite storage."""
    alerts = get_all_alerts()
    target_alert = next((a for a in alerts if a["alert_id"] == alert_id), None)
    if not target_alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    df_history = get_all_transactions_df()
    tx_rows = df_history[df_history["transaction_id"] == target_alert["transaction_id"]]
    if len(tx_rows) == 0:
        raise HTTPException(status_code=404, detail=f"Transaction for alert {alert_id} not found")

    tx_dict = tx_rows.iloc[0].to_dict()
    tx_dict["rules_fired"] = target_alert["rules_fired"]
    tx_dict["risk_score"] = target_alert["risk_score"]

    # Execute fresh live investigation with force_fallback=False
    audit = agent.investigate(tx_dict, df_history, force_fallback=False)
    rec = audit["recommendation"]

    rec_action_str = (
        rec.recommended_action.value
        if hasattr(rec.recommended_action, "value")
        else str(rec.recommended_action)
    )
    confidence_str = (
        rec.confidence.value if hasattr(rec.confidence, "value") else str(rec.confidence)
    )

    updated_alert = {
        "alert_id": target_alert["alert_id"],
        "transaction_id": target_alert["transaction_id"],
        "user_id": target_alert["user_id"],
        "timestamp": target_alert["timestamp"],
        "amount": target_alert["amount"],
        "currency": target_alert.get("currency", "INR"),
        "city": target_alert.get("city", ""),
        "device_id": target_alert.get("device_id", ""),
        "ip_address": target_alert.get("ip_address", ""),
        "shipping_address": target_alert.get("shipping_address", ""),
        "risk_score": target_alert["risk_score"],
        "rules_fired": target_alert["rules_fired"],
        "is_flagged": target_alert["is_flagged"],
        "recommended_action": rec_action_str,
        "confidence": confidence_str,
        "top_signals": rec.top_signals,
        "explanation": rec.explanation,
        "is_fallback": audit.get("is_fallback", False),
        "raw_prompt": audit.get("raw_prompt", ""),
        "raw_response": audit.get("raw_response", ""),
        "analyst_decision": target_alert.get("analyst_decision", "PENDING"),
    }

    save_alert(updated_alert)
    return {"alert": updated_alert}


class SimulateRequest(BaseModel):
    scenario: str = Field(
        default="stealth_ring",
        description="Scenario: 'stealth_ring', 'velocity_spike', 'amount_anomaly', or 'clean_payment'",
    )


@app.post("/simulate")
def simulate_payment(req: SimulateRequest) -> Dict[str, Any]:
    """Simulates an incoming live payment event, intercepts it at gateway,
    runs rule engine + autonomous investigator agent, saves record, and returns
    full 5-stage trace for 3D animation.
    """
    import random
    import time
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    rand_suffix = random.randint(1000, 9999)
    scenario = req.scenario

    if scenario == "stealth_ring":
        tx_dict = {
            "transaction_id": f"tx_sim_{rand_suffix}",
            "user_id": "usr_105",
            "timestamp": now_iso,
            "amount": 757.0,
            "currency": "INR",
            "merchant_category": "electronics",
            "device_id": "dev_shared_stealth_ring",
            "ip_address": "103.21.105.10",
            "shipping_address": "60 MG Road, Chennai",
            "city": "Chennai",
            "is_fraud": True,
            "fraud_type": "stealth_shared_device",
            "is_stealth": True,
        }
    elif scenario == "velocity_spike":
        sim_dt = datetime(2026, 8, 24, 6, 8, 0, tzinfo=timezone.utc)
        tx_dict = {
            "transaction_id": f"tx_sim_{rand_suffix}",
            "user_id": "usr_103",
            "timestamp": sim_dt.isoformat(),
            "amount": 863.0,
            "currency": "INR",
            "merchant_category": "digital_goods",
            "device_id": "dev_usr_103",
            "ip_address": "103.21.103.10",
            "shipping_address": "12 Indiranagar, Bengaluru",
            "city": "Bengaluru",
            "is_fraud": True,
            "fraud_type": "velocity_spike",
            "is_stealth": False,
        }
    elif scenario == "amount_anomaly":
        tx_dict = {
            "transaction_id": f"tx_sim_{rand_suffix}",
            "user_id": "usr_101",
            "timestamp": now_iso,
            "amount": 45000.0,
            "currency": "INR",
            "merchant_category": "luxury_retail",
            "device_id": "dev_usr_101",
            "ip_address": "103.21.101.10",
            "shipping_address": "12 MG Road, Bengaluru",
            "city": "Bengaluru",
            "is_fraud": False,
            "fraud_type": "amount_anomaly",
            "is_stealth": False,
        }
    else:  # clean_payment
        tx_dict = {
            "transaction_id": f"tx_sim_{rand_suffix}",
            "user_id": "usr_104",
            "timestamp": now_iso,
            "amount": 420.0,
            "currency": "INR",
            "merchant_category": "grocery",
            "device_id": "dev_usr_104",
            "ip_address": "103.21.104.10",
            "shipping_address": "45 Anna Salai, Chennai",
            "city": "Chennai",
            "is_fraud": False,
            "fraud_type": "none",
            "is_stealth": False,
        }

    # 1. Gateway Interception
    save_transaction(tx_dict)

    # 2. ML Model Feature Extraction & Fraud Risk Prediction
    df_history = get_all_transactions_df()
    ml_res = fraud_model.predict(tx_dict, df_history)
    full_tx = {
        **tx_dict,
        **ml_res,
        "risk_score": ml_res["ml_risk_score"],
        "rules_fired": ml_res["ml_signals"],
    }

    # 3. Investigator Agent Tool-Calling
    audit = agent.investigate(full_tx, df_history, force_fallback=False)
    rec = audit["recommendation"]

    rec_action_str = (
        rec.recommended_action.value
        if hasattr(rec.recommended_action, "value")
        else str(rec.recommended_action)
    )
    confidence_str = (
        rec.confidence.value if hasattr(rec.confidence, "value") else str(rec.confidence)
    )

    alert_dict = {
        "alert_id": f"alt_{tx_dict['transaction_id']}",
        "transaction_id": tx_dict["transaction_id"],
        "user_id": tx_dict["user_id"],
        "timestamp": tx_dict["timestamp"],
        "amount": tx_dict["amount"],
        "currency": tx_dict.get("currency", "INR"),
        "city": tx_dict.get("city", ""),
        "device_id": tx_dict.get("device_id", ""),
        "ip_address": tx_dict.get("ip_address", ""),
        "shipping_address": tx_dict.get("shipping_address", ""),
        "risk_score": ml_res["ml_risk_score"],
        "rules_fired": ml_res["ml_signals"],
        "is_flagged": ml_res["is_flagged"],
        "recommended_action": rec_action_str,
        "confidence": confidence_str,
        "top_signals": rec.top_signals,
        "explanation": rec.explanation,
        "is_fallback": audit.get("is_fallback", False),
        "raw_prompt": audit.get("raw_prompt", ""),
        "raw_response": audit.get("raw_response", ""),
        "analyst_decision": "PENDING",
    }

    save_alert(alert_dict)

    return {
        "scenario": scenario,
        "step1_event": tx_dict,
        "step2_rules": {
            "ml_risk_score": ml_res["ml_risk_score"],
            "ml_signals": ml_res["ml_signals"],
            "feature_contributions": ml_res["feature_contributions"],
            "feature_vector": ml_res["feature_vector"],
            "is_flagged": ml_res["is_flagged"],
            "rules_fired": ml_res["ml_signals"],
            "risk_score": ml_res["ml_risk_score"],
        },
        "step3_tools": audit.get("tool_calls_made", []),
        "step4_verdict": {
            "recommended_action": rec_action_str,
            "confidence": confidence_str,
            "top_signals": rec.top_signals,
            "explanation": rec.explanation,
            "is_fallback": audit.get("is_fallback", False),
        },
        "step5_alert": alert_dict,
    }


@app.post("/events")
def post_event(tx: TransactionEvent) -> Dict[str, Any]:
    """Ingests a new transaction event, runs ML model & investigator agent, and saves audit alert."""
    tx_dict = tx.model_dump()
    save_transaction(tx_dict)

    df_history = get_all_transactions_df()
    ml_res = fraud_model.predict(tx_dict, df_history)

    full_tx = {
        **tx_dict,
        **ml_res,
        "risk_score": ml_res["ml_risk_score"],
        "rules_fired": ml_res["ml_signals"],
    }

    # Run Investigator Agent for flagged transactions or stealth cases
    audit = agent.investigate(full_tx, df_history)
    rec = audit["recommendation"]

    rec_action_str = (
        rec.recommended_action.value
        if hasattr(rec.recommended_action, "value")
        else str(rec.recommended_action)
    )
    confidence_str = (
        rec.confidence.value if hasattr(rec.confidence, "value") else str(rec.confidence)
    )

    alert_dict = {
        "alert_id": f"alt_{tx_dict['transaction_id']}",
        "transaction_id": tx_dict["transaction_id"],
        "user_id": tx_dict["user_id"],
        "timestamp": tx_dict["timestamp"],
        "amount": tx_dict["amount"],
        "currency": tx_dict.get("currency", "INR"),
        "city": tx_dict.get("city", ""),
        "device_id": tx_dict.get("device_id", ""),
        "ip_address": tx_dict.get("ip_address", ""),
        "shipping_address": tx_dict.get("shipping_address", ""),
        "risk_score": ml_res["ml_risk_score"],
        "rules_fired": ml_res["ml_signals"],
        "is_flagged": ml_res["is_flagged"],
        "recommended_action": rec_action_str,
        "confidence": confidence_str,
        "top_signals": rec.top_signals,
        "explanation": rec.explanation,
        "is_fallback": audit.get("is_fallback", False),
        "raw_prompt": audit.get("raw_prompt", ""),
        "raw_response": audit.get("raw_response", ""),
        "analyst_decision": "PENDING",
    }

    save_alert(alert_dict)

    return {
        "transaction_id": tx.transaction_id,
        "ml_model": ml_res,
        "investigation": alert_dict,
    }


@app.get("/alerts")
def get_alerts() -> List[Dict[str, Any]]:
    """Fetches all alert records with full investigation audit trails."""
    return get_all_alerts()


@app.post("/alerts/{alert_id}/decision")
def post_decision(
    alert_id: str = Path(..., description="Target alert ID"),
    payload: DecisionPayload = None,
) -> Dict[str, Any]:
    """Records an analyst decision ('MARK_FRAUD' or 'MARK_OK') and returns updated session stats."""
    if not payload or payload.decision not in ("MARK_FRAUD", "MARK_OK"):
        raise HTTPException(
            status_code=400,
            detail="Decision must be 'MARK_FRAUD' or 'MARK_OK'",
        )

    updated_alert = update_analyst_decision(alert_id, payload.decision)
    if not updated_alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    stats = calculate_session_stats()

    return {
        "alert": updated_alert,
        "session_stats": stats,
    }
