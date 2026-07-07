from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from ganesh_backend.services.config import config_service, SUPPORTED_PROVIDERS
from ganesh_backend.services import llm as llm_service

router = APIRouter(prefix="/api/config", tags=["config"])

class ConfigUpdate(BaseModel):
    key: str
    value: Any

class KeyringUpdate(BaseModel):
    api_key: str

class ProviderKeyUpdate(BaseModel):
    api_key: str

class LocalEndpointUpdate(BaseModel):
    base_url: str
    model: str | None = None

@router.get("")
async def get_config() -> dict[str, Any]:
    return config_service.get_safe_config()

@router.put("")
async def update_config(update: ConfigUpdate) -> dict[str, str]:
    try:
        config_service.set_setting(update.key, update.value)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/keyring")
async def check_keyring() -> dict[str, bool]:
    return {"available": config_service.is_keyring_available()}

@router.post("/keyring")
async def store_api_key(update: KeyringUpdate) -> dict[str, str]:
    try:
        config_service.set_api_key(update.api_key)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/providers")
async def list_providers() -> dict[str, list[dict[str, Any]]]:
    providers = [
        {"name": p, "configured": config_service.is_provider_configured(p)}
        for p in SUPPORTED_PROVIDERS
    ]
    return {"providers": providers}

@router.post("/providers/{provider}/key")
async def store_provider_key(provider: str, update: ProviderKeyUpdate) -> dict[str, str]:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {provider!r}",
        )
    try:
        config_service.set_provider_key(provider, update.api_key)
        llm_service.reset_api_key_cache()
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/providers/{provider}/models")
async def list_provider_models(provider: str) -> dict[str, Any]:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {provider!r}",
        )
    return {"provider": provider, "models": llm_service.get_available_models(provider)}

@router.post("/providers/{provider}/test")
async def test_provider_connection(provider: str) -> dict[str, Any]:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {provider!r}",
        )
    ok = llm_service.test_connection(provider)
    return {"provider": provider, "ok": ok}

@router.post("/providers/local/endpoint")
async def set_local_endpoint(update: LocalEndpointUpdate) -> dict[str, str]:
    config_service.set_setting("llm.local.base_url", update.base_url)
    if update.model is not None:
        config_service.set_setting("llm.local.model", update.model)
    llm_service.reset_api_key_cache()
    return {"status": "ok"}
