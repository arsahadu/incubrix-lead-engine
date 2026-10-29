import argparse
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

DB_PATH = Path("data/test_mode.db")
TRACKING_BASE = "http://localhost:8000/t"

def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            job_id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'scheduled',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tracking_links (
            tracking_id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            campaign TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS replies (
            reply_id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            reply_text TEXT NOT NULL,
            reply_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
    print(f"Test database ready: {DB_PATH}")

def add_event(con, lead_id, event_type, details):
    con.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), lead_id, event_type, details, now())
    )

def schedule(args):
    init_db()
    job_id = str(uuid.uuid4())
    with connect() as con:
        con.execute(
            """INSERT INTO scheduled_jobs
               (job_id, lead_id, channel, scheduled_at, message, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'scheduled', ?)""",
            (job_id, args.lead_id, args.channel, args.when, args.message, now())
        )
        add_event(con, args.lead_id, "message_scheduled",
                  f"job_id={job_id}; channel={args.channel}; scheduled_at={args.when}")
    print("Scheduled test job:", job_id)
    print("Status: scheduled (queued only; not sent)")

def create_tracking(args):
    init_db()
    tracking_id = str(uuid.uuid4())
    query = urlencode({"id": tracking_id, "lead": args.lead_id, "campaign": args.campaign})
    url = f"{TRACKING_BASE}?{query}"
    with connect() as con:
        con.execute(
            "INSERT INTO tracking_links VALUES (?, ?, ?, ?, ?)",
            (tracking_id, args.lead_id, args.campaign, url, now())
        )
        add_event(con, args.lead_id, "tracking_link_created",
                  f"tracking_id={tracking_id}; campaign={args.campaign}")
    print("Tracking ID:", tracking_id)
    print("Tracking URL:", url)
    print("Note: URL generation works; click tracking requires a running web endpoint.")

def log_reply(args):
    init_db()
    reply_id = str(uuid.uuid4())
    with connect() as con:
        con.execute(
            "INSERT INTO replies VALUES (?, ?, ?, ?, ?, ?)",
            (reply_id, args.lead_id, args.channel, args.text, args.reply_type, now())
        )
        add_event(con, args.lead_id, "reply_logged",
                  f"reply_id={reply_id}; channel={args.channel}; type={args.reply_type}")
    print("Reply logged:", reply_id)

def show_status(args):
    init_db()
    with connect() as con:
        for table in ("scheduled_jobs", "tracking_links", "replies", "events"):
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table}: {count}")
        print("\nRecent events:")
        rows = con.execute(
            "SELECT lead_id, event_type, details, created_at FROM events "
            "ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        for row in rows:
            print(dict(row))

def main():
    parser = argparse.ArgumentParser(description="IncuBrix safe test-mode workflow")
    sub = parser.add_subparsers(required=True)

    sub.add_parser("init", help="Initialize the test database")

    p = sub.add_parser("schedule", help="Queue a test message without sending")
    p.add_argument("--lead-id", required=True)
    p.add_argument("--channel", required=True, choices=["email", "instagram", "linkedin"])
    p.add_argument("--when", required=True, help="ISO timestamp, e.g. 2026-10-30T10:00:00+05:30")
    p.add_argument("--message", required=True)
    p.set_defaults(func=schedule)

    p = sub.add_parser("tracking", help="Generate a tracking URL")
    p.add_argument("--lead-id", required=True)
    p.add_argument("--campaign", default="assessment-test")
    p.set_defaults(func=create_tracking)

    p = sub.add_parser("reply", help="Log a real test reply or clearly labeled simulation")
    p.add_argument("--lead-id", required=True)
    p.add_argument("--channel", required=True, choices=["email", "instagram", "linkedin"])
    p.add_argument("--text", required=True)
    p.add_argument("--type", dest="reply_type", choices=[
        "positive", "negative", "opt_out", "question", "simulated"
    ], default="simulated")
    p.set_defaults(func=log_reply)

    p = sub.add_parser("status", help="Show workflow counts and recent events")
    p.set_defaults(func=show_status)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        init_db()

if __name__ == "__main__":
    main()
