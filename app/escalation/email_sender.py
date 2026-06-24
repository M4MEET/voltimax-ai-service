"""Send escalation notification emails via SMTP."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_config

logger = logging.getLogger(__name__)


async def send_escalation_email_to_customer(
    customer_email: str,
    customer_name: str,
    session_id: str,
    ticket_id: str,
    topic: str,
    summary: str,
) -> bool:
    """Send confirmation email to the customer with ticket reference."""
    config = get_config().escalation
    smtp = config.smtp

    if not smtp.host or not customer_email:
        logger.warning("SMTP not configured or no customer email — skipping customer notification")
        return False

    subject = f"Voltimax Support — Your request #{ticket_id}"

    first_name = customer_name.split()[0] if customer_name else "Customer"

    html_body = f"""
    <div style="font-family: -apple-system, Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333;">
        <div style="background: linear-gradient(135deg, #6366f1, #4f46e5); padding: 24px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #fff; font-size: 20px; margin: 0;">Voltimax Support</h1>
        </div>
        <div style="padding: 24px; background: #fff; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px;">
            <p>Hi {first_name},</p>
            <p>Your support request has been received and a ticket has been created. A member of our team will review it shortly.</p>

            <div style="background: #f8f9fc; border-radius: 8px; padding: 16px; margin: 20px 0;">
                <table style="width: 100%; font-size: 14px;">
                    <tr>
                        <td style="padding: 4px 12px 4px 0; color: #6b7280; font-weight: 600;">Ticket ID:</td>
                        <td style="padding: 4px 0; font-weight: 700;">#{ticket_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 12px 4px 0; color: #6b7280; font-weight: 600;">Session:</td>
                        <td style="padding: 4px 0; font-family: monospace; font-size: 12px;">{session_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 12px 4px 0; color: #6b7280; font-weight: 600;">Topic:</td>
                        <td style="padding: 4px 0;">{topic or 'General'}</td>
                    </tr>
                </table>
            </div>

            <p style="font-size: 13px; color: #6b7280;"><strong>Summary of your conversation:</strong></p>
            <div style="background: #f8f9fc; border-left: 3px solid #6366f1; padding: 12px 16px; border-radius: 0 8px 8px 0; font-size: 13px; color: #4b5563; margin-bottom: 20px;">
                {summary}
            </div>

            <p style="font-size: 13px; color: #6b7280;">If you need to follow up, please reference your ticket ID <strong>#{ticket_id}</strong>.</p>

            <p style="margin-top: 24px; font-size: 13px; color: #9ca3af;">
                — Groot, AI Assistant at Voltimax<br>
                <a href="https://voltimax.de" style="color: #6366f1;">voltimax.de</a>
            </p>
        </div>
    </div>
    """

    text_body = f"""Hi {first_name},

Your support request has been received.

Ticket ID: #{ticket_id}
Session: {session_id}
Topic: {topic or 'General'}

Summary:
{summary}

If you need to follow up, reference ticket #{ticket_id}.

— Groot, AI Assistant at Voltimax
https://voltimax.de
"""

    return _send_email(smtp, customer_email, subject, html_body, text_body)


async def send_escalation_email_to_support(
    customer_email: str,
    customer_name: str,
    session_id: str,
    ticket_id: str,
    topic: str,
    escalation_reason: str,
    summary: str,
    transcript: str,
) -> bool:
    """Send full escalation details to the support team email."""
    config = get_config().escalation
    smtp = config.smtp

    if not smtp.host or not config.support_email:
        logger.warning("SMTP not configured or no support email — skipping support notification")
        return False

    subject = f"Groot Escalation — {topic or 'General'} — Ticket #{ticket_id}"

    html_body = f"""
    <div style="font-family: -apple-system, Arial, sans-serif; max-width: 700px; margin: 0 auto; color: #333;">
        <div style="background: #ef4444; padding: 16px 24px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #fff; font-size: 18px; margin: 0;">AI Escalation Alert</h1>
        </div>
        <div style="padding: 24px; background: #fff; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px;">
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                <table style="width: 100%; font-size: 14px;">
                    <tr><td style="padding: 4px 12px 4px 0; color: #991b1b; font-weight: 600;">Ticket:</td><td>#{ticket_id}</td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #991b1b; font-weight: 600;">Session:</td><td style="font-family: monospace; font-size: 12px;">{session_id}</td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #991b1b; font-weight: 600;">Customer:</td><td>{customer_name} ({customer_email})</td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #991b1b; font-weight: 600;">Topic:</td><td>{topic or 'General'}</td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #991b1b; font-weight: 600;">Reason:</td><td>{escalation_reason}</td></tr>
                </table>
            </div>

            <h3 style="font-size: 14px; color: #111;">AI Summary</h3>
            <div style="background: #f8f9fc; border-left: 3px solid #6366f1; padding: 12px 16px; border-radius: 0 8px 8px 0; font-size: 13px; margin-bottom: 20px;">
                {summary}
            </div>

            <h3 style="font-size: 14px; color: #111;">Full Transcript</h3>
            <pre style="background: #f8f9fc; padding: 16px; border-radius: 8px; font-size: 12px; white-space: pre-wrap; overflow-x: auto; max-height: 600px;">{transcript}</pre>
        </div>
    </div>
    """

    text_body = f"""AI ESCALATION ALERT

Ticket: #{ticket_id}
Session: {session_id}
Customer: {customer_name} ({customer_email})
Topic: {topic or 'General'}
Reason: {escalation_reason}

AI SUMMARY:
{summary}

FULL TRANSCRIPT:
{transcript}
"""

    return _send_email(smtp, config.support_email, subject, html_body, text_body)


async def send_urgent_alert_email(
    ticket_id: str,
    ticket_subject: str,
    customer_email: str,
    customer_name: str,
    reason: str = "",
) -> bool:
    """Send urgent alert to support team when a customer marks a ticket as urgent."""
    config = get_config().escalation
    smtp = config.smtp

    if not smtp.host or not config.support_email:
        logger.warning("SMTP not configured — skipping urgent alert email")
        return False

    subject = f"\U0001F6A8 URGENT — Ticket #{ticket_id} requires immediate attention"

    html_body = f"""
    <div style="font-family: -apple-system, Arial, sans-serif; max-width: 700px; margin: 0 auto; color: #333;">
        <div style="background: #dc2626; padding: 16px 24px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #fff; font-size: 18px; margin: 0;">\U0001F6A8 Urgent Escalation Request</h1>
        </div>
        <div style="padding: 24px; background: #fff; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px;">
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                <p style="margin: 0 0 8px; font-weight: 700; color: #991b1b;">Customer requested URGENT priority on this ticket.</p>
                <table style="width: 100%; font-size: 14px;">
                    <tr><td style="padding: 4px 12px 4px 0; color: #991b1b; font-weight: 600;">Ticket:</td><td>#{ticket_id}</td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #991b1b; font-weight: 600;">Subject:</td><td>{ticket_subject}</td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #991b1b; font-weight: 600;">Customer:</td><td>{customer_name} ({customer_email})</td></tr>
                    {"<tr><td style='padding: 4px 12px 4px 0; color: #991b1b; font-weight: 600;'>Reason:</td><td>" + reason + "</td></tr>" if reason else ""}
                </table>
            </div>
            <p style="font-size: 13px; color: #6b7280;">This ticket's priority has been changed to <strong>Urgent</strong> in Zendesk. Please review and respond as soon as possible.</p>
        </div>
    </div>
    """

    text_body = f"""URGENT ESCALATION REQUEST

Ticket: #{ticket_id}
Subject: {ticket_subject}
Customer: {customer_name} ({customer_email})
{"Reason: " + reason if reason else ""}

This ticket's priority has been changed to Urgent in Zendesk.
Please review and respond as soon as possible.
"""

    return _send_email(smtp, config.support_email, subject, html_body, text_body)


def _send_email(smtp_config, to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SMTP. Returns True on success."""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{smtp_config.from_name} <{smtp_config.from_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Port 465 = implicit SSL (SMTP_SSL). Port 587 = STARTTLS. Else plain.
        if int(smtp_config.port) == 465:
            server = smtplib.SMTP_SSL(smtp_config.host, smtp_config.port, timeout=20)
        elif smtp_config.use_tls:
            server = smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=20)
            server.starttls()
        else:
            server = smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=20)

        if smtp_config.username and smtp_config.password:
            server.login(smtp_config.username, smtp_config.password)

        server.sendmail(smtp_config.from_email, to_email, msg.as_string())
        server.quit()
        logger.info(f"Escalation email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False
