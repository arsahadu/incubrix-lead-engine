import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

DB_PATH = Path("data/test_mode.db")

app = FastAPI(title="IncuBrix Test Tracking")

def now():
    return datetime.now(timezone.utc).isoformat()

def record_click(tracking_id: str, lead_id: str, campaign: str):
    if not DB_PATH.exists():
        return False

    with sqlite3.connect(DB_PATH) as con:
        link = con.execute(
            """
            SELECT tracking_id
            FROM tracking_links
            WHERE tracking_id = ? AND lead_id = ?
            """,
            (tracking_id, lead_id),
        ).fetchone()

        if not link:
            return False

        con.execute(
            """
            INSERT INTO events
            (event_id, lead_id, event_type, details, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                f"click-{tracking_id}-{datetime.now().timestamp()}",
                lead_id,
                "tracking_link_clicked",
                f"tracking_id={tracking_id}; campaign={campaign}",
                now(),
            ),
        )

    return True

@app.get("/health")
def health():
    return {"status": "ok", "mode": "test"}

@app.get("/t", response_class=HTMLResponse)
def track(
    id: str = Query(...),
    lead: str = Query(...),
    campaign: str = Query("assessment-test"),
):
    if not record_click(id, lead, campaign):
        return HTMLResponse(
            "<h2>Tracking link not found</h2><p>This may be an invalid or expired test link.</p>",
            status_code=404,
        )

    return HTMLResponse(
        "<h2>IncuBrix test tracking</h2>"
        "<p>Click recorded successfully.</p>"
        "<p>This is a test endpoint; no message was sent.</p>"
    )
