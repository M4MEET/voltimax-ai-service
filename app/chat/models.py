from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: MessageRole
    content: str
    metadata: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CloseReason(str, Enum):
    COMPLETED = "completed"           # customer closed the chat normally
    IDLE_TIMEOUT = "idle_timeout"     # no activity, Groot closed it
    DISCONNECTED = "disconnected"     # WebSocket dropped unexpectedly
    ERROR = "error"                   # server error forced close
    ESCALATED = "escalated"           # handed off to human agent


class ChatSession(BaseModel):
    id: str = ""
    customer_name: str
    customer_email: str
    order_number: str | None = None
    sales_channel_id: str | None = None
    topic_id: str | None = None
    llm_provider: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    close_reason: str | None = None   # CloseReason value — why the session ended
    message_count: int = 0
    total_tokens: int = 0
    escalation_reason: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class IncomingMessage(BaseModel):
    type: str
    token: str | None = None
    topic_id: str | None = None
    content: str | None = None
    message_id: str | None = None
    feedback: str | None = None
    rating: int | None = None
    chat_id: str | None = None  # Widget's local session ID for reconnection
    # Confirmation flow
    action: str | None = None
    fields: dict | None = None  # { key: value } — confirmed/edited field values
    # Interactive responses
    input_value: str | None = None            # Response to input_prompt
    input_field: str | None = None            # Which field this is for


class OutgoingMessage(BaseModel):
    type: str
    content: str | None = None
    topics: list[dict] | None = None
    message: str | None = None
    ticket_id: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    # Confirmation flow
    confirmation: dict | None = None  # { action, title, summary, fields: [{key, label, value, editable, type}] }
    # Interactive UI elements
    choices: list[str] | None = None          # Choice button options
    input_prompt: dict | None = None          # { field, label, placeholder, action }
    info_card: dict | None = None             # { card_type, data, actions }
    suggestions: list[str] | None = None      # Contextual suggestion chips
