"""Self-monitoring alerts — emails the team about API errors and health problems.

The AI service checks its own logs and DB health, then emails separate alerts.
This covers failures where the process is still alive (errors, Mongo down). A
fully-dead service can't email itself — that case is caught by an external
watchdog (n8n pinging /health).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.config import get_config
from app.db.collections import logs_collection
from app.db.mongodb import get_db

logger = logging.getLogger(__name__)

# Per-alert cooldown so a persistent problem doesn't email every cycle.
_last_alert: dict[str, datetime] = {}
_COOLDOWN_MINUTES = 60


def _cooldown_ok(key: str) -> bool:
    now = datetime.now(timezone.utc)
    last = _last_alert.get(key)
    if last and (now - last) < timedelta(minutes=_COOLDOWN_MINUTES):
        return False
    _last_alert[key] = now
    return True


def _send(subject: str, html: str, text: str) -> bool:
    config = get_config()
    smtp = config.escalation.smtp
    to_email = config.escalation.support_email
    if not (to_email and smtp.host and smtp.from_email):
        logger.warning("Alert not sent — SMTP/recipient not configured")
        return False
    from app.escalation.email_sender import _send_email
    return _send_email(smtp, to_email, subject, html, text)


async def check_and_alert(error_minutes: int = 15) -> dict:
    """Check recent errors + DB health and email separate alerts. Returns a summary."""
    now = datetime.now(timezone.utc)
    result = {"api_errors": 0, "mongo_ok": True, "emails_sent": []}

    # Flush the in-memory log buffer first so we don't miss errors that
    # haven't been written to Mongo yet (handler batches up to 5 records).
    try:
        from app.logging_handler import flush_logs
        await flush_logs()
    except Exception:
        pass

    # ── 1. API errors (from the logs collection) ──
    since = now - timedelta(minutes=error_minutes)
    try:
        errors = await (
            logs_collection()
            .find({"level": "ERROR", "timestamp": {"$gte": since}})
            .sort("timestamp", -1)
            .to_list(50)
        )
    except Exception:
        errors = []
    result["api_errors"] = len(errors)

    if errors and _cooldown_ok("api_errors"):
        rows = "".join(
            f'<tr><td style="padding:4px 8px;color:#6b7280;font-size:12px;white-space:nowrap">'
            f'{str(e.get("timestamp",""))[:19]}</td>'
            f'<td style="padding:4px 8px;font-size:12px;color:#374151">'
            f'<b>{e.get("logger","?")}</b>: {str(e.get("message",""))[:160]}</td></tr>'
            for e in errors[:20]
        )
        html = (
            f'<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:640px">'
            f'<h2 style="color:#dc2626">Groot API Errors</h2>'
            f'<p style="font-size:13px;color:#374151">{len(errors)} error(s) in the last '
            f'{error_minutes} minutes:</p>'
            f'<table style="width:100%;border-collapse:collapse">{rows}</table>'
            f'<p style="font-size:12px;color:#9ca3af;margin-top:16px">'
            f'Dashboard: https://chat.voltimax.de/dashboard/logs</p></div>'
        )
        text_lines = "\n".join(
            f'- {str(e.get("timestamp",""))[:19]}  {e.get("logger","?")}: '
            f'{str(e.get("message",""))[:200]}'
            for e in errors[:20]
        )
        text = (
            f"Groot detected {len(errors)} error(s) in the AI service logs over "
            f"the last {error_minutes} minutes.\n\n"
            f"{text_lines}\n\n"
            f"Full logs: https://chat.voltimax.de/dashboard/logs\n\n"
            f"This is an automated monitoring message from the Voltimax chat service."
        )
        if _send(f"Groot API Errors — {len(errors)} in last {error_minutes}min", html, text):
            result["emails_sent"].append("api_errors")

    # ── 2. Health: MongoDB reachable? ──
    mongo_ok = True
    try:
        await get_db().command("ping")
    except Exception as e:
        mongo_ok = False
        logger.error(f"Health alert: MongoDB ping failed: {e}")
    result["mongo_ok"] = mongo_ok

    if not mongo_ok and _cooldown_ok("health"):
        html = (
            '<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:640px">'
            '<h2 style="color:#dc2626">Groot Health Alert</h2>'
            '<p style="font-size:14px;color:#374151"><b>MongoDB is unreachable.</b> '
            'The chat service cannot read or write sessions, knowledge, or analytics. '
            'Immediate attention required.</p>'
            '<p style="font-size:12px;color:#9ca3af">Check: '
            '<code>docker compose -f docker-compose.prod.yml ps mongo</code></p></div>'
        )
        text = (
            "Groot health alert: MongoDB is unreachable.\n\n"
            "The chat service cannot read or write sessions, knowledge, or "
            "analytics. Immediate attention required.\n\n"
            "Check container status:\n"
            "  docker compose -f docker-compose.prod.yml ps mongo\n\n"
            "This is an automated monitoring message from the Voltimax chat service."
        )
        if _send("Groot Health Alert — MongoDB unreachable", html, text):
            result["emails_sent"].append("health")

    return result
