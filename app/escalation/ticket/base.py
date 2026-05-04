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
    ) -> str:
        """Create a support ticket. Returns ticket ID."""
        ...
