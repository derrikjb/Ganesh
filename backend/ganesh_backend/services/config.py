import os
import json
import yaml
import keyring
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG = {
    "llm": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": None,
    },
    "memory": {
        "enabled": True,
        "max_memories": 1000,
    },
    "voice": {
        "stt_enabled": False,
        "tts_enabled": False,
    },
}

CONFIG_DIR = Path.home() / ".ganesh"
YAML_CONFIG_PATH = CONFIG_DIR / "config.yaml"
JSON_OVERRIDE_PATH = CONFIG_DIR / "config.json"
KEYRING_SERVICE = "ganesh"

class ConfigService:
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        config = DEFAULT_CONFIG.copy()

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
        import copy
        safe_config = copy.deepcopy(self._config)
        if "llm" in safe_config and "api_key" in safe_config["llm"]:
            safe_config["llm"]["api_key"] = None
        return safe_config

config_service = ConfigService()
