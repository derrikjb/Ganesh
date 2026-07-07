"""Pluggable embedding providers for the memory layer.

Embeddings are generated locally — no cloud API calls. The default provider
is ``sentence-transformers`` (lazy-imported so the heavy torch dependency is
only loaded when actually needed). A deterministic ``HashEmbedder`` is
provided for tests and offline environments where model downloads are not
desirable.

All embedders conform to :class:`EmbedderProtocol` so the memory service can
accept any implementation without coupling to a specific library.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Protocol, runtime_checkable, Any

DEFAULT_EMBEDDING_DIM = 384
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Interface for embedding providers used by the memory service."""

    @property
    def dimension(self) -> int:
        """Dimensionality of the embedding vectors."""
        ...

    def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for ``text``."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        ...


class HashEmbedder:
    """Deterministic embedding provider using SHA-256 hashing.

    Produces fixed-dimensional vectors from text via hashing. No model
    downloads, no external services, fully deterministic — ideal for tests
    and offline environments. Vectors are L2-normalised so cosine
    similarity in LanceDB produces meaningful rankings.
    """

    def __init__(self, dimension: int = DEFAULT_EMBEDDING_DIM) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        text_bytes = text.encode("utf-8")
        offset = 0
        for i in range(self._dimension):
            # Mix dimension index into the hash so adjacent dimensions diverge.
            chunk = struct.pack(">I", i) + text_bytes[offset:offset + 8]
            digest = hashlib.sha256(chunk).digest()
            val = struct.unpack(">q", digest[:8])[0]
            vec[i] = val / 2**63
            offset += 4
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class SentenceTransformerEmbedder:
    """Embedding provider backed by ``sentence-transformers``.

    The ``sentence-transformers`` library (and its torch dependency) is
    lazy-imported on first use so that environments without it can still
    import this module. The default model is ``all-MiniLM-L6-v2`` which
    produces 384-dimensional vectors and downloads automatically on first
    use from HuggingFace Hub.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        dimension: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        self._model_name = model_name
        self._dimension = dimension
        self._model: object | None = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self._model_name)
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        model = self._load()
        vec = model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vecs = model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in v] for v in vecs]


def create_default_embedder() -> EmbedderProtocol:
    """Create the default embedder for production use.

    Falls back to :class:`HashEmbedder` if ``sentence-transformers`` is not
    installed, so the service degrades gracefully in minimal environments.
    """
    try:
        import sentence_transformers  # noqa: F401, type: ignore[import-untyped]

        return SentenceTransformerEmbedder()
    except ImportError:
        return HashEmbedder()
