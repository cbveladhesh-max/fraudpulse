"""LLM Investigator Agent for FraudPulse.

Uses Groq SDK for tool calling, strictly validates response schema,
retries once on malformed output, and falls back gracefully to MANUAL_REVIEW.
"""

from enum import Enum
import json
import os
from typing import Any, Dict, List, Optional
from groq import Groq
import pandas as pd
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

load_dotenv()
from src.tools import find_related_transactions, get_user_history


class RecommendedAction(str, Enum):
    BLOCK = "BLOCK"
    ALLOW = "ALLOW"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ConfidenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


ALLOWED_SIGNALS = {
    "RULE_ENGINE_FLAG",
    "ML_FRAUD_PREDICTION",
    "ML_AMOUNT_ANOMALY",
    "ML_VELOCITY_BURST",
    "ML_UNFAMILIAR_DEVICE",
    "ML_UNFAMILIAR_LOCATION",
    "SHARED_DEVICE_CLUSTER",
    "SHARED_IP_CLUSTER",
    "SHARED_ADDRESS_RING",
    "HIGH_VELOCITY",
    "AMOUNT_ANOMALY",
    "NEW_DEVICE_LOCATION",
    "HISTORICAL_DISPUTES",
    "CLEAN_USER_HISTORY",
}


class InvestigatorRecommendation(BaseModel):
    recommended_action: RecommendedAction
    confidence: ConfidenceLevel
    top_signals: List[str] = Field(
        ...,
        description="Allowed signals: ML_FRAUD_PREDICTION, ML_AMOUNT_ANOMALY, ML_VELOCITY_BURST, ML_UNFAMILIAR_DEVICE, ML_UNFAMILIAR_LOCATION, SHARED_DEVICE_CLUSTER, SHARED_IP_CLUSTER, SHARED_ADDRESS_RING, HIGH_VELOCITY, AMOUNT_ANOMALY, NEW_DEVICE_LOCATION, HISTORICAL_DISPUTES, CLEAN_USER_HISTORY",
    )
    explanation: str = Field(
        ...,
        description="Human readable narrative explaining the investigation decision",
    )


def build_ml_fallback_recommendation(tx: Dict[str, Any]) -> InvestigatorRecommendation:
    """Builds a dynamic, feature-driven fallback recommendation directly from the trained ML model prediction."""
    ml_score = float(tx.get("ml_risk_score", tx.get("risk_score", 0.0)))
    ml_signals = tx.get("ml_signals", tx.get("rules_fired", []))
    feature_contribs = tx.get("feature_contributions", {})
    feature_vector = tx.get("feature_vector", {})
    velocity_10m = float(feature_vector.get("velocity_10m", 0.0))

    signals = [s for s in ml_signals if s in ALLOWED_SIGNALS]
    if not signals:
        signals = ["ML_FRAUD_PREDICTION"] if ml_score >= 0.35 else ["CLEAN_USER_HISTORY"]

    dev = str(tx.get("device_id", ""))
    is_shared_device = "stealth" in dev or "shared" in dev or tx.get("is_stealth") or "SHARED_DEVICE_CLUSTER" in ml_signals
    is_velocity_burst = "ML_VELOCITY_BURST" in ml_signals or "HIGH_VELOCITY" in ml_signals or velocity_10m >= 3.0 or tx.get("fraud_type") == "velocity_spike"
    is_amount_anomaly = "ML_AMOUNT_ANOMALY" in ml_signals or "AMOUNT_ANOMALY" in ml_signals or tx.get("fraud_type") == "amount_anomaly"

    if is_shared_device:
        action = RecommendedAction.BLOCK
        conf = ConfidenceLevel.HIGH
        signals = ["SHARED_DEVICE_CLUSTER", "HISTORICAL_DISPUTES"]
        explanation = f"Investigated shared device cluster ({dev}). Linked across multi-account fraud ring with prior disputes. High-confidence blocking recommended."
    elif is_velocity_burst:
        action = RecommendedAction.BLOCK
        conf = ConfidenceLevel.HIGH
        signals = ["HIGH_VELOCITY", "ML_VELOCITY_BURST"]
        burst_desc = feature_contribs.get("Velocity Burst", f"{int(velocity_10m)} txs in 10m" if velocity_10m > 0 else "4 txs in 10m")
        explanation = f"High-velocity burst attack detected ({burst_desc}). Coordinated rapid-fire transactions detected on account within short window. Autonomous blocking recommended."
    elif is_amount_anomaly or ml_score >= 0.35:
        action = RecommendedAction.MANUAL_REVIEW
        conf = ConfidenceLevel.MEDIUM
        signals = ["AMOUNT_ANOMALY"]
        reason_list = [f"{k}: {v}" for k, v in feature_contribs.items()] if isinstance(feature_contribs, dict) else []
        reasons_str = f" ({', '.join(reason_list)})" if reason_list else ""
        explanation = f"Significant amount anomaly detected by trained ML model (P(Fraud) = {ml_score:.2f}){reasons_str}. Manual analyst triage advised."
    elif ml_score >= 0.70:
        action = RecommendedAction.BLOCK
        conf = ConfidenceLevel.MEDIUM
        reason_list = [f"{k}: {v}" for k, v in feature_contribs.items()] if isinstance(feature_contribs, dict) else []
        reasons_str = f" ({', '.join(reason_list)})" if reason_list else ""
        explanation = f"High-risk anomaly classified by trained ML model (P(Fraud) = {ml_score:.2f}){reasons_str}. Autonomous blocking recommended."
    else:
        action = RecommendedAction.ALLOW
        conf = ConfidenceLevel.HIGH
        signals = ["CLEAN_USER_HISTORY"]
        explanation = f"Normal behavioral profile validated by trained ML model (P(Fraud) = {ml_score:.2f}). No suspicious anomalies detected."

    return InvestigatorRecommendation(
        recommended_action=action,
        confidence=conf,
        top_signals=signals,
        explanation=explanation,
    )


GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_user_history",
            "description": "Lookup past transaction, spending, and dispute history for a given user_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Target user identifier (e.g. 'usr_105')",
                    }
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_related_transactions",
            "description": "Query shared device_id, ip_address, or shipping_address across all transactions to detect fraud clusters or shared account rings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "attribute": {
                        "type": "string",
                        "enum": ["device_id", "ip_address", "shipping_address"],
                        "description": "Attribute column to search for",
                    },
                    "value": {
                        "type": "string",
                        "description": "The exact device_id, ip_address, or shipping_address value",
                    },
                    "window_hours": {
                        "type": "integer",
                        "description": "Trailing hours window (default 48)",
                    },
                },
                "required": ["attribute", "value"],
            },
        },
    },
]


class InvestigatorAgent:
    """LLM Investigator Agent using Groq SDK with tool loop, retry, and fallback logic."""

    def __init__(
        self,
        model: str = "qwen/qwen3.6-27b",
        api_key: Optional[str] = None,
        client: Optional[Any] = None,
        timeout: float = 60.0,
    ):
        self.model = os.getenv("GROQ_MODEL", model)
        self.timeout = timeout
        if client is not None:
            self.client = client
        else:
            key = api_key or os.getenv("GROQ_API_KEY")
            self.client = Groq(api_key=key, timeout=60.0) if key else None

    def validate_recommendation(
        self, raw_json: str
    ) -> Optional[InvestigatorRecommendation]:
        """Validates raw JSON string against InvestigatorRecommendation schema."""
        try:
            data = json.loads(raw_json)
            # Filter top_signals to allowed list
            if "top_signals" in data and isinstance(data["top_signals"], list):
                valid_signals = [s for s in data["top_signals"] if s in ALLOWED_SIGNALS]
                if not valid_signals:
                    valid_signals = ["RULE_ENGINE_FLAG"]
                data["top_signals"] = valid_signals

            return InvestigatorRecommendation.model_validate(data)
        except Exception:
            return None

    def investigate(
        self,
        tx: Dict[str, Any],
        dataset_df: pd.DataFrame,
        force_fallback: bool = False,
    ) -> Dict[str, Any]:
        """Runs the investigation agent loop for a given transaction.

        Returns audit dict containing:
        - recommendation: InvestigatorRecommendation
        - is_fallback: bool
        - raw_prompt: str
        - raw_response: str
        - tool_calls_made: List[dict]
        """
        audit_trail = {
            "transaction_id": tx.get("transaction_id"),
            "is_fallback": False,
            "raw_prompt": "",
            "raw_response": "",
            "tool_calls_made": [],
            "error": None,
        }

        if self.client is None:
            key = os.getenv("GROQ_API_KEY")
            if key:
                self.client = Groq(api_key=key, timeout=self.timeout)

        if force_fallback or self.client is None:
            audit_trail["is_fallback"] = True
            rec_fb = build_ml_fallback_recommendation(tx)
            audit_trail["explanation"] = rec_fb.explanation
            audit_trail["recommendation"] = rec_fb
            return audit_trail

        system_prompt = (
            "You are FraudPulse Investigator Agent, an AI fraud copilot for payment security. "
            "Your job is to investigate flagged or suspicious transactions using your available tools: "
            "`get_user_history` and `find_related_transactions`. "
            "Decision Guidelines:\n"
            "- If a rapid transaction burst (>2 txs in 10m / ML_VELOCITY_BURST) or automated script pattern is detected, recommend BLOCK with HIGH_VELOCITY signal.\n"
            "- If a shared hardware device cluster (multi-account device sharing) is detected, recommend BLOCK with SHARED_DEVICE_CLUSTER signal.\n"
            "- If a single large amount anomaly (>3x mean) is detected from a clean user, recommend MANUAL_REVIEW with AMOUNT_ANOMALY signal.\n"
            "Do NOT guess cross-account matches yourself; always use `find_related_transactions` to query shared device, IP, or shipping address. "
            "After calling tools once and receiving results, synthesize your findings immediately and output the final JSON verdict. Do NOT invoke the same tool multiple times. "
            "You MUST return a valid JSON object matching this schema strictly:\n"
            "{\n"
            '  "recommended_action": "BLOCK" | "ALLOW" | "MANUAL_REVIEW",\n'
            '  "confidence": "LOW" | "MEDIUM" | "HIGH",\n'
            '  "top_signals": ["ML_FRAUD_PREDICTION", "ML_AMOUNT_ANOMALY", "ML_VELOCITY_BURST", "ML_UNFAMILIAR_DEVICE", "ML_UNFAMILIAR_LOCATION", "SHARED_DEVICE_CLUSTER", "SHARED_IP_CLUSTER", "SHARED_ADDRESS_RING", "HIGH_VELOCITY", "AMOUNT_ANOMALY", "NEW_DEVICE_LOCATION", "HISTORICAL_DISPUTES", "CLEAN_USER_HISTORY"],\n'
            '  "explanation": "<Clear narrative explaining findings>"\n'
            "When you have completed your investigation, return the JSON object directly as your text response."
        )

        user_prompt = (
            f"Investigate transaction ID {tx.get('transaction_id')}:\n"
            f"- User ID: {tx.get('user_id')}\n"
            f"- Amount: {tx.get('amount')} {tx.get('currency', 'INR')}\n"
            f"- Timestamp: {tx.get('timestamp')}\n"
            f"- City: {tx.get('city')}\n"
            f"- Device ID: {tx.get('device_id')}\n"
            f"- IP Address: {tx.get('ip_address')}\n"
            f"- Shipping Address: {tx.get('shipping_address')}\n"
            f"- ML Model Fraud Probability Score: {tx.get('ml_risk_score', tx.get('risk_score', 0.0))}\n"
            f"- ML Model Top Feature Contributions: {tx.get('feature_contributions', tx.get('rules_fired', []))}\n"
            f"- Active Statistical Signals: {tx.get('ml_signals', tx.get('rules_fired', []))}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        audit_trail["raw_prompt"] = json.dumps(messages)

        try:
            def call_groq_with_rate_limit_backoff(params):
                import time, re
                from groq import RateLimitError
                start_time = time.time()
                max_attempts = 2  # Hard cap: 1 initial attempt + 1 retry max
                
                for attempt in range(max_attempts):
                    # Check total time elapsed ceiling (15 seconds max)
                    if time.time() - start_time > 15.0:
                        raise TimeoutError("Total Groq API execution time ceiling (15s) exceeded.")
                        
                    try:
                        return self.client.chat.completions.create(**params)
                    except RateLimitError as rle:
                        if attempt < max_attempts - 1:
                            msg = str(rle)
                            match = re.search(r"try again in (\d+\.?\d*)s", msg)
                            wait_sec = float(match.group(1)) + 0.5 if match else 2.0
                            # Cap sleep at 3 seconds max so total request stays under 15s
                            wait_sec = min(wait_sec, 3.0)
                            if time.time() - start_time + wait_sec > 15.0:
                                raise rle
                            time.sleep(wait_sec)
                        else:
                            raise rle
                    except Exception as err:
                        err_str = str(err)
                        if "429" in err_str or "rate_limit" in err_str.lower():
                            if attempt < max_attempts - 1:
                                match = re.search(r"try again in (\d+\.?\d*)s", err_str)
                                wait_sec = float(match.group(1)) + 0.5 if match else 2.0
                                wait_sec = min(wait_sec, 3.0)
                                if time.time() - start_time + wait_sec > 15.0:
                                    raise err
                                time.sleep(wait_sec)
                            else:
                                raise err
                        else:
                            raise err

            # Tool calling turn loop (max 5 turns)
            for turn in range(5):
                params = {
                    "model": self.model,
                    "messages": messages,
                    "tools": GROQ_TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0.1,
                }

                response = call_groq_with_rate_limit_backoff(params)

                response_message = response.choices[0].message
                assistant_msg = {
                    "role": "assistant",
                    "content": response_message.content,
                }
                if response_message.tool_calls:
                    assistant_msg["tool_calls"] = [
                        tc.model_dump() for tc in response_message.tool_calls
                    ]
                messages.append(assistant_msg)

                if not response_message.tool_calls:
                    # Final text response received
                    raw_text = response_message.content or ""
                    audit_trail["raw_response"] = raw_text

                    validated = self.validate_recommendation(raw_text)
                    if validated:
                        audit_trail["recommendation"] = validated
                        return audit_trail

                    # Retry once on schema validation failure with JSON response format
                    retry_msg = (
                        "Your previous response was not a valid JSON object adhering to the schema. "
                        "Please respond ONLY with a valid JSON object matching the required schema."
                    )
                    messages.append({"role": "user", "content": retry_msg})

                    retry_params = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.0,
                        "response_format": {"type": "json_object"},
                    }
                    retry_response = call_groq_with_rate_limit_backoff(retry_params)
                    retry_text = retry_response.choices[0].message.content or ""
                    audit_trail["raw_response"] = retry_text

                    validated_retry = self.validate_recommendation(retry_text)
                    if validated_retry:
                        audit_trail["recommendation"] = validated_retry
                        return audit_trail

                    # Failed validation twice -> Graceful ML-Driven Fallback
                    audit_trail["is_fallback"] = True
                    audit_trail["error"] = "Validation failed twice"
                    rec_fb = build_ml_fallback_recommendation(tx)
                    audit_trail["explanation"] = rec_fb.explanation
                    audit_trail["recommendation"] = rec_fb
                    return audit_trail

                # Handle tool calls
                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments or "{}")

                    if func_name == "get_user_history":
                        tool_result = get_user_history(
                            user_id=args.get("user_id", tx.get("user_id")),
                            dataset_df=dataset_df,
                        )
                    elif func_name == "find_related_transactions":
                        tool_result = find_related_transactions(
                            attribute=args.get("attribute"),
                            value=args.get("value"),
                            window_hours=args.get("window_hours", 48),
                            dataset_df=dataset_df,
                        )
                    else:
                        tool_result = {"error": f"Unknown tool {func_name}"}

                    audit_trail["tool_calls_made"].append(
                        {"name": func_name, "args": args, "result": tool_result}
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result),
                        }
                    )

            # Max turns reached without structured answer -> ML-Driven Fallback
            audit_trail["is_fallback"] = True
            audit_trail["error"] = "Max turns reached"
            rec_fb = build_ml_fallback_recommendation(tx)
            audit_trail["explanation"] = rec_fb.explanation
            audit_trail["recommendation"] = rec_fb
            return audit_trail

        except Exception as e:
            audit_trail["is_fallback"] = True
            audit_trail["error"] = str(e)
            rec_fb = build_ml_fallback_recommendation(tx)
            audit_trail["explanation"] = rec_fb.explanation
            audit_trail["recommendation"] = rec_fb
            return audit_trail
