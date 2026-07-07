"""Memory service: explicit CRUD over LanceDB + local embeddings.

Recovery support: :meth:`check_integrity` probes schema version + row
count + sample read. :meth:`repair_from_backup` re-indexes from a JSON
backup. :meth:`reset` archives the corrupted DB and starts fresh. Every
``store_memory`` call appends to a JSON backup file (best-effort) so
repair never loses data.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast

from ganesh_backend.embeddings import (
    EmbedderProtocol,
    create_default_embedder,
)
from ganesh_backend.vector_store import LanceDbVectorStore

DEFAULT_COLLECTION = "ganesh_memories"
DEFAULT_DB_PATH = ":memory:"

#: Bumped whenever the LanceDB row schema changes. The integrity check
#: compares this against the version recorded in the sidecar file.
SCHEMA_VERSION = 1
SCHEMA_VERSION_FILENAME = "_schema_version.json"
BACKUP_FILENAME = "memories_backup.json"


class MemoryRecord:
    """A single memory entry returned by the service."""

    def __init__(
        self,
        id: str,
        content: str,
        metadata: dict[str, Any],
        created_at: str,
        updated_at: str,
    ) -> None:
        self.id = id
        self.content = content
        self.metadata = metadata
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MemoryService:
    """Explicit CRUD memory service backed by LanceDB."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        embedder: Optional[EmbedderProtocol] = None,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        self._db_path = db_path
        self._collection_name = collection_name
        self._embedder = embedder or create_default_embedder()
        self._store = LanceDbVectorStore(
            uri=db_path,
            collection_name=collection_name,
            vector_dim=self._embedder.dimension,
            distance="cosine",
        )
        self._store.create_col(collection_name, self._embedder.dimension, "cosine")
        self._write_schema_version()

    # ------------------------------------------------------------------
    # Schema version + backup helpers
    # ------------------------------------------------------------------

    def _is_persistent(self) -> bool:
        return self._db_path not in (":memory:", "", None)

    def _db_dir(self) -> Optional[Path]:
        if not self._is_persistent():
            return None
        return Path(self._db_path)

    def _schema_version_path(self) -> Optional[Path]:
        d = self._db_dir()
        return None if d is None else d / SCHEMA_VERSION_FILENAME

    def _backup_path(self) -> Optional[Path]:
        d = self._db_dir()
        return None if d is None else d / BACKUP_FILENAME

    def _write_schema_version(self) -> None:
        p = self._schema_version_path()
        if p is None:
            return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps({"schema_version": SCHEMA_VERSION}))
            tmp.replace(p)
        except OSError:
            pass

    def _read_schema_version(self) -> Optional[int]:
        p = self._schema_version_path()
        if p is None or not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            return int(data.get("schema_version", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _read_backup(self) -> list[dict[str, Any]]:
        p = self._backup_path()
        if p is None or not p.exists():
            return []
        try:
            return cast(list[dict[str, Any]], json.loads(p.read_text()))
        except (OSError, json.JSONDecodeError):
            return []

    def _append_backup(
        self, record: MemoryRecord, profile_id: Optional[str]
    ) -> None:
        p = self._backup_path()
        if p is None:
            return
        try:
            existing = self._read_backup()
            existing.append({
                "id": record.id,
                "content": record.content,
                "metadata": record.metadata,
                "profile_id": profile_id,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            })
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(existing))
            tmp.replace(p)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Integrity / recovery
    # ------------------------------------------------------------------

    def check_integrity(self) -> dict[str, Any]:
        """Probe LanceDB integrity. Returns dict with ``healthy``,
        ``schema_version_expected``, ``schema_version_found``, ``error``."""
        result: dict[str, Any] = {
            "healthy": False,
            "schema_version_expected": SCHEMA_VERSION,
            "schema_version_found": None,
            "error": None,
        }
        result["schema_version_found"] = self._read_schema_version()
        try:
            _ = self._store.list()
            probe_vec = self._embedder.embed("integrity probe")
            _ = self._store.search(
                query="integrity probe", vectors=probe_vec, top_k=1
            )
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
            return result
        found = result["schema_version_found"]
        if found is not None and found != SCHEMA_VERSION:
            result["error"] = (
                f"schema version mismatch: expected {SCHEMA_VERSION}, "
                f"found {found}"
            )
            return result
        result["healthy"] = True
        return result

    def export_backup(self, backup_path: Optional[Path] = None) -> Optional[Path]:
        """Export all memories to a JSON file. Returns the path written, or
        ``None`` if the DB is in-memory."""
        if not self._is_persistent():
            return None
        if backup_path is None:
            backup_path = self._backup_path()
        if backup_path is None:
            return None
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        records = self.list_memories()
        payload = []
        for r in records:
            full = self._store.get(r.id)
            profile_id = full.payload.get("profile_id") if full else None
            payload.append({
                "id": r.id,
                "content": r.content,
                "metadata": r.metadata,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "profile_id": profile_id,
            })
        tmp = backup_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, default=str))
        tmp.replace(backup_path)
        return backup_path

    def repair_from_backup(self, backup_path: Path) -> int:
        """Drop and recreate the collection, re-indexing from a JSON backup.

        Returns the number of memories restored. Raises ``FileNotFoundError``
        if the backup does not exist, ``ValueError`` if unparseable.
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"backup not found: {backup_path}")
        try:
            payload = json.loads(backup_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"corrupt backup file: {exc}") from exc
        self._store.reset()
        self._store.create_col(
            self._collection_name, self._embedder.dimension, "cosine"
        )
        restored = 0
        for entry in payload:
            content = entry.get("content", "")
            if not content:
                continue
            memory_id = entry.get("id") or str(uuid.uuid4())
            now = entry.get("updated_at") or datetime.now(timezone.utc).isoformat()
            full_metadata = {
                "content": content,
                "user_metadata": entry.get("metadata") or {},
                "profile_id": entry.get("profile_id"),
                "created_at": entry.get("created_at") or now,
                "updated_at": now,
            }
            embedding = self._embedder.embed(content)
            self._store.insert(
                vectors=[embedding],
                payloads=[full_metadata],
                ids=[memory_id],
            )
            restored += 1
        self._write_schema_version()
        return restored

    def reset(self, archive: bool = True) -> bool:
        """Archive the corrupted DB and start fresh.

        When ``archive`` is True (default) the on-disk DB directory is
        renamed to ``<name>.corrupted.<timestamp>`` so no data is lost.
        Returns ``True`` if the reset completed successfully.
        """
        if not self._is_persistent():
            self._store.reset()
            self._store.create_col(
                self._collection_name, self._embedder.dimension, "cosine"
            )
            return True
        db_path = Path(self._db_path)
        if archive and db_path.exists():
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            archived = db_path.with_name(f"{db_path.name}.corrupted.{ts}")
            try:
                shutil.move(str(db_path), str(archived))
            except OSError:
                shutil.rmtree(str(db_path), ignore_errors=True)
        elif db_path.exists():
            shutil.rmtree(str(db_path), ignore_errors=True)
        db_path.mkdir(parents=True, exist_ok=True)
        self._store = LanceDbVectorStore(
            uri=self._db_path,
            collection_name=self._collection_name,
            vector_dim=self._embedder.dimension,
            distance="cosine",
        )
        self._store.create_col(
            self._collection_name, self._embedder.dimension, "cosine"
        )
        self._write_schema_version()
        return True

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def store_memory(
        self,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        profile_id: Optional[str] = None,
    ) -> MemoryRecord:
        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        full_metadata = {
            "content": content,
            "user_metadata": metadata or {},
            "profile_id": profile_id,
            "created_at": now,
            "updated_at": now,
        }
        embedding = self._embedder.embed(content)
        self._store.insert(
            vectors=[embedding],
            payloads=[full_metadata],
            ids=[memory_id],
        )
        record = MemoryRecord(
            id=memory_id,
            content=content,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self._append_backup(record, profile_id)
        return record

    def retrieve_memories(
        self,
        query: str,
        limit: int = 5,
        profile_id: Optional[str] = None,
    ) -> list[MemoryRecord]:
        query_embedding = self._embedder.embed(query)
        pool_limit = limit * 10 if profile_id is not None else limit
        results = self._store.search(
            query=query,
            vectors=query_embedding,
            top_k=pool_limit,
        )
        records: list[MemoryRecord] = []
        for result in results:
            payload = result.payload
            if profile_id is not None and payload.get("profile_id") != profile_id:
                continue
            records.append(
                MemoryRecord(
                    id=result.id,
                    content=payload.get("content", ""),
                    metadata=payload.get("user_metadata", {}),
                    created_at=payload.get("created_at", ""),
                    updated_at=payload.get("updated_at", ""),
                )
            )
            if len(records) >= limit:
                break
        return records

    def get_memory(
        self,
        memory_id: str,
        profile_id: Optional[str] = None,
    ) -> Optional[MemoryRecord]:
        existing = self._store.get(memory_id)
        if existing is None:
            return None
        payload = existing.payload
        if profile_id is not None and payload.get("profile_id") != profile_id:
            return None
        return MemoryRecord(
            id=memory_id,
            content=payload.get("content", ""),
            metadata=payload.get("user_metadata", {}),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
        )

    def update_memory(
        self,
        memory_id: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        profile_id: Optional[str] = None,
    ) -> Optional[MemoryRecord]:
        existing = self._store.get(memory_id)
        if existing is None:
            return None
        old_payload = existing.payload
        if profile_id is not None and old_payload.get("profile_id") != profile_id:
            return None
        now = datetime.now(timezone.utc).isoformat()
        new_metadata = metadata if metadata is not None else old_payload.get("user_metadata", {})
        full_metadata = {
            "content": content,
            "user_metadata": new_metadata,
            "profile_id": old_payload.get("profile_id"),
            "created_at": old_payload.get("created_at", now),
            "updated_at": now,
        }
        new_embedding = self._embedder.embed(content)
        self._store.update(
            vector_id=memory_id,
            vector=new_embedding,
            payload=full_metadata,
        )
        return MemoryRecord(
            id=memory_id,
            content=content,
            metadata=new_metadata,
            created_at=full_metadata["created_at"],
            updated_at=now,
        )

    def delete_memory(self, memory_id: str, profile_id: Optional[str] = None) -> bool:
        existing = self._store.get(memory_id)
        if existing is None:
            return False
        if profile_id is not None and existing.payload.get("profile_id") != profile_id:
            return False
        self._store.delete(memory_id)
        return True

    def list_memories(self, profile_id: Optional[str] = None) -> list[MemoryRecord]:
        results = self._store.list()
        records: list[MemoryRecord] = []
        for result in results:
            payload = result.payload
            if profile_id is not None and payload.get("profile_id") != profile_id:
                continue
            records.append(
                MemoryRecord(
                    id=result.id,
                    content=payload.get("content", ""),
                    metadata=payload.get("user_metadata", {}),
                    created_at=payload.get("created_at", ""),
                    updated_at=payload.get("updated_at", ""),
                )
            )
        return records

    def delete_memories_for_profile(self, profile_id: str) -> int:
        """Delete all memories owned by ``profile_id``. Returns count removed."""
        removed = 0
        for record in self.list_memories(profile_id=profile_id):
            if self.delete_memory(record.id, profile_id=profile_id):
                removed += 1
        return removed
