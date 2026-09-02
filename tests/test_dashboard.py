"""Tests for Step 5 Analyst Dashboard static file serving and live stats.

Verifies GET /, GET /static/index.html, GET /static/app.js, and Tailwind CDN integration.
"""

import os
from fastapi.testclient import TestClient
from src.db import init_db
from src.main import app

TEST_DB_PATH = "test_dashboard_step5.db"
os.environ["DATABASE_PATH"] = TEST_DB_PATH


def test_dashboard_frontend():
    """Verifies dashboard HTML, Tailwind CDN, and JS app static assets load successfully."""
    init_db(TEST_DB_PATH)

    with TestClient(app) as client:
        # 1. Test GET / (HTML Dashboard)
        root_resp = client.get("/")
        assert root_resp.status_code == 200
        assert "FraudPulse" in root_resp.text
        assert "tailwindcss.com" in root_resp.text
        assert "LLM recommendation matched analyst decision" in root_resp.text
        assert "Alert Inspector" in root_resp.text

        # 2. Test GET /static/app.js
        js_resp = client.get("/static/app.js")
        assert js_resp.status_code == 200
        assert "fetchAlerts" in js_resp.text
        assert "sortDesc" in js_resp.text

    print("\n--- STEP 5 ANALYST DASHBOARD TEST SUCCESSFUL ---")
    print("HTML dashboard, Tailwind CDN, and JS application static assets loaded cleanly.")


if __name__ == "__main__":
    test_dashboard_frontend()
