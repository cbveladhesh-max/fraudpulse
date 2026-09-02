"""Standalone script to sequentially populate uninvestigated alerts with controlled 8s pacing.

Does NOT run automatically at server startup.
"""
import time
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.db as db
import src.main as m

def populate_uninvestigated_alerts():
    alerts = db.get_all_alerts()
    # Find all placeholder alerts lacking evidence (raw_prompt/raw_response)
    placeholder_alerts = [
        a for a in alerts 
        if not (a.get('raw_prompt') and a.get('raw_response'))
    ]

    print(f"Found {len(placeholder_alerts)} uninvestigated placeholder alerts to process.\n", flush=True)

    for idx, alert in enumerate(placeholder_alerts):
        alert_id = alert['alert_id']
        
        if idx > 0:
            print(f"Pacing requests: waiting 18.0 seconds before investigating {alert_id} to prevent rate limits...", flush=True)
            time.sleep(18.0)

        t0 = time.time()
        try:
            res = m.reinvestigate_alert(alert_id)
            a = res['alert']
            t1 = time.time()
            
            print(
                f"[{idx+1}/{len(placeholder_alerts)}] Alert: {a['alert_id']} | "
                f"Action: {a['recommended_action']} | "
                f"Confidence: {a['confidence']} | "
                f"Is Fallback: {a['is_fallback']} | "
                f"Time: {round(t1 - t0, 2)}s",
                flush=True
            )
        except Exception as err:
            print(f"[{idx+1}/{len(placeholder_alerts)}] Alert: {alert_id} | Failed with error: {err}", flush=True)

    print("\nData population complete! All alerts now have real live evidence data.", flush=True)

if __name__ == "__main__":
    populate_uninvestigated_alerts()
