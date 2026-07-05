from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
from ganesh_backend.services.config import config_service

router = APIRouter(prefix="/api/config", tags=["config"])

class ConfigUpdate(BaseModel):
    key: str
    value: Any

class KeyringUpdate(BaseModel):
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
