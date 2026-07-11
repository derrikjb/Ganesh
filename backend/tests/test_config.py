import json
import yaml
import pytest
from unittest.mock import patch
from ganesh_backend.services.config import ConfigService, DEFAULT_CONFIG

class MockKeyring:
    def __init__(self):
        self.passwords = {}
    def set_password(self, service, username, password):
        self.passwords[(service, username)] = password
    def get_password(self, service, username):
        return self.passwords.get((service, username))
    def get_keyring(self):
        return self

@pytest.fixture
def temp_config_dir(tmp_path):
    with patch("ganesh_backend.services.config.CONFIG_DIR", tmp_path), \
         patch("ganesh_backend.services.config.YAML_CONFIG_PATH", tmp_path / "config.yaml"), \
         patch("ganesh_backend.services.config.JSON_OVERRIDE_PATH", tmp_path / "config.json"):
        yield tmp_path

@pytest.fixture
def mock_keyring():
    mock = MockKeyring()
    with patch("keyring.set_password", side_effect=mock.set_password), \
         patch("keyring.get_password", side_effect=mock.get_password), \
         patch("keyring.get_keyring", return_value=mock):
        yield mock

def test_load_default_config(temp_config_dir):
    service = ConfigService()
    assert service._config == DEFAULT_CONFIG
    assert (temp_config_dir / "config.yaml").exists()

def test_get_set_setting(temp_config_dir):
    service = ConfigService()
    service.set_setting("llm.model", "gpt-4")
    assert service.get_setting("llm.model") == "gpt-4"
    
    with open(temp_config_dir / "config.yaml", "r") as f:
        data = yaml.safe_load(f)
        assert data["llm"]["model"] == "gpt-4"

def test_keyring_store_retrieve(temp_config_dir, mock_keyring):
    service = ConfigService()
    service.set_api_key("test-key")
    assert service.get_api_key() == "test-key"
    assert mock_keyring.passwords[("ganesh", "openai_api_key")] == "test-key"

def test_config_excludes_secrets(temp_config_dir):
    service = ConfigService()
    service.set_setting("llm.api_key", "secret")
    safe_config = service.get_safe_config()
    assert safe_config["llm"]["api_key"] is None

def test_json_override(temp_config_dir):
    (temp_config_dir / "config.json").write_text(json.dumps({"llm": {"model": "json-model"}}))
    service = ConfigService()
    assert service.get_setting("llm.model") == "json-model"


def test_update_config_defaults(temp_config_dir):
    service = ConfigService()
    assert service.get_setting("update.channel") == "stable"
    assert service.get_setting("update.auto_check") is True


def test_update_config_set_channel(temp_config_dir):
    service = ConfigService()
    service.set_setting("update.channel", "beta")
    assert service.get_setting("update.channel") == "beta"


def test_update_config_set_auto_check(temp_config_dir):
    service = ConfigService()
    service.set_setting("update.auto_check", False)
    assert service.get_setting("update.auto_check") is False


def test_update_config_persists(temp_config_dir):
    service = ConfigService()
    service.set_setting("update.channel", "beta")
    service.set_setting("update.auto_check", False)

    with open(temp_config_dir / "config.yaml", "r") as f:
        data = yaml.safe_load(f)
    assert data["update"]["channel"] == "beta"
    assert data["update"]["auto_check"] is False


def test_update_config_safe(temp_config_dir):
    service = ConfigService()
    safe = service.get_safe_config()
    assert "update" in safe
    assert safe["update"]["channel"] == "stable"
    assert safe["update"]["auto_check"] is True

def test_update_config_in_safe_config(temp_config_dir):
    service = ConfigService()
    safe = service.get_safe_config()
    assert "update" in safe
    assert safe["update"]["channel"] == "stable"
    assert safe["update"]["auto_check"] is True

def test_conversation_memory_defaults(temp_config_dir):
    service = ConfigService()
    assert service.get_setting("conversation_memory.enabled") is True
    assert service.get_setting("conversation_memory.checkpoint_gap_seconds") == 300
    assert service.get_setting("conversation_memory.min_messages_for_checkpoint") == 2
    assert service.get_setting("conversation_memory.max_summaries_injected") == 3
    assert service.get_setting("conversation_memory.full_pull_threshold") == 0.85
    assert service.get_setting("conversation_memory.max_transcript_messages") == 50
    assert service.get_setting("conversation_memory.adjacent_segments") == 1
    assert service.get_setting("conversation_memory.summary_provider") is None
    assert service.get_setting("conversation_memory.summary_model") is None

def test_conversation_memory_override(temp_config_dir):
    override = {
        "conversation_memory": {
            "enabled": False,
            "checkpoint_gap_seconds": 600
        }
    }
    (temp_config_dir / "config.json").write_text(json.dumps(override))
    service = ConfigService()
    assert service.get_setting("conversation_memory.enabled") is False
    assert service.get_setting("conversation_memory.checkpoint_gap_seconds") == 600
    # Other defaults should remain
    assert service.get_setting("conversation_memory.min_messages_for_checkpoint") == 2

def test_kokoro_config_defaults(temp_config_dir):
    service = ConfigService()
    assert service.get_setting("voice.tts_voice_name") == "af_heart"
    assert service.get_setting("voice.tts_model_path") == ""
    assert service.get_setting("voice.tts_voices_path") == ""

def test_piper_config_removed(temp_config_dir):
    service = ConfigService()
    assert service.get_setting("voice.piper_voices") is None
    assert service.get_setting("voice.piper_active_voice") is None
