from __future__ import annotations

import httpx

from app.config import get_config
from app.escalation.ticket.base import BaseTicketAdapter


class N8nWebhookAdapter(BaseTicketAdapter):
    """Delegates ticket creation to n8n via webhook."""

    async def create_ticket(
        self,
        subject: str,
        description: str,
        customer_email: str,
        customer_name: str,
        metadata: dict | None = None,
    ) -> str:
        config = get_config().escalation.n8n

        if not config.enabled or not config.base_url:
            raise ValueError("n8n not configured: enabled=False or missing base_url")

        webhook_path = config.webhook_paths.get("ticket", "/webhook/voltimax-ticket")
        url = f"{config.base_url.rstrip('/')}{webhook_path}"

        payload = {
            "subject": subject,
            "description": description,
            "customer_email": customer_email,
            "customer_name": customer_name,
            "metadata": metadata or {},
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("ticket_id", "pending")
        except httpx.RequestError:
            pass

        return "pending"
