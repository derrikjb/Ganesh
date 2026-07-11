import os
import json
import copy
import yaml
import keyring
from pathlib import Path
from typing import Any, Dict, Optional

SUPPORTED_PROVIDERS = ("openai", "anthropic", "google", "openrouter", "local")
SUPPORTED_VOICE_PROVIDERS = ("deepgram", "elevenlabs")

_PROVIDER_ENV_VAR = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

_VOICE_PROVIDER_ENV_VAR = {
    "deepgram": "DEEPGRAM_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
}

DEFAULT_CONFIG = {
    "llm": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": None,
        "local": {
            "base_url": "http://localhost:11434/v1",
            "model": None,
        },
        "models": {
            "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            "anthropic": [
                "claude-3-5-sonnet-20240620",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
            ],
            "google": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"],
            "openrouter": [
                "openai/gpt-4o-mini",
                "anthropic/claude-3.5-sonnet",
                "google/gemini-2.0-flash-001",
            ],
            "local": [],
        },
        "temperature": 0.7,
        "max_tokens": 1000,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "timeout": 10.0,
        "test_max_tokens": 1,
    },
    "memory": {
        "enabled": True,
        "max_memories": 1000,
    },
    "voice": {
        "stt_enabled": False,
        "tts_enabled": False,
        "activation_mode": "click_to_talk",
        "input_device": None,
        "stt_language": None,
        "stt_engine": "local",
        "tts_engine": "local",
        "whisper_model": "tiny",
        "stt_device": "auto",
        "tts_device": "auto",
        "deepgram_model": "nova-2",
        "deepgram_url": "https://api.deepgram.com/v1/listen",
        "deepgram_smart_format": True,
        "deepgram_punctuate": True,
        "deepgram_diarize": False,
        "stt_timeout": 30.0,
        "tts_voice_name": "af_heart",
        "tts_model_path": "",
        "tts_voices_path": "",
        "kokoro_speed": 1.0,
        "kokoro_lang": "en-us",
        "elevenlabs_voice_id": "21m00Tcm4TlvDq8ikWAM",
        "elevenlabs_model": "eleven_turbo_v2_5",
        "elevenlabs_api_base": "https://api.elevenlabs.io/v1",
        "elevenlabs_stability": None,
        "elevenlabs_similarity_boost": None,
        "elevenlabs_style": None,
        "elevenlabs_speed": None,
        "tts_timeout": 30.0,
        "max_upload_bytes": 26214400,
        "audio": {
            "sample_rate": 16000,
            "channels": 1,
            "sample_width": 2,
        },
        "chime": {
            "sample_rate": 22050,
            "duration": 0.3,
            "frequency": 440.0,
            "fade_ms": 10,
        },
    },
    "embeddings": {
        "model": "all-MiniLM-L6-v2",
        "dimension": 384,
        "lancedb_uri": None,
    },
    "personality": {
        "traits": {
            "formality": 0.0,
            "verbosity": 0.0,
            "warmth": 0.5,
            "humor": 0.3,
            "assertiveness": 0.0,
        },
        "locked": [],
        "mutation_rate_cap": 0.15,
        "mutation_scale": 0.05,
        "trait_bounds": {
            "formality": [-1.0, 1.0],
            "verbosity": [-1.0, 1.0],
            "warmth": [0.0, 1.0],
            "humor": [0.0, 1.0],
            "assertiveness": [-1.0, 1.0],
        },
    },
    "update": {
        "channel": "stable",
        "auto_check": True,
    },
    "conversation_memory": {
        "enabled": True,
        "checkpoint_gap_seconds": 300,
        "min_messages_for_checkpoint": 2,
        "max_summaries_injected": 3,
        "full_pull_threshold": 0.85,
        "max_transcript_messages": 50,
        "adjacent_segments": 1,
        "summary_provider": None,
        "summary_model": None,
        "checkpoint_max_tokens": 200,
        "conversation_max_tokens": 500,
    },
    "retrieval": {
        "cross_day_threshold": 0.3,
        "search_limit": 5,
    },
    "continuity": {
        "welcome_threshold_seconds": 300,
    },
    "search": {
        "backend": "duckduckgo",
        "url": "https://html.duckduckgo.com/html/",
        "default_results": 5,
        "max_results": 20,
        "timeout": 10.0,
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    },
    "patterns": {
        "detection_threshold": 3,
        "suggestion_confidence": 0.7,
        "accept_delta": 0.1,
        "decline_delta": -0.2,
    },
    "conversations": {
        "auto_title_max_len": 50,
        "default_title": "New Conversation",
    },
    "model_download": {
        "chunk_size": 65536,
        "disk_space_safety_multiplier": 2,
    },
    "summary_embeddings": {
        "checkpoint_collection": "ganesh_checkpoint_summaries",
        "conversation_collection": "ganesh_conversation_summaries",
        "pool_limit_multiplier": 10,
        "pool_limit_min": 50,
    },
}

CONFIG_DIR = Path.home() / ".ganesh"
YAML_CONFIG_PATH = CONFIG_DIR / "config.yaml"
JSON_OVERRIDE_PATH = CONFIG_DIR / "config.json"
KEYRING_SERVICE = "ganesh"

class ConfigService:
    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        config = copy.deepcopy(DEFAULT_CONFIG)

        if YAML_CONFIG_PATH.exists():
            with open(YAML_CONFIG_PATH, "r") as f:
                yaml_data = yaml.safe_load(f) or {}
                self._deep_update(config, yaml_data)
        else:
            self.save_config(config)

        if JSON_OVERRIDE_PATH.exists():
            with open(JSON_OVERRIDE_PATH, "r") as f:
                json_data = json.load(f) or {}
                self._deep_update(config, json_data)

        self._config = config
        return self._config

    def save_config(self, config: Optional[Dict[str, Any]] = None) -> None:
        if config is not None:
            self._config = config
        
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(YAML_CONFIG_PATH, "w") as f:
            yaml.safe_dump(self._config, f, default_flow_style=False)

    def get_setting(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        val = self._config
        for part in parts:
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                return default
        return val

    def set_setting(self, key: str, value: Any) -> None:
        parts = key.split(".")
        val = self._config
        for part in parts[:-1]:
            if part not in val or not isinstance(val[part], dict):
                val[part] = {}
            val = val[part]
        val[parts[-1]] = value
        self.save_config()

    def get_api_key(self) -> Optional[str]:
        key = keyring.get_password(KEYRING_SERVICE, "openai_api_key")
        if not key:
            key = os.environ.get("OPENAI_API_KEY")
        return key

    def set_api_key(self, api_key: str) -> None:
        keyring.set_password(KEYRING_SERVICE, "openai_api_key", api_key)

    def get_provider_key(self, provider: str) -> Optional[str]:
        """Read a provider's API key from the keyring (no env fallback)."""
        if provider not in SUPPORTED_PROVIDERS:
            return None
        return keyring.get_password(KEYRING_SERVICE, f"ganesh_api_key_{provider}")

    def get_provider_key_env(self, provider: str) -> Optional[str]:
        """Read a provider's API key from the environment variable fallback."""
        env_var = _PROVIDER_ENV_VAR.get(provider)
        if not env_var:
            return None
        return os.environ.get(env_var)

    def set_provider_key(self, provider: str, api_key: str) -> None:
        """Store a provider's API key in the keyring."""
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unknown provider: {provider!r}")
        keyring.set_password(KEYRING_SERVICE, f"ganesh_api_key_{provider}", api_key)

    def is_provider_configured(self, provider: str) -> bool:
        """True if a provider has a key in keyring or env.

        The ``local`` provider has no key — it's considered configured when
        ``llm.local.base_url`` is set in the config.
        """
        if provider == "local":
            base_url = self.get_setting("llm.local.base_url")
            return bool(base_url)
        return bool(self.get_provider_key(provider) or self.get_provider_key_env(provider))

    def get_voice_provider_key(self, provider: str) -> Optional[str]:
        """Read a voice provider's API key from the keyring (no env fallback)."""
        if provider not in SUPPORTED_VOICE_PROVIDERS:
            return None
        return keyring.get_password(KEYRING_SERVICE, f"ganesh_voice_key_{provider}")

    def get_voice_provider_key_env(self, provider: str) -> Optional[str]:
        """Read a voice provider's API key from the environment variable fallback."""
        env_var = _VOICE_PROVIDER_ENV_VAR.get(provider)
        if not env_var:
            return None
        return os.environ.get(env_var)

    def set_voice_provider_key(self, provider: str, api_key: str) -> None:
        """Store a voice provider's API key in the keyring."""
        if provider not in SUPPORTED_VOICE_PROVIDERS:
            raise ValueError(f"Unknown voice provider: {provider!r}")
        keyring.set_password(KEYRING_SERVICE, f"ganesh_voice_key_{provider}", api_key)

    def is_voice_provider_configured(self, provider: str) -> bool:
        """True if a voice provider has a key in keyring or env."""
        if provider not in SUPPORTED_VOICE_PROVIDERS:
            return False
        return bool(
            self.get_voice_provider_key(provider)
            or self.get_voice_provider_key_env(provider)
        )

    def is_keyring_available(self) -> bool:
        try:
            keyring.get_keyring()
            return True
        except Exception:
            return False

    def _deep_update(self, base: Dict[str, Any], overrides: Dict[str, Any]) -> None:
        for k, v in overrides.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def get_safe_config(self) -> Dict[str, Any]:
        safe_config = copy.deepcopy(self._config)
        if "llm" in safe_config and "api_key" in safe_config["llm"]:
            safe_config["llm"]["api_key"] = None
        return safe_config

config_service = ConfigService()
