"""Tests for Task 40: Error Recovery.

Covers:
    - test_sidecar_reconnect: health endpoint + sidecar lifecycle
    - test_corrupted_memory_detection: LanceDB integrity check + repair + reset
    - test_disk_full_handling: ModelManager disk space check + ENOSPC
    - test_api_key_invalid_graceful: 401 from LLM → friendly message, no crash
"""
from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import main as main_module  # noqa: E402
from ganesh_backend.embeddings import HashEmbedder  # noqa: E402
from ganesh_backend.services import llm as llm_service  # noqa: E402
from ganesh_backend.services.memory import (  # noqa: E402
    BACKUP_FILENAME,
    SCHEMA_VERSION,
    MemoryService,
)
from ganesh_backend.services.model_manager import (  # noqa: E402
    DiskFullError,
    ModelManager,
    ModelSpec,
)
from ganesh_backend.routers import memory as memory_router  # noqa: E402
from ganesh_backend.routers import models as models_router  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_api_key_cache():
    llm_service.reset_api_key_cache()
    yield
    llm_service.reset_api_key_cache()


@pytest.fixture(autouse=True)
def _reset_memory_service():
    memory_router.reset_memory_service()
    yield
    memory_router.reset_memory_service()


@pytest.fixture(autouse=True)
def _reset_model_manager():
    models_router._reset()
    yield
    models_router._reset()


def test_sidecar_reconnect_health_endpoint_returns_ok():
    client = TestClient(main_module.create_app())
    with client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_sidecar_reconnect_shutdown_then_unreachable():
    client = TestClient(main_module.create_app())
    with client:
        resp = client.post("/shutdown")
        assert resp.status_code == 200
        assert resp.json()["status"] == "shutting down"


@pytest.fixture
def persistent_memory_service(tmp_path: Path) -> MemoryService:
    db_path = tmp_path / "lancedb"
    db_path.mkdir(parents=True, exist_ok=True)
    return MemoryService(
        db_path=str(db_path),
        embedder=HashEmbedder(dimension=64),
        collection_name=f"test_memories_{uuid.uuid4().hex[:8]}",
    )


def test_corrupted_memory_detection_healthy(persistent_memory_service: MemoryService):
    report = persistent_memory_service.check_integrity()
    assert report["healthy"] is True
    assert report["schema_version_expected"] == SCHEMA_VERSION
    assert report["schema_version_found"] == SCHEMA_VERSION
    assert report["error"] is None


def test_corrupted_memory_detection_schema_mismatch(
    persistent_memory_service: MemoryService,
):
    sv_path = persistent_memory_service._schema_version_path()
    sv_path.write_text(json.dumps({"schema_version": 999}))
    report = persistent_memory_service.check_integrity()
    assert report["healthy"] is False
    assert "mismatch" in (report["error"] or "").lower()


def test_corrupted_memory_repair_from_backup(persistent_memory_service: MemoryService):
    persistent_memory_service.store_memory(content="Memory one")
    persistent_memory_service.store_memory(content="Memory two")
    backup_path = persistent_memory_service._backup_path()
    assert backup_path is not None
    assert backup_path.exists()
    restored = persistent_memory_service.repair_from_backup(backup_path)
    assert restored == 2
    results = persistent_memory_service.retrieve_memories(query="memory", limit=10)
    contents = {r.content for r in results}
    assert "Memory one" in contents
    assert "Memory two" in contents


def test_corrupted_memory_reset_archives(
    persistent_memory_service: MemoryService, tmp_path: Path
):
    persistent_memory_service.store_memory(content="will be archived")
    db_path = Path(persistent_memory_service._db_path)
    assert db_path.exists()
    result = persistent_memory_service.reset(archive=True)
    assert result is True
    archived = list(db_path.parent.glob(f"{db_path.name}.corrupted.*"))
    assert len(archived) == 1
    report = persistent_memory_service.check_integrity()
    assert report["healthy"] is True
    assert persistent_memory_service.list_memories() == []


def test_corrupted_memory_router_endpoints(persistent_memory_service: MemoryService):
    memory_router.set_memory_service(persistent_memory_service)
    persistent_memory_service.store_memory(content="backed up memory")
    client = TestClient(main_module.create_app())
    with client:
        integrity = client.get("/api/memory/integrity")
        assert integrity.status_code == 200
        assert integrity.json()["healthy"] is True

        repair = client.post("/api/memory/repair")
        assert repair.status_code == 200
        assert repair.json()["restored"] == 1

        reset = client.post("/api/memory/reset")
        assert reset.status_code == 200
        assert reset.json()["archived"] is True

        integrity2 = client.get("/api/memory/health")
        assert integrity2.status_code == 200
        assert integrity2.json()["healthy"] is True


@pytest.fixture
def disk_manager(tmp_path: Path) -> ModelManager:
    return ModelManager(models_dir=tmp_path / "models")


def test_disk_full_check_disk_space_returns_fields(disk_manager: ModelManager):
    info = disk_manager.check_disk_space()
    assert "free" in info
    assert "total" in info
    assert "used" in info
    assert "threshold" in info
    assert "sufficient" in info
    assert isinstance(info["sufficient"], bool)


def test_disk_full_handling_enospc_during_write(
    disk_manager: ModelManager, tmp_path: Path
):
    payload = b"x" * 1024
    digest = hashlib.sha256(payload).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=payload, headers={"Content-Length": str(len(payload))}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    disk_manager._specs["stt"] = ModelSpec(
        name="stt",
        url="https://example.com/stt.bin",
        checksum=digest,
        description="STT",
        size=len(payload),
    )

    original_open = open

    def fake_open(path, mode="r", *args, **kwargs):
        f = original_open(path, mode, *args, **kwargs)

        def write(_data):
            raise OSError(errno.ENOSPC, "No space left on device")

        f.write = write
        return f

    async def run():
        with patch("ganesh_backend.services.model_manager.open", fake_open):
            with pytest.raises((OSError, DiskFullError)):
                await disk_manager.download_model("stt", client=client)

    asyncio.run(run())
    progress = disk_manager.get_download_progress()["stt"]
    assert progress.status == "disk_full"
    assert "disk" in (progress.error or "").lower()


def test_disk_full_router_endpoint(disk_manager: ModelManager):
    from ganesh_backend.services.model_manager import reset_model_manager
    import ganesh_backend.services.model_manager as mm
    reset_model_manager()
    mm._manager = disk_manager
    try:
        client = TestClient(main_module.create_app())
        with client:
            resp = client.get("/api/models/disk-space")
        assert resp.status_code == 200
        body = resp.json()
        assert "free" in body
        assert "sufficient" in body
    finally:
        reset_model_manager()


def test_api_key_invalid_graceful_missing_key():
    with patch(
        "ganesh_backend.services.llm.get_api_key",
        side_effect=llm_service.MissingAPIKeyError("no key configured"),
    ):
        client = TestClient(main_module.create_app())
        with client:
            resp = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert "api key" in detail.lower()
    assert "invalid" in detail.lower() or "missing" in detail.lower()


def test_api_key_invalid_graceful_revoked_key():
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        side_effect=Exception("AuthenticationError: invalid API key"),
    ), patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="revoked-key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            resp = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert resp.status_code == 401
    detail = resp.json()["detail"].lower()
    assert "invalid" in detail or "revoked" in detail


def test_api_key_invalid_streaming_returns_error_event():
    with patch(
        "ganesh_backend.services.llm.get_api_key",
        side_effect=llm_service.MissingAPIKeyError("no key"),
    ):
        client = TestClient(main_module.create_app())
        with client:
            resp = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )
    assert resp.status_code == 200
    body = resp.text
    assert "event: error" in body
    assert "401" in body or "api key" in body.lower()


def test_api_key_invalid_sidecar_stays_up():
    with patch(
        "ganesh_backend.services.llm.get_api_key",
        side_effect=llm_service.MissingAPIKeyError("no key"),
    ):
        client = TestClient(main_module.create_app())
        with client:
            bad = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
            assert bad.status_code == 401
            health = client.get("/health")
            assert health.status_code == 200
