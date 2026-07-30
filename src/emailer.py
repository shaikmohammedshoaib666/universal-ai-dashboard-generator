"""SMTP delivery for generated dashboard reports."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def configured_recipients() -> list[str]:
    return [address.strip() for address in os.getenv("REPORT_RECIPIENTS", "").split(",") if address.strip()]


def send_report(pdf_path: str | Path) -> str:
    """Email a PDF report using STARTTLS and return a human-readable result."""
    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM") or username
    recipients = configured_recipients()
    missing = [
        label for label, value in {
            "SMTP_HOST": host, "SMTP_USERNAME": username, "SMTP_PASSWORD": password,
            "SMTP_FROM (or SMTP_USERNAME)": sender, "REPORT_RECIPIENTS": recipients,
        }.items() if not value
    ]
    if missing:
        raise RuntimeError("Email is not configured. Missing: " + ", ".join(missing))

    report = Path(pdf_path)
    if not report.exists():
        raise FileNotFoundError(f"Report was not found: {report}")
    message = EmailMessage()
    message["Subject"] = "Your daily AI dashboard report"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(
        "Attached is your daily Universal AI Dashboard Generator report. "
        "It contains the latest saved dataset profile and evidence-based insights."
    )
    message.add_attachment(
        report.read_bytes(), maintype="application", subtype="pdf", filename=report.name
    )
    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(username, password)
        server.send_message(message)
    return f"Report emailed to {', '.join(recipients)}."
