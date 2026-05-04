from __future__ import annotations

import tempfile

import yaml
import pytest

import app.config as cfg_module
from app.config import AppConfig, load_config


def test_load_config_from_yaml(config_file):
    config = load_config(config_file)
    assert config.server.port == 8000
    assert config.shopware.api_key == "test-api-key"
    assert config.jwt.secret == "test-secret-that-is-long-enough-32c"
    assert config.llm_providers["openai"].api_key == "sk-test"
    assert config.llm_providers["openai"].default_model == "gpt-4o"


def test_config_defaults(config_file):
    config = load_config(config_file)
    assert config.server.host == "0.0.0.0"
    assert config.mongodb.database == "test_db"
    assert config.jwt.algorithm == "HS256"


def test_config_singleton(config_file):
    """load_config should return same instance on second call."""
    c1 = load_config(config_file)
    c2 = load_config()  # no path — uses cached
    assert c1 is c2


def test_config_topic_routing(config_file):
    config = load_config(config_file)
    assert config.topic_routing["order_status"] == "anthropic"
    assert config.topic_routing["fallback"] == "openai"


def test_config_escalation_defaults(config_file):
    config = load_config(config_file)
    assert config.escalation.frustration_threshold == 0.75
    assert config.escalation.max_failed_responses == 3
    assert config.escalation.ai_detection_enabled is True


def test_config_rate_limit_defaults(config_file):
    config = load_config(config_file)
    assert config.rate_limiting.max_messages_per_session == 50
    assert config.rate_limiting.max_messages_per_minute == 10
    assert config.rate_limiting.daily_token_cap == 1000000


def test_missing_required_fields():
    """AppConfig must require shopware and jwt fields."""
    with pytest.raises(Exception):
        AppConfig()  # Missing required shopware and jwt


def test_topic_cards_parsing(tmp_path):
    data = {
        "shopware": {"server_a_url": "http://x", "api_key": "k"},
        "jwt": {"secret": "s"},
        "topic_cards": [
            {
                "id": "orders",
                "title": "Orders",
                "visibility": "has_orders",
                "sub_cards": [
                    {"id": "order_status", "title": "Track Order"},
                ],
            }
        ],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data))
    cfg_module._config = None
    config = load_config(str(path))
    assert len(config.topic_cards) == 1
    assert config.topic_cards[0].id == "orders"
    assert config.topic_cards[0].sub_cards[0].id == "order_status"
