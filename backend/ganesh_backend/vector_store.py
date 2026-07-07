"""LanceDB vector store adapter implementing mem0's VectorStoreBase interface.

This adapter bridges LanceDB (a local embedded vector database) with the
mem0 OSS architecture. It implements :class:`mem0.vector_stores.base.VectorStoreBase`
so it can be plugged into mem0's ``Memory`` class when LLM-based memory
extraction is enabled in a future task. For now, the :class:`MemoryService`
uses this adapter directly for explicit CRUD operations.
"""

from __future__ import annotations

from typing import Any, Optional

import lancedb
import pyarrow as pa

try:
    from mem0.vector_stores.base import VectorStoreBase
except ImportError:
    class VectorStoreBase:  # type: ignore[no-redef]
        """Fallback when mem0 is not installed."""

        def create_col(self, name: str, vector_size: int, distance: str) -> None: ...
        def insert(self, vectors: list[list[float]], payloads: Optional[list[dict[str, Any]]] = None, ids: Optional[list[str]] = None) -> None: ...
        def search(self, query: str, vectors: list[float], top_k: int = 5, filters: Optional[dict[str, Any]] = None) -> list[Any]: return []
        def delete(self, vector_id: str) -> None: ...
        def update(self, vector_id: str, vector: Optional[list[float]] = None, payload: Optional[dict[str, Any]] = None) -> None: ...
        def get(self, vector_id: str) -> Optional[Any]: return None
        def list_cols(self) -> list[str]: return []
        def delete_col(self) -> None: ...
        def col_info(self) -> dict[str, Any]: return {}
        def list(self, filters: Optional[dict[str, Any]] = None, top_k: Optional[int] = None) -> list[Any]: return []
        def reset(self) -> None: ...


class OutputData:
    """Normalised result wrapper matching mem0's expected output shape."""

    def __init__(self, id: str, score: float, payload: dict[str, Any]) -> None:
        self.id = id
        self.score = score
        self.payload = payload


class LanceDbVectorStore(VectorStoreBase):  # type: ignore[misc]
    """LanceDB-backed vector store.

    Supports both persistent (on-disk) and in-memory (URI ``":memory:"``)
    modes. In-memory mode is used in tests to avoid touching the filesystem.
    """

    def __init__(
        self,
        uri: str = ":memory:",
        collection_name: str = "ganesh_memories",
        vector_dim: int = 384,
        distance: str = "cosine",
    ) -> None:
        self._uri = uri
        self._collection_name = collection_name
        self._vector_dim = vector_dim
        self._distance = distance
        self._db = lancedb.connect(uri)
        self._table: Any = None

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def _table_list(self) -> list[str]:
        if hasattr(self._db, "list_tables"):
            resp = self._db.list_tables()
            if hasattr(resp, "tables"):
                return list(resp.tables)
            return list(resp)
        return list(self._db.table_names())

    def create_col(self, name: str, vector_size: int, distance: str) -> None:
        self._collection_name = name
        self._vector_dim = vector_size
        self._distance = distance
        existing = self._table_list()
        if name in existing:
            self._table = self._db.open_table(name)
        else:
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), vector_size)),
                pa.field("payload", pa.string()),
            ])
            self._table = self._db.create_table(name, schema=schema)

    def _ensure_table(self) -> Any:
        if self._table is None:
            self.create_col(self._collection_name, self._vector_dim, self._distance)
        return self._table

    def insert(
        self,
        vectors: list[list[float]],
        payloads: Optional[list[dict[str, Any]]] = None,
        ids: Optional[list[str]] = None,
    ) -> None:
        table = self._ensure_table()
        import json

        rows = []
        for i, vec in enumerate(vectors):
            row_id = ids[i] if ids else str(i)
            payload = payloads[i] if payloads else {}
            rows.append({
                "id": row_id,
                "vector": [float(v) for v in vec],
                "payload": json.dumps(payload, default=str),
            })
        table.add(rows)

    def search(
        self,
        query: str,
        vectors: list[float],
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[OutputData]:
        table = self._ensure_table()
        query_vec = [float(v) for v in vectors]
        # NOTE: ``filters`` is accepted for API compatibility but not applied
        # here — LanceDB's json_extract requires a binary payload column.
        # Callers filter results in Python instead.
        results = table.search(query_vec).metric(self._distance).limit(top_k).to_list()
        import json

        out: list[OutputData] = []
        for row in results:
            payload_str = row.get("payload", "{}")
            try:
                payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
            except (json.JSONDecodeError, TypeError):
                payload = {}
            if filters:
                matched = True
                for key, value in filters.items():
                    if payload.get(key) != value:
                        matched = False
                        break
                if not matched:
                    continue
            distance_val = row.get("_distance", 0.0)
            score = max(0.0, 1.0 - distance_val)
            out.append(OutputData(id=str(row["id"]), score=score, payload=payload))
            if len(out) >= top_k:
                break
        return out

    def delete(self, vector_id: str) -> None:
        table = self._ensure_table()
        table.delete(f'id = "{vector_id}"')

    def update(
        self,
        vector_id: str,
        vector: Optional[list[float]] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        self.delete(vector_id)
        if vector is not None:
            self.insert(
                vectors=[vector],
                payloads=[payload or {}],
                ids=[vector_id],
            )

    def get(self, vector_id: str) -> Optional[OutputData]:
        table = self._ensure_table()
        rows = table.search().where(f'id = "{vector_id}"').limit(1).to_list()
        if not rows:
            return None
        import json

        row = rows[0]
        payload_str = row.get("payload", "{}")
        try:
            payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        except (json.JSONDecodeError, TypeError):
            payload = {}
        return OutputData(id=str(row["id"]), score=1.0, payload=payload)

    def list_cols(self) -> list[str]:
        return self._table_list()

    def delete_col(self) -> None:
        try:
            self._db.drop_table(self._collection_name)
        except Exception:
            pass
        self._table = None

    def col_info(self) -> dict[str, Any]:
        table = self._ensure_table()
        return {"name": self._collection_name, "count": table.count_rows()}

    def list(
        self,
        filters: Optional[dict[str, Any]] = None,
        top_k: Optional[int] = None,
    ) -> list[OutputData]:
        table = self._ensure_table()
        query = table.search()
        rows = query.to_list()
        import json

        out: list[OutputData] = []
        for row in rows:
            payload_str = row.get("payload", "{}")
            try:
                payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
            except (json.JSONDecodeError, TypeError):
                payload = {}
            if filters:
                matched = True
                for key, value in filters.items():
                    if payload.get(key) != value:
                        matched = False
                        break
                if not matched:
                    continue
            out.append(OutputData(id=str(row["id"]), score=1.0, payload=payload))
        if top_k:
            out = out[:top_k]
        return out

    def reset(self) -> None:
        self.delete_col()
        self.create_col(self._collection_name, self._vector_dim, self._distance)
