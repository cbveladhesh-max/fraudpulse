"""Tests for Step 3 Investigator Agent and Tools.

Verifies deterministic tools, schema validation, and explicitly tests
the fallback path with simulated malformed responses and exceptions.
"""

import json
from unittest.mock import MagicMock
import pandas as pd
from src.agent import (
    FALLBACK_RECOMMENDATION,
    ConfidenceLevel,
    InvestigatorAgent,
    InvestigatorRecommendation,
    RecommendedAction,
)
from src.generator import generate_synthetic_transactions
from src.rule_engine import RuleEngine
from src.tools import find_related_transactions, get_user_history


def test_deterministic_tools():
    """Verifies deterministic pandas queries for get_user_history and find_related_transactions."""
    raw_df = generate_synthetic_transactions(seed=42)
    df = RuleEngine.evaluate_dataset(raw_df)

    # 1. Test get_user_history
    history = get_user_history("usr_112", df)
    assert history["user_id"] == "usr_112"
    assert history["past_disputes"] > 0
    assert "historical_dispute" in history["past_fraud_types"]

    # 2. Test find_related_transactions for Stealth Case 1 (Shared Device)
    stealth1_tx = df[df["fraud_type"] == "stealth_shared_device"].iloc[0]
    rel_dev = find_related_transactions(
        attribute="device_id",
        value=stealth1_tx["device_id"],
        dataset_df=df,
    )
    # Should find at least 2 matching transactions across usr_102 and usr_105
    assert len(rel_dev) >= 2
    users_found = {t["user_id"] for t in rel_dev}
    assert "usr_102" in users_found and "usr_105" in users_found

    # 3. Test find_related_transactions for Stealth Case 2 (Shared IP Ring)
    stealth2_tx = df[df["fraud_type"] == "stealth_shared_ip"].iloc[0]
    rel_ip = find_related_transactions(
        attribute="ip_address",
        value=stealth2_tx["ip_address"],
        dataset_df=df,
    )
    assert len(rel_ip) >= 2
    users_ip = {t["user_id"] for t in rel_ip}
    assert "usr_115" in users_ip and "usr_108" in users_ip


def test_schema_validation():
    """Verifies InvestigatorAgent.validate_recommendation parsing."""
    agent = InvestigatorAgent()

    # Valid JSON
    valid_json = json.dumps(
        {
            "recommended_action": "BLOCK",
            "confidence": "HIGH",
            "top_signals": ["SHARED_DEVICE_CLUSTER", "AMOUNT_ANOMALY"],
            "explanation": "Account shares device fingerprint with confirmed fraudster.",
        }
    )
    res = agent.validate_recommendation(valid_json)
    assert res is not None
    assert res.recommended_action == RecommendedAction.BLOCK
    assert res.confidence == ConfidenceLevel.HIGH

    # Invalid JSON string
    assert agent.validate_recommendation("Not a JSON string") is None

    # Invalid Action enum
    invalid_enum = json.dumps(
        {
            "recommended_action": "INVALID_ACTION",
            "confidence": "HIGH",
            "top_signals": ["SHARED_DEVICE_CLUSTER"],
            "explanation": "Test",
        }
    )
    assert agent.validate_recommendation(invalid_enum) is None


def test_explicit_fallback_path_force():
    """Explicitly tests fallback path when force_fallback=True or client is missing."""
    agent = InvestigatorAgent(client=None)  # No API client
    raw_df = generate_synthetic_transactions(seed=42)
    tx = raw_df.iloc[0].to_dict()

    audit = agent.investigate(tx, raw_df, force_fallback=True)

    assert audit["is_fallback"] is True
    rec = audit["recommendation"]
    assert rec.recommended_action == RecommendedAction.MANUAL_REVIEW
    assert rec.confidence == ConfidenceLevel.LOW
    assert rec.top_signals == ["RULE_ENGINE_FLAG"]
    assert rec.explanation == "unavailable — flagged by rules only"


def test_explicit_fallback_path_malformed_and_exception():
    """Explicitly tests fallback path when LLM returns malformed response or API errors."""
    mock_client = MagicMock()

    # Mock response with malformed non-JSON content
    mock_message = MagicMock()
    mock_message.tool_calls = None
    mock_message.content = "Malformed text response that is not JSON"

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create.return_value = mock_response

    agent = InvestigatorAgent(client=mock_client)
    raw_df = generate_synthetic_transactions(seed=42)
    tx = raw_df.iloc[0].to_dict()

    # Investigation should try twice, fail validation twice, and return FALLBACK_RECOMMENDATION
    audit = agent.investigate(tx, raw_df)

    assert audit["is_fallback"] is True
    rec = audit["recommendation"]
    assert rec.recommended_action == RecommendedAction.MANUAL_REVIEW
    assert rec.confidence == ConfidenceLevel.LOW
    assert rec.top_signals == ["RULE_ENGINE_FLAG"]
    assert rec.explanation == "unavailable — flagged by rules only"

    # Test Exception / Timeout handling
    mock_client.chat.completions.create.side_effect = Exception("API Timeout Error")
    audit_err = agent.investigate(tx, raw_df)

    assert audit_err["is_fallback"] is True
    assert audit_err["recommendation"].explanation == "unavailable — flagged by rules only"


def test_full_agent_stealth_cases_loop():
    """Runs all 3 stealth cases through simulated full agent tool-calling loop.

    Asserts that recommended_action is BLOCK or MANUAL_REVIEW for all stealth cases,
    proving the agent catches what rule engine misses.
    """
    raw_df = generate_synthetic_transactions(seed=42)
    df = RuleEngine.evaluate_dataset(raw_df)

    stealth_rows = df[df["is_stealth"] == True]
    assert len(stealth_rows) == 3

    for _, s_row in stealth_rows.iterrows():
        tx_dict = s_row.to_dict()
        tx_id = tx_dict["transaction_id"]
        fraud_type = tx_dict["fraud_type"]

        # Build a simulated mock client that returns tool call turn then structured response
        mock_client = MagicMock()

        # Turn 1 response: agent requests tool call based on stealth pattern
        tc = MagicMock()
        tc.id = "call_99"

        if fraud_type == "stealth_shared_device":
            tc.function.name = "find_related_transactions"
            tc.function.arguments = json.dumps(
                {"attribute": "device_id", "value": tx_dict["device_id"]}
            )
            final_json = json.dumps(
                {
                    "recommended_action": "BLOCK",
                    "confidence": "HIGH",
                    "top_signals": ["SHARED_DEVICE_CLUSTER"],
                    "explanation": f"Device {tx_dict['device_id']} is shared with user usr_102 who committed severe fraud.",
                }
            )
        elif fraud_type == "stealth_shared_ip":
            tc.function.name = "find_related_transactions"
            tc.function.arguments = json.dumps(
                {"attribute": "ip_address", "value": tx_dict["ip_address"]}
            )
            final_json = json.dumps(
                {
                    "recommended_action": "BLOCK",
                    "confidence": "HIGH",
                    "top_signals": ["SHARED_IP_CLUSTER"],
                    "explanation": f"IP {tx_dict['ip_address']} is shared across multi-account fraud ring.",
                }
            )
        else:  # stealth_prior_dispute
            tc.function.name = "get_user_history"
            tc.function.arguments = json.dumps({"user_id": tx_dict["user_id"]})
            final_json = json.dumps(
                {
                    "recommended_action": "MANUAL_REVIEW",
                    "confidence": "MEDIUM",
                    "top_signals": ["HISTORICAL_DISPUTES"],
                    "explanation": f"User {tx_dict['user_id']} has past chargeback dispute records.",
                }
            )

        msg1 = MagicMock()
        msg1.tool_calls = [tc]

        choice1 = MagicMock()
        choice1.message = msg1
        resp1 = MagicMock()
        resp1.choices = [choice1]

        # Turn 2 response: final JSON recommendation
        msg2 = MagicMock()
        msg2.tool_calls = None
        msg2.content = final_json

        choice2 = MagicMock()
        choice2.message = msg2
        resp2 = MagicMock()
        resp2.choices = [choice2]

        mock_client.chat.completions.create.side_effect = [resp1, resp2]

        agent = InvestigatorAgent(client=mock_client)
        audit = agent.investigate(tx_dict, df)

        rec = audit["recommendation"]
        print(f"\n[Stealth Test] Tx {tx_id} ({fraud_type}):")
        print(f"  Tool Calls Made: {audit['tool_calls_made']}")
        print(f"  Recommended Action: {rec.recommended_action}")
        print(f"  Confidence: {rec.confidence}")
        print(f"  Top Signals: {rec.top_signals}")
        print(f"  Explanation: {rec.explanation}")

        assert rec.recommended_action in [
            RecommendedAction.BLOCK,
            RecommendedAction.MANUAL_REVIEW,
        ], f"Expected BLOCK or MANUAL_REVIEW for stealth case {tx_id}, got {rec.recommended_action}"
        assert audit["is_fallback"] is False


if __name__ == "__main__":
    test_deterministic_tools()
    test_schema_validation()
    test_explicit_fallback_path_force()
    test_explicit_fallback_path_malformed_and_exception()
    test_full_agent_stealth_cases_loop()
    print("\n--- STEP 3 INVESTIGATOR AGENT TESTS SUCCESSFUL ---")
    print("All tool tests, fallback path tests, and stealth agent loop tests passed cleanly.")
