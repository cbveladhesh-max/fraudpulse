# What Broke: Lessons Learned in LLM Rate Limiting & Agent Resiliency

During the development and testing of FraudPulse's autonomous Investigator Agent, we encountered real-world API rate-limiting issues on Groq's free tier. This document details what failed, how we diagnosed the root cause, the fix we engineered, and architectural improvements for production.

---

## 1. What We Tried First

Initially, we implemented a basic fallback mechanism: if the LLM call failed or threw an exception, the system caught the error and immediately returned a static `MANUAL_REVIEW` fallback recommendation (`is_fallback: True`). 

To make the demo seamless, we configured application startup (`startup_event` in FastAPI) to populate synthetic transactions and automatically trigger LLM investigations across all flagged and stealth transactions back-to-back before serving the dashboard.

---

## 2. What Broke

When running the application, startup population began hanging for **30+ minutes** across multiple stealth case investigations.

Three distinct issues compounded into a major system bottleneck:
1. **Back-to-Back Request Storm**: The startup lifespan fired tool-calling LLM investigations sequentially across all flagged and stealth alerts. Each investigation performed 3 to 4 API turns (initial prompt → tool execution → tool result → final response), rapidly burning through Groq's free-tier Tokens-per-Minute (TPM) and Tokens-per-Day (TPD) limits.
2. **Unbounded Backoff Loops**: Our initial rate-limit retry logic attempted up to **5 retries per request** with long sleep intervals (15 to 20 seconds per attempt).
3. **Compounding Delays**: Over a dataset of multiple transactions, 5 retry attempts × 15-20s sleeps × 3-4 tool turns per transaction accumulated into a massive 30+ minute execution delay.

---

## 3. How We Diagnosed It

We isolated the issue by analyzing execution timestamps and detailed traceback logs:

1. **Inspecting Log Outputs**:
   Log messages revealed that Groq API was returning HTTP `429 RateLimitError` with messages such as:
   `Rate limit reached for model openai/gpt-oss-20b on tokens per day (TPD): Limit 200000, Used 199532. Please try again in 6m46s.`
2. **Tracing Execution Flow**:
   We observed that individual API requests were waiting 15–20 seconds inside the retry loop, only to hit the 429 rate limit again on the next turn because the sleep time was shorter than the window required to reset the daily token bucket.
3. **HTTP Read Timeouts**:
   Short client-side timeouts (15s) were cutting off HTTP connections while the backoff sleep was active, causing premature exception cascades and forcing alerts into fallback mode even when the model was actively processing.

---

## 4. How We Fixed It

We re-architected the rate-limiting and retry logic in `src/agent.py` with strict, bounded constraints:

1. **Hard Attempt Cap**: Restricted retries to **exactly 2 attempts maximum** (1 initial call + 1 retry max).
2. **Capped Sleep Intervals**: Limited any single backoff sleep delay to a **maximum of 3.0 seconds**.
3. **Hard Request Ceiling**: Implemented a **15.0-second total time ceiling** per investigation. If an investigation exceeds 15 seconds total or fails its 2nd attempt, it aborts immediately and returns a clean `MANUAL_REVIEW` fallback recommendation (`is_fallback: True`).
4. **On-Demand Manual Re-Investigation**: Added a `POST /alerts/{id}/reinvestigate` endpoint and a **`⚡ Re-investigate`** UI button in the analyst dashboard, allowing analysts to manually trigger fresh LLM investigations on demand without restarting the server or triggering batch rate limits.

---

## 5. What We'd Do Differently With More Time

In a production environment, we would implement the following architectural enhancements:

- **Asynchronous Task Queue**: Replace sequential startup batch processing with a distributed queue (Celery + Redis / RabbitMQ) that processes investigations asynchronously with token-bucket rate pacing.
- **Multi-Provider Failover**: Implement multi-provider fallback (e.g., falling back from Groq to Anthropic Claude or OpenAI GPT-4o-mini) when primary model rate limits are reached.
- **Paid Tier & Dedicated Throughput**: Deploy dedicated enterprise API capacity or self-hosted open models (e.g., vLLM on cloud GPUs) to eliminate rate limits during traffic spikes.
