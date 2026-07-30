"""Durable daily scheduler. Run separately from Streamlit in production."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from .cleaning import load_cleaned_csv
from .emailer import send_report
from .insights import generate_insights
from .llm import build_executive_summary
from .reporting import build_pdf_report


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "latest_cleaned.csv"
REPORT_PATH = ROOT / "outputs" / "daily_ai_dashboard_report.pdf"


def generate_and_send() -> str:
    """Build and email a report from the latest dataset saved by the app."""
    load_dotenv(ROOT / ".env")
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"No saved dataset at {DATASET_PATH}. Upload a CSV in the app and click 'Save for daily automation' first."
        )
    frame, summary = load_cleaned_csv(str(DATASET_PATH))
    insights = generate_insights(frame, summary)
    executive_summary = build_executive_summary(insights)
    report = build_pdf_report(REPORT_PATH, frame, summary, insights, executive_summary)
    result = send_report(report)
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {result}")
    return result


def run_scheduler() -> None:
    load_dotenv(ROOT / ".env")
    timezone_name = os.getenv("REPORT_TIMEZONE", "Asia/Kolkata")
    timezone = ZoneInfo(timezone_name)
    hour = int(os.getenv("REPORT_HOUR", "7"))
    minute = int(os.getenv("REPORT_MINUTE", "0"))
    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(
        generate_and_send, "cron", hour=hour, minute=minute,
        id="daily_dashboard_report", replace_existing=True, misfire_grace_time=3600,
    )
    print(f"Daily dashboard email scheduled for {hour:02d}:{minute:02d} ({timezone_name}). Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Email the latest AI dashboard report every morning.")
    parser.add_argument("--run-now", action="store_true", help="Generate and send the report immediately.")
    args = parser.parse_args()
    if args.run_now:
        generate_and_send()
    else:
        run_scheduler()
