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

@router.get("")
async def get_config():
    return config_service.get_safe_config()

@router.put("")
async def update_config(update: ConfigUpdate):
    try:
        config_service.set_setting(update.key, update.value)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/keyring")
async def check_keyring():
    return {"available": config_service.is_keyring_available()}

@router.post("/keyring")
async def store_api_key(update: KeyringUpdate):
    try:
        config_service.set_api_key(update.api_key)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/providers")
async def list_providers():
    providers = [
        {"name": p, "configured": config_service.is_provider_configured(p)}
        for p in SUPPORTED_PROVIDERS
    ]
    return {"providers": providers}

@router.post("/providers/{provider}/key")
async def store_provider_key(provider: str, update: ProviderKeyUpdate):
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
async def list_provider_models(provider: str):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {provider!r}",
        )
    return {"provider": provider, "models": llm_service.get_available_models(provider)}

@router.post("/providers/{provider}/test")
async def test_provider_connection(provider: str):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {provider!r}",
        )
    ok = llm_service.test_connection(provider)
    return {"provider": provider, "ok": ok}
