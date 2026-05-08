from __future__ import annotations

import logging
import httpx

from app.config import get_config
from app.escalation.ticket.base import BaseTicketAdapter

logger = logging.getLogger(__name__)


class ZendeskAdapter(BaseTicketAdapter):
    """Zendesk REST API adapter — ticket creation, lookup, and priority updates."""

    def _auth(self):
        config = get_config().escalation.zendesk
        if not config.subdomain or not config.api_token:
            raise ValueError("Zendesk not configured: missing subdomain or api_token")
        return (f"{config.email}/token", config.api_token)

    def _base_url(self) -> str:
        config = get_config().escalation.zendesk
        return f"https://{config.subdomain}.zendesk.com/api/v2"

    async def create_ticket(
        self,
        subject: str,
        description: str,
        customer_email: str,
        customer_name: str,
        metadata: dict | None = None,
    ) -> str:
        full_description = description
        if metadata:
            full_description += "\n\n--- Metadata ---\n"
            for k, v in metadata.items():
                full_description += f"{k}: {v}\n"

        payload = {
            "ticket": {
                "subject": subject,
                "description": full_description,
                "requester": {
                    "name": customer_name or "Guest",
                    "email": customer_email or "anonymous@voltimax.de",
                },
                "tags": ["voltimax-chat", "ai-escalation"],
            }
        }

        logger.info(f"Creating Zendesk ticket: subject={subject!r}, requester={customer_name!r} <{customer_email!r}>")

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self._base_url()}/tickets.json",
                json=payload,
                auth=self._auth(),
            )
            if response.status_code != 201:
                logger.error(f"Zendesk ticket failed: {response.status_code} — {response.text[:500]}")
            response.raise_for_status()
            data = response.json()

        logger.info(f"Zendesk ticket created: #{data['ticket']['id']}")
        return str(data["ticket"]["id"])

    async def get_ticket(self, ticket_id: str, requester_email: str) -> dict | None:
        """Fetch a ticket by ID. Returns ticket dict if requester email matches, None otherwise."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self._base_url()}/tickets/{ticket_id}.json",
                    auth=self._auth(),
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                ticket = response.json().get("ticket", {})

                # Fetch requester to verify email
                requester_id = ticket.get("requester_id")
                if requester_id:
                    user_resp = await client.get(
                        f"{self._base_url()}/users/{requester_id}.json",
                        auth=self._auth(),
                    )
                    if user_resp.status_code == 200:
                        user = user_resp.json().get("user", {})
                        if user.get("email", "").lower() != requester_email.lower():
                            return None  # Email doesn't match — deny access

                # Fetch latest comment
                comments_resp = await client.get(
                    f"{self._base_url()}/tickets/{ticket_id}/comments.json?sort_order=desc&per_page=1",
                    auth=self._auth(),
                )
                last_comment = ""
                if comments_resp.status_code == 200:
                    comments = comments_resp.json().get("comments", [])
                    if comments:
                        last_comment = comments[0].get("plain_body") or comments[0].get("body", "")

                return {
                    "id": str(ticket.get("id", "")),
                    "subject": ticket.get("subject", ""),
                    "status": ticket.get("status", ""),
                    "priority": ticket.get("priority") or "normal",
                    "created_at": str(ticket.get("created_at", ""))[:10],
                    "updated_at": str(ticket.get("updated_at", ""))[:10],
                    "tags": ticket.get("tags", []),
                    "last_comment": last_comment[:300],
                }
        except httpx.HTTPStatusError:
            return None

    async def mark_urgent(self, ticket_id: str, reason: str = "") -> bool:
        """Set ticket priority to urgent and add an internal note."""
        comment_body = (
            "\u26a0\ufe0f URGENT: Customer requested immediate attention via Groot chat.\n"
        )
        if reason:
            comment_body += f"Reason: {reason}\n"

        payload = {
            "ticket": {
                "priority": "urgent",
                "additional_tags": ["groot-urgent"],
                "comment": {
                    "body": comment_body,
                    "public": False,
                },
            }
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.put(
                    f"{self._base_url()}/tickets/{ticket_id}.json",
                    json=payload,
                    auth=self._auth(),
                )
                response.raise_for_status()
                return True
        except Exception:
            return False

    async def upload_attachment(self, filename: str, content: bytes, content_type: str = "application/pdf") -> str | None:
        """Upload a file to Zendesk and return the attachment token."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self._base_url()}/uploads.json",
                    params={"filename": filename},
                    content=content,
                    headers={"Content-Type": content_type},
                    auth=self._auth(),
                )
                response.raise_for_status()
                data = response.json()
                return data.get("upload", {}).get("token")
        except Exception:
            return None

    async def create_ticket_with_attachments(
        self,
        subject: str,
        description: str,
        customer_email: str,
        customer_name: str,
        attachment_tokens: list[str],
        tags: list[str] | None = None,
    ) -> str:
        """Create a ticket with file attachments."""
        payload = {
            "ticket": {
                "subject": subject,
                "comment": {
                    "body": description,
                    "uploads": attachment_tokens,
                },
                "requester": {
                    "name": customer_name,
                    "email": customer_email,
                },
                "tags": tags or ["voltimax-chat", "ai-escalation"],
            }
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self._base_url()}/tickets.json",
                json=payload,
                auth=self._auth(),
            )
            response.raise_for_status()
            data = response.json()

        return str(data["ticket"]["id"])
