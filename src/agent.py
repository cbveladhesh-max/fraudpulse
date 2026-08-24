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
        description="Allowed signals: RULE_ENGINE_FLAG, SHARED_DEVICE_CLUSTER, SHARED_IP_CLUSTER, SHARED_ADDRESS_RING, HIGH_VELOCITY, AMOUNT_ANOMALY, NEW_DEVICE_LOCATION, HISTORICAL_DISPUTES, CLEAN_USER_HISTORY",
    )
    explanation: str = Field(
        ...,
        description="Human readable narrative explaining the investigation decision",
    )


FALLBACK_RECOMMENDATION = InvestigatorRecommendation(
    recommended_action=RecommendedAction.MANUAL_REVIEW,
    confidence=ConfidenceLevel.LOW,
    top_signals=["RULE_ENGINE_FLAG"],
    explanation="unavailable — flagged by rules only",
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
        api_key: Optional[str] = None,
        model: str = "openai/gpt-oss-20b",
        client: Optional[Any] = None,
        timeout: float = 10.0,
    ):
        self.model = os.getenv("GROQ_MODEL", model)
        self.timeout = timeout
        if client is not None:
            self.client = client
        else:
            key = api_key or os.getenv("GROQ_API_KEY")
            self.client = Groq(api_key=key, timeout=self.timeout) if key else None

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

        if force_fallback or self.client is None:
            audit_trail["is_fallback"] = True
            audit_trail["explanation"] = FALLBACK_RECOMMENDATION.explanation
            audit_trail["recommendation"] = FALLBACK_RECOMMENDATION
            return audit_trail

        system_prompt = (
            "You are FraudPulse Investigator Agent, an AI fraud copilot for payment security. "
            "Your job is to investigate flagged or suspicious transactions using your available tools: "
            "`get_user_history` and `find_related_transactions`. "
            "Do NOT guess cross-account matches yourself; always use `find_related_transactions` to query shared device, IP, or shipping address. "
            "After calling necessary tools, you MUST return a valid JSON object matching this schema strictly:\n"
            "{\n"
            '  "recommended_action": "BLOCK" | "ALLOW" | "MANUAL_REVIEW",\n'
            '  "confidence": "LOW" | "MEDIUM" | "HIGH",\n'
            '  "top_signals": ["RULE_ENGINE_FLAG", "SHARED_DEVICE_CLUSTER", "SHARED_IP_CLUSTER", "SHARED_ADDRESS_RING", "HIGH_VELOCITY", "AMOUNT_ANOMALY", "NEW_DEVICE_LOCATION", "HISTORICAL_DISPUTES", "CLEAN_USER_HISTORY"],\n'
            '  "explanation": "<Clear narrative explaining findings>"\n'
            "}\n"
            "Output ONLY the JSON object, with no extra text or markdown formatting."
        )

        user_content = (
            f"Investigate transaction ID {tx.get('transaction_id')}:\n"
            f"- User ID: {tx.get('user_id')}\n"
            f"- Amount: {tx.get('amount')} {tx.get('currency', 'INR')}\n"
            f"- Timestamp: {tx.get('timestamp')}\n"
            f"- City: {tx.get('city')}\n"
            f"- Device ID: {tx.get('device_id')}\n"
            f"- IP Address: {tx.get('ip_address')}\n"
            f"- Shipping Address: {tx.get('shipping_address')}\n"
            f"- Deterministic Rules Fired: {tx.get('rules_fired', [])}\n"
            f"- Deterministic Risk Score: {tx.get('risk_score', 0.0)}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        audit_trail["raw_prompt"] = json.dumps(messages)

        try:
            # Tool calling turn loop (max 5 turns)
            for turn in range(5):
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=GROQ_TOOLS,
                    tool_choice="auto",
                    temperature=0.1,
                    timeout=self.timeout,
                )

                response_message = response.choices[0].message
                messages.append(response_message)

                if not response_message.tool_calls:
                    # Final text response received
                    raw_text = response_message.content or ""
                    audit_trail["raw_response"] = raw_text

                    validated = self.validate_recommendation(raw_text)
                    if validated:
                        audit_trail["recommendation"] = validated
                        return audit_trail

                    # Retry once on schema validation failure
                    retry_msg = (
                        "Your previous response was not a valid JSON object adhering to the schema. "
                        "Please respond ONLY with a valid JSON object matching the required schema."
                    )
                    messages.append({"role": "user", "content": retry_msg})

                    retry_response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=0.0,
                        timeout=self.timeout,
                    )
                    retry_text = retry_response.choices[0].message.content or ""
                    audit_trail["raw_response"] = retry_text

                    validated_retry = self.validate_recommendation(retry_text)
                    if validated_retry:
                        audit_trail["recommendation"] = validated_retry
                        return audit_trail

                    # Failed validation twice -> Graceful Fallback
                    audit_trail["is_fallback"] = True
                    audit_trail["error"] = "Validation failed twice"
                    audit_trail["recommendation"] = FALLBACK_RECOMMENDATION
                    return audit_trail

                # Handle tool calls
                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments or "{}")

                    audit_trail["tool_calls_made"].append(
                        {"name": func_name, "args": args}
                    )

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

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result),
                        }
                    )

            # Max turns reached without structured answer -> Fallback
            audit_trail["is_fallback"] = True
            audit_trail["error"] = "Max turns reached"
            audit_trail["recommendation"] = FALLBACK_RECOMMENDATION
            return audit_trail

        except Exception as e:
            audit_trail["is_fallback"] = True
            audit_trail["error"] = str(e)
            audit_trail["recommendation"] = FALLBACK_RECOMMENDATION
            return audit_trail
