"""FastAPI Backend Application for FraudPulse.

Provides API endpoints for transaction ingestion, alert querying,
and analyst decisions with live agreement rate calculation.
"""

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Path
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
from src.rule_engine import RuleEngine

app = FastAPI(
    title="FraudPulse API",
    description="AI-Assisted Fraud Investigation Copilot Backend",
    version="1.0.0",
)

agent = InvestigatorAgent()


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
    init_db()
    existing_tx = get_all_transactions_df()
    if len(existing_tx) == 0:
        # Populate initial synthetic dataset for historical query baseline
        df_gen = generate_synthetic_transactions(seed=42)
        for _, row in df_gen.iterrows():
            save_transaction(row.to_dict())

        # Evaluate rules across dataset and create baseline alerts for flagged/stealth tx
        df_eval = RuleEngine.evaluate_dataset(df_gen)
        for _, row in df_eval.iterrows():
            tx_dict = row.to_dict()
            if tx_dict.get("is_flagged") or tx_dict.get("is_stealth"):
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


@app.post("/events")
def post_event(tx: TransactionEvent) -> Dict[str, Any]:
    """Ingests a new transaction event, runs rule engine & investigator agent, and saves audit alert."""
    tx_dict = tx.model_dump()
    save_transaction(tx_dict)

    df_history = get_all_transactions_df()
    rule_res = RuleEngine.evaluate_transaction(tx_dict, df_history)

    full_tx = {**tx_dict, **rule_res}

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
        "risk_score": rule_res["risk_score"],
        "rules_fired": rule_res["rules_fired"],
        "is_flagged": rule_res["is_flagged"],
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
        "rule_engine": rule_res,
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
