from __future__ import annotations

import tempfile

import pytest
import yaml

import app.config as cfg_module
from app.config import AppConfig, load_config


@pytest.fixture(autouse=True)
def reset_config():
    """Reset the global config singleton between tests."""
    cfg_module._config = None
    yield
    cfg_module._config = None


@pytest.fixture
def minimal_config_data() -> dict:
    return {
        "server": {"host": "0.0.0.0", "port": 8000},
        "shopware": {
            "server_a_url": "http://localhost",
            "api_key": "test-api-key",
        },
        "jwt": {
            "secret": "test-secret-that-is-long-enough-32c",
            "algorithm": "HS256",
        },
        "mongodb": {
            "uri": "mongodb://localhost:27017",
            "database": "test_db",
        },
        "llm_providers": {
            "openai": {"api_key": "sk-test", "default_model": "gpt-4o"},
            "anthropic": {"api_key": "sk-ant-test", "default_model": "claude-3-haiku-20240307"},
        },
        "topic_routing": {
            "order_status": "anthropic",
            "product_help": "openai",
            "fallback": "openai",
        },
    }


@pytest.fixture
def config_file(minimal_config_data, tmp_path):
    """Write a minimal config YAML to a temp file and return the path."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(minimal_config_data))
    return str(path)


@pytest.fixture
def loaded_config(config_file):
    """Return a loaded AppConfig from the minimal config file."""
    cfg_module._config = None
    return load_config(config_file)
