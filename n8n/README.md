# N8N Workflows — VoltimaxChat

N8N acts as the **glue layer** between the AI service, Zendesk, email, and monitoring — without adding dependencies to the core application. Server B fires webhooks describing what happened. N8N decides what to do about it.

**Deployment:** Self-hosted Docker container on Hetzner (~200MB RAM, no subscription fees).

---

## Current Workflows

| Workflow | File | Trigger | What it does |
|----------|------|---------|--------------|
| **Zendesk Ticket** | `zendesk-ticket.json` | Webhook from AI pipeline | Creates Zendesk ticket with session context, customer phase, complexity, model used |
| **Escalation Alert** | `escalation-alert.json` | Webhook from AI pipeline | Sends urgent email to support with frustration score, session events, urgency reason |
| **Knowledge Ingestion** | `knowledge-ingestion.json` | Webhook (manual/CMS) | Syncs CMS content → re-embeds KB → clears semantic cache → returns chunk count |
| **Weekly Report** | `weekly-report.json` | Cron (Monday 9am) | Emails KPIs: total chats, AI resolution rate, escalation rate, token usage, cache stats, close reasons |

---

## Why N8N (not coded directly)

- **Decoupling** — AI service just fires a webhook and moves on. No Zendesk SDK, SMTP libs, or retry logic in Python code.
- **Non-developer changes** — Support team wants alerts on Slack instead of email? Add a Slack node — no code deploy.
- **Retry & error handling** — N8N handles failed deliveries, SMTP timeouts, API rate limits with built-in retries.
- **Observability** — Every execution logged with inputs/outputs. Debug why a ticket wasn't created without digging through app logs.
- **Composability** — New automations are drag-and-drop, not code changes.

---

## Future Workflow Ideas

### Operations & Monitoring

| Idea | Trigger | Flow |
|------|---------|------|
| **Uptime Monitor** | Cron (every 5 min) | Hit `/health` → alert on failure (email/Slack) |
| **Token Budget Alert** | Cron (daily) | Check daily token usage via `/api/analytics` → alert if approaching monthly budget |
| **Dead Session Cleanup** | Cron (daily) | Query MongoDB for sessions idle >24h → close them → update stats |

### Customer Intelligence

| Idea | Trigger | Flow |
|------|---------|------|
| **Frustration Spike Alert** | Webhook on `frustration_score > 8` | Instant Slack DM to support lead with session link |
| **Customer Satisfaction Digest** | Cron (weekly) | Aggregate rating scores from sessions → email summary to stakeholders |
| **Repeat Customer Detection** | Webhook on new session | Check if email has >3 sessions this week → flag for proactive support |

### Knowledge & Content

| Idea | Trigger | Flow |
|------|---------|------|
| **KB Freshness Check** | Cron (weekly) | Compare CMS last-modified timestamps → flag stale articles → email content team |
| **Auto-sync on CMS Publish** | Shopware webhook on content update | Trigger knowledge ingestion automatically when CMS pages are published |

### Feedback Loop

| Idea | Trigger | Flow |
|------|---------|------|
| **Zendesk Resolution Feedback** | Zendesk webhook on ticket resolved | Store resolution method in MongoDB → AI learns from human solutions |
| **Low-rated Session Review** | Cron (daily) | Find sessions rated 1-2 stars → email transcripts to team for review |
| **Unanswered Question Log** | Webhook on `close_reason=escalated` | Log the question that triggered escalation → weekly report of knowledge gaps |
