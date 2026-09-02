# FraudPulse: 5-Minute Live Demo Script & Walkthrough

This document provides a step-by-step presentation script for demonstrating FraudPulse to judges and risk engineering teams.

---

## Demo Timing Overview (Total: 5 Minutes)

| Time | Topic | Key Focus / Takeaway |
| :--- | :--- | :--- |
| **0:00 - 0:30** | Problem Statement | Black-box risk scores vs. explainable triage |
| **0:30 - 1:30** | Normal Flagged Alert (`alt_tx_1111`) | Proportional risk: `MANUAL_REVIEW`, clean device history |
| **1:30 - 3:00** | Stealth Fraud Case (`alt_tx_1118`) | Agent tool-calling uncovers cross-account shared device ring |
| **3:00 - 4:00** | Evidence Tab & Audit Trail | Raw prompt and LLM JSON output transparency |
| **4:00 - 4:30** | Rate Limit Resilience & Fallback | Graceful degradation under API rate limits |
| **4:30 - 5:00** | Session Stats & Agent Studio Vision | Analyst agreement rate & integration into payment platforms |

---

## Step-by-Step Script

### 1. Problem Statement (0:00 - 0:30)

> **Speaker Script:**
> *"In payment risk engineering, traditional fraud engines output risk scores—like 0.85 or 0.40—without explanations. Analysts spend minutes digging through logs for a single transaction, while multi-account fraud rings hide in plain sight because single-transaction evaluation is blind to shared infrastructure.*
>
> *FraudPulse is an AI-assisted Fraud Investigation Copilot. It combines fast deterministic rules with an autonomous Investigator Agent that executes database queries to explain transactions, uncover stealth fraud rings, and present actionable recommendations."*

---

### 2. Normal Flagged Transaction: Amount Anomaly (0:30 - 1:30)

> **Action in Dashboard:**
> 1. Open `http://127.0.0.1:8000`.
> 2. Click on transaction **`alt_tx_1111`** (User: `usr_101`, Amount: `₹45,000.00`, Risk Score: `0.40`).

> **Speaker Script:**
> *"Let's look at `alt_tx_1111`. The rule engine flagged this transaction for `RULE_AMOUNT_ANOMALY` because ₹45,000 is a sudden jump above the user's historical average of ~₹600.
>
> But notice the AI Recommendation tab: the Investigator Agent recommends **MANUAL_REVIEW** with **MEDIUM** confidence, rather than an automated block. 
> 
> Why? The agent ran historical queries and confirmed that the device ID, IP address, and shipping address match this user's clean 6-month history, with zero disputes. The agent demonstrates proportionate reasoning: an amount jump on a trusted device warrants verification, not an immediate block."*

---

### 3. Stealth Fraud Case: Shared Device Ring (1:30 - 3:00)

> **Action in Dashboard:**
> 1. Select transaction **`alt_tx_1118`** (User: `usr_105`, Amount: `₹757.00`, Risk Score: `0.00`).
> 2. Highlight that **Deterministic Rules Fired** is `None` (`is_flagged: false`, `risk_score: 0.00`).

> **Speaker Script:**
> *"Now let's examine `alt_tx_1118`. This is a **stealth fraud case**. 
>
> Notice that the traditional rule engine gave this transaction a risk score of **0.00**. No rules fired because ₹757 is within normal spending limits and the location is valid. Traditional engines would let this pass.
>
> However, our AI Investigator Agent autonomously called its `find_related_transactions` tool to query shared attributes. It discovered that device `dev_shared_stealth_ring` was used 2 hours earlier in a confirmed fraudulent transaction (`tx_1117`) on a completely different user account.
>
> The agent outputs **BLOCK** with **HIGH** confidence, top signal `SHARED_DEVICE_CLUSTER`, and explicitly explains: *'No deterministic rules fired, but cross-account device sharing with a known fraudulent transaction indicates a high probability of fraud.'*"*

---

### 4. Evidence Tab & Audit Trail (3:00 - 4:00)

> **Action in Dashboard:**
> 1. Inside the Inspector panel for `alt_tx_1118`, click on the **Evidence Tab**.
> 2. Scroll through the **Raw Prompt Sent to LLM** and **Raw LLM Response JSON**.

> **Speaker Script:**
> *"Risk and safety engineering requires total auditability. Click on the Evidence tab: here you see the exact raw prompt sent to the LLM—including tool definitions and user history—and the raw JSON response returned by the model. 
>
> Every recommendation is backed by a verifiable audit trail for compliance and internal review."*

---

### 5. Rate Limit Resilience & Fallback Mode (4:00 - 4:30)

> **Speaker Script / Demo Reference:**
> *"Under real-world API rate limits (e.g. Groq free tier), third-party services can blip or hit token limits. 
>
> FraudPulse is built with a hard 15-second execution ceiling and bounded retries. If an API call times out or hits a rate limit, FraudPulse degrades gracefully into **FALLBACK MODE**, returning a safe `MANUAL_REVIEW` recommendation without crashing the dashboard. 
>
> Analysts can also click the **`⚡ Re-investigate`** button to retry the live investigation on demand once rate limit windows clear."*

---

### 6. Live Agreement Rate Stat (4:30 - 5:00)

> **Action in Dashboard:**
> 1. On `alt_tx_1118` (AI Recommendation: `BLOCK`), click **Mark as Fraud**.
> 2. Observe the top header banner update: **"LLM recommendation matched analyst decision in 100% of cases this session"**.

> **Speaker Script:**
> *"When the analyst agrees with the AI recommendation and clicks 'Mark as Fraud', the live agreement stat banner updates in real time. This gives risk leads immediate feedback on model-analyst alignment during live triage sessions."*

---

### 7. Closing (5:00)

> **Speaker Script:**
> *"FraudPulse bridges the gap between raw scoring engines and human risk teams. By combining tool-calling AI agents with human-in-the-loop controls, FraudPulse can plug directly into payment gateways like Razorpay as an analyst-facing copilot layer on top of existing fraud detection pipelines. Thank you!"*
