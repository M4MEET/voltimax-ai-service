from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTicketAdapter(ABC):
    @abstractmethod
    async def create_ticket(
        self,
        subject: str,
        description: str,
        customer_email: str,
        customer_name: str,
        metadata: dict | None = None,
        internal_note: str | None = None,
    ) -> str:
        """Create a support ticket. Returns ticket ID.

        description: Customer-visible ticket body (transcript)
        internal_note: Support-only note (AI summary + metadata), added as private comment
        """
        ...
