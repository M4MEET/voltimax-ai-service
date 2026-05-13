from __future__ import annotations

import os
from typing import Any

import yaml
from pydantic import BaseModel


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    public_url: str = "http://localhost:8000"
    cors_origins: list[str] = ["*"]
    debug: bool = False


class ShopwareConfig(BaseModel):
    server_a_url: str
    api_key: str
    # OAuth2 client secret for direct Shopware Admin API calls.
    # Pair with api_key (= client_id) via POST /api/oauth/token grant_type=client_credentials.
    integration_secret: str = ""
    # Sales Channel access key for Store API (/store-api/...) — read-only, no OAuth needed.
    store_api_key: str = ""
    timeout: int = 10
    verify_ssl: bool = True


class MongoConfig(BaseModel):
    uri: str = "mongodb://localhost:27017"
    database: str = "voltimax_chat"


class JwtConfig(BaseModel):
    secret: str
    algorithm: str = "HS256"


class LlmProviderConfig(BaseModel):
    api_key: str = ""
    default_model: str = ""
    base_url: str | None = None


class TopicCard(BaseModel):
    id: str
    title: str
    icon: str = "💬"
    description: str = ""
    visibility: str = "always"
    llm_provider: str | None = None
    sub_cards: list["TopicCard"] = []


class KnowledgeBaseConfig(BaseModel):
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 512
    chunk_overlap: int = 50
    sources: dict[str, Any] = {}


class ZendeskConfig(BaseModel):
    subdomain: str = ""
    email: str = ""
    api_token: str = ""


class N8nConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://n8n:5678"
    webhook_paths: dict[str, str] = {}


class SmtpConfig(BaseModel):
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = "noreply@voltimax.de"
    from_name: str = "Voltimax Support"
    use_tls: bool = True


class EscalationConfig(BaseModel):
    ai_detection_enabled: bool = True
    frustration_threshold: float = 0.75
    max_failed_responses: int = 3
    zendesk: ZendeskConfig = ZendeskConfig()
    n8n: N8nConfig = N8nConfig()
    smtp: SmtpConfig = SmtpConfig()
    support_email: str = "support@voltimax.de"


class AnalyticsConfig(BaseModel):
    retention_days: int = 90
    dashboard_port: int = 8001


class RateLimitConfig(BaseModel):
    max_messages_per_session: int = 50
    max_messages_per_minute: int = 10
    daily_token_cap: int = 1000000
    abuse_detection: bool = True


class WebSocketConfig(BaseModel):
    ping_interval: int = 30
    sse_fallback: bool = True
    max_connections: int = 1000


class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    shopware: ShopwareConfig
    mongodb: MongoConfig = MongoConfig()
    jwt: JwtConfig
    llm_providers: dict[str, LlmProviderConfig] = {}
    topic_routing: dict[str, str] = {}
    topic_cards: list[TopicCard] = []
    knowledge_base: KnowledgeBaseConfig = KnowledgeBaseConfig()
    escalation: EscalationConfig = EscalationConfig()
    analytics: AnalyticsConfig = AnalyticsConfig()
    rate_limiting: RateLimitConfig = RateLimitConfig()
    websocket: WebSocketConfig = WebSocketConfig()


# Allow TopicCard self-reference
TopicCard.model_rebuild()


_config: AppConfig | None = None


def load_config(path: str | None = None) -> AppConfig:
    global _config
    if _config is not None:
        return _config

    config_path = path or os.getenv("CONFIG_PATH", "config.yaml")
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    _config = AppConfig(**raw)
    return _config


def get_config() -> AppConfig:
    if _config is None:
        return load_config()
    return _config
