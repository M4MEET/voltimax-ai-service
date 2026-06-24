"""Weekly analytics report — builds an HTML summary and emails it via SMTP."""
from __future__ import annotations

import logging

from app.analytics.aggregator import AnalyticsAggregator
from app.config import get_config

logger = logging.getLogger(__name__)


def _delta(d: float | None, good_when_down: bool = False) -> str:
    """Render a trend delta as a small colored HTML span."""
    if d is None:
        return ""
    rising = d > 0
    is_good = (rising and not good_when_down) or (not rising and good_when_down)
    color = "#9ca3af" if d == 0 else ("#16a34a" if is_good else "#dc2626")
    arrow = "" if d == 0 else ("&#9650;" if rising else "&#9660;")
    sign = "+" if d > 0 else ""
    return f' <span style="color:{color};font-size:12px">{sign}{d}% {arrow}</span>'


async def build_weekly_report(days: int = 7) -> dict:
    """Aggregate everything the weekly email needs."""
    agg = AnalyticsAggregator()
    return {
        "days": days,
        "overview": await agg.get_overview(days),
        "topics": await agg.get_topic_breakdown(days),
        "gaps": await agg.get_rag_gaps(days, limit=5),
        "products": await agg.get_product_recommendations(days),
        "ratings": await agg.get_rating_stats(days),
    }


def render_html(data: dict) -> str:
    """Render the report as an email-safe HTML string (inline styles)."""
    o = data["overview"]
    t = o.get("trends", {}) or {}
    days = data["days"]
    ratings = data["ratings"]
    products = data["products"]
    gaps = data["gaps"]
    topics = data["topics"][:5]

    def kpi(label, value, delta_html=""):
        return (
            f'<td style="padding:12px 16px;background:#f8f9fc;border-radius:10px;vertical-align:top">'
            f'<div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.5px">{label}</div>'
            f'<div style="font-size:22px;font-weight:700;color:#111827;margin-top:4px">{value}{delta_html}</div>'
            f'</td>'
        )

    kpi_row1 = (
        kpi("Total Chats", f"{o.get('total_chats', 0):,}", _delta(t.get("total_chats")))
        + '<td style="width:12px"></td>'
        + kpi("AI Resolution", f"{o.get('ai_resolution_rate', 0)}%", _delta(t.get("ai_resolution_rate")))
        + '<td style="width:12px"></td>'
        + kpi("Escalation Rate", f"{o.get('escalation_rate', 0)}%", _delta(t.get("escalation_rate"), good_when_down=True))
    )
    kpi_row2 = (
        kpi("Tickets", f"{o.get('tickets_created', 0):,}", _delta(t.get("tickets_created"), good_when_down=True))
        + '<td style="width:12px"></td>'
        + kpi("Avg Response", f"{o.get('avg_response_ms', 0)}ms" if o.get('avg_response_ms') else "—", _delta(t.get("avg_response_ms"), good_when_down=True))
        + '<td style="width:12px"></td>'
        + kpi("Avg Rating", f"{ratings.get('avg_rating', 0):.1f}/5" if ratings.get('total') else "—")
    )

    topics_rows = "".join(
        f'<tr><td style="padding:6px 0;color:#374151;font-size:13px">{tp.get("_id","?")}</td>'
        f'<td style="padding:6px 0;text-align:right;font-weight:600;font-size:13px">{tp.get("count",0)}</td></tr>'
        for tp in topics
    ) or '<tr><td style="color:#9ca3af;font-size:13px">No data</td></tr>'

    gaps_rows = "".join(
        f'<tr><td style="padding:6px 0;color:#374151;font-size:13px">{g.get("query","")[:70]}</td>'
        f'<td style="padding:6px 0;text-align:right;color:#b45309;font-size:13px">{g.get("count",0)}&times;</td></tr>'
        for g in gaps.get("gaps", [])
    ) or '<tr><td style="color:#16a34a;font-size:13px">No knowledge gaps &#10003;</td></tr>'

    conv = products.get("total_conversions", 0)
    revenue = products.get("total_revenue", 0)

    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;color:#111827">
  <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:24px;border-radius:14px 14px 0 0">
    <h1 style="margin:0;color:#fff;font-size:20px">VoltimaxChat — Wochenbericht</h1>
    <p style="margin:4px 0 0;color:#e0e7ff;font-size:13px">Letzte {days} Tage &middot; Trends vs. Vorperiode</p>
  </div>
  <div style="border:1px solid #eef0f4;border-top:none;border-radius:0 0 14px 14px;padding:24px;background:#fff">
    <table style="width:100%;border-collapse:separate"><tr>{kpi_row1}</tr>
    <tr><td colspan="5" style="height:12px"></td></tr>
    <tr>{kpi_row2}</tr></table>

    <h2 style="font-size:14px;margin:24px 0 8px">Top Themen</h2>
    <table style="width:100%;border-collapse:collapse">{topics_rows}</table>

    <h2 style="font-size:14px;margin:24px 0 8px">Wissenslücken (Fragen ohne gute Antwort)</h2>
    <table style="width:100%;border-collapse:collapse">{gaps_rows}</table>

    <h2 style="font-size:14px;margin:24px 0 8px">Produktempfehlungen</h2>
    <p style="font-size:13px;color:#374151;margin:0">
      {products.get('total_sessions_with_recommendations', 0)} Sessions mit Empfehlungen &middot;
      <b>{conv}</b> K&auml;ufe &middot; <b>&euro;{revenue:.2f}</b> Umsatz aus Chat
    </p>

    <p style="font-size:12px;color:#9ca3af;margin-top:24px;border-top:1px solid #eef0f4;padding-top:12px">
      Automatisch generiert von Groot Bot &middot; voltimax.de/dashboard
    </p>
  </div>
</div>"""


async def send_weekly_report(recipient: str | None = None, days: int = 7) -> dict:
    """Build and email the weekly report. Returns {sent, recipient}."""
    config = get_config()
    smtp = config.escalation.smtp
    to_email = recipient or config.escalation.support_email
    if not to_email:
        logger.warning("Weekly report: no recipient configured")
        return {"sent": False, "error": "no recipient configured"}
    if not (smtp.host and smtp.from_email):
        logger.warning("Weekly report: SMTP not configured")
        return {"sent": False, "error": "SMTP not configured"}

    data = await build_weekly_report(days)
    html = render_html(data)
    subject = f"VoltimaxChat Wochenbericht — {data['overview'].get('total_chats', 0)} Chats, letzte {days} Tage"
    text = "Ihr VoltimaxChat Wochenbericht. Bitte in einem HTML-fähigen Mail-Client öffnen."

    from app.escalation.email_sender import _send_email
    sent = _send_email(smtp, to_email, subject, html, text)
    return {"sent": sent, "recipient": to_email, "days": days}
