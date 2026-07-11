"""Model manager: first-run model download with resume + checksum verification.

Stores models under ``~/.ganesh/models/`` (override via ``GANESH_DATA_DIR``).
Downloads use HTTP ``Range`` requests to resume from a ``.part`` file.
SHA-256 checksums are verified after the download completes; a mismatch
raises ``ValueError`` and removes the partial file.

Disk-full handling: :meth:`check_disk_space` returns free bytes on the
models partition. :meth:`download_model` catches ``OSError`` with ``ENOSPC``
during writes and transitions the progress to ``status="disk_full"`` so
the UI can prompt the user to clean up or cancel.
"""
from __future__ import annotations

import asyncio
import errno
import hashlib
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from ganesh_backend.services.config import config_service

DEFAULT_MODELS_DIR = Path.home() / ".ganesh" / "models"

CHUNK_SIZE = 64 * 1024

# Safety multiplier: warn if free space < 2x the model size so there's room
# for the .part file plus the final rename.
DISK_SPACE_SAFETY_MULTIPLIER = 2


class DiskFullError(RuntimeError):
    """Raised when the filesystem cannot accommodate the model download."""


@dataclass
class ModelSpec:
    name: str
    url: str
    checksum: str
    description: str
    size: int = 0


REQUIRED_MODELS: dict[str, ModelSpec] = {
    "stt": ModelSpec(
        name="stt.bin",
        url="https://github.com/ganesh-ai/models/releases/download/v0.1/stt.bin",
        checksum="",
        description="Speech-to-text (faster-whisper base)",
        size=0,
    ),
    "tts": ModelSpec(
        name="kokoro-v1.0.onnx",
        url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
        checksum="",
        description="Text-to-speech (Kokoro model)",
        size=0,
    ),
    "voices": ModelSpec(
        name="voices-v1.0.bin",
        url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        checksum="",
        description="Text-to-speech (Kokoro voices)",
        size=0,
    ),
    "embeddings": ModelSpec(
        name="embeddings.bin",
        url="https://github.com/ganesh-ai/models/releases/download/v0.1/embeddings.bin",
        checksum="",
        description="Sentence embeddings (all-MiniLM-L6-v2)",
        size=0,
    ),
}


@dataclass
class DownloadProgress:
    name: str
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    eta: float = 0.0
    status: str = "pending"
    error: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(
        self,
        downloaded: Optional[int] = None,
        total: Optional[int] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
        speed: Optional[float] = None,
        eta: Optional[float] = None,
    ) -> None:
        with self._lock:
            if downloaded is not None:
                self.downloaded = downloaded
            if total is not None:
                self.total = total
            if status is not None:
                self.status = status
            if error is not None:
                self.error = error
            if speed is not None:
                self.speed = speed
            if eta is not None:
                self.eta = eta

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "name": self.name,
                "downloaded": self.downloaded,
                "total": self.total,
                "speed": self.speed,
                "eta": self.eta,
                "status": self.status,
                "error": self.error,
            }


class ModelManager:
    """Manages local model files: presence checks, downloads, progress."""

    def __init__(
        self,
        models_dir: Optional[Path] = None,
        specs: Optional[dict[str, ModelSpec]] = None,
    ) -> None:
        env_dir = os.environ.get("GANESH_DATA_DIR")
        if env_dir:
            self._models_dir = Path(env_dir) / "models"
        else:
            self._models_dir = models_dir or DEFAULT_MODELS_DIR
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._specs = dict(specs) if specs is not None else dict(REQUIRED_MODELS)
        self._progress: dict[str, DownloadProgress] = {
            name: DownloadProgress(name=name) for name in self._specs
        }
        self._pause_events: dict[str, threading.Event] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._tasks: dict[str, "asyncio.Task[object]"] = {}

    def _path_for(self, name: str) -> Path:
        return self._models_dir / self._specs[name].name

    def _part_path_for(self, name: str) -> Path:
        return self._models_dir / f"{self._specs[name].name}.part"

    def check_models(self) -> dict[str, bool]:
        """Return ``{name: present_and_checksum_valid}`` for every required model."""
        result: dict[str, bool] = {}
        for name, spec in self._specs.items():
            path = self._path_for(name)
            if not path.exists():
                result[name] = False
                continue
            if spec.checksum:
                digest = self._sha256_file(path)
                result[name] = digest == spec.checksum
            else:
                result[name] = True
        return result

    def check_disk_space(self) -> dict[str, object]:
        """Return free/total/used bytes on the models partition.

        Also returns ``sufficient`` (bool): True if free bytes >= 2x the
        largest required model size (or unknown-size models). The 2x margin
        guards against the download + decompression peak.
        """
        usage = shutil.disk_usage(self._models_dir)
        max_model_size = max((s.size for s in self._specs.values()), default=0)
        safety_multiplier = config_service.get_setting(
            "model_download.disk_space_safety_multiplier", DISK_SPACE_SAFETY_MULTIPLIER
        )
        threshold = max_model_size * safety_multiplier if max_model_size > 0 else 0
        sufficient = threshold == 0 or usage.free >= threshold
        return {
            "free": usage.free,
            "total": usage.total,
            "used": usage.used,
            "threshold": threshold,
            "sufficient": sufficient,
        }

    def has_space_for(self, name: str) -> tuple[bool, int, int]:
        """Check whether there's enough free space to download ``name``.

        Returns ``(has_space, free_bytes, required_bytes)`` where
        ``required_bytes = spec.size * DISK_SPACE_SAFETY_MULTIPLIER``.
        """
        if name not in self._specs:
            raise KeyError(f"Unknown model: {name}")
        spec = self._specs[name]
        usage = shutil.disk_usage(self._models_dir)
        free = usage.free
        safety_multiplier = config_service.get_setting(
            "model_download.disk_space_safety_multiplier", DISK_SPACE_SAFETY_MULTIPLIER
        )
        required = spec.size * safety_multiplier
        return (free >= required, free, required)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        chunk_size = config_service.get_setting("model_download.chunk_size", CHUNK_SIZE)
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
        return h.hexdigest()

    async def download_model(
        self,
        name: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> bool:
        """Download ``name`` with resume support and verify its SHA-256 checksum.

        Resumes from ``<name>.bin.part`` if present by issuing an HTTP
        ``Range: bytes=<offset>-`` request. On success the ``.part`` file is
        renamed to ``<name>.bin``. On checksum mismatch the partial file is
        deleted and ``ValueError`` is raised.
        """
        if name not in self._specs:
            raise KeyError(f"Unknown model: {name}")
        spec = self._specs[name]
        progress = self._progress[name]
        progress.update(status="downloading", error=None)

        if spec.size > 0:
            space = self.check_disk_space()
            if not space["sufficient"]:
                progress.update(
                    status="disk_full",
                    error=(
                        f"Insufficient disk space: need {space['threshold']} bytes, "
                        f"have {space['free']} bytes. Free space before downloading."
                    ),
                )
                raise DiskFullError(
                    f"Insufficient disk space for {name}: need {space['threshold']}, "
                    f"have {space['free']}"
                )

        part_path = self._part_path_for(name)
        final_path = self._path_for(name)

        own_client = client is None
        cli = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))

        try:
            await self._download_with_resume(spec, part_path, cli, progress)
            if progress.status == "disk_full":
                raise DiskFullError(
                    f"Disk full while downloading {name}: "
                    f"{progress.error or 'no space left on device'}"
                )
            progress.update(status="verifying")
            digest = self._sha256_file(part_path)
            if spec.checksum and digest != spec.checksum:
                part_path.unlink(missing_ok=True)
                progress.update(status="failed", error=f"checksum mismatch: expected {spec.checksum}, got {digest}")
                raise ValueError(
                    f"checksum mismatch for {name}: expected {spec.checksum}, got {digest}"
                )
            part_path.replace(final_path)
            progress.update(status="completed")
            return True
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                progress.update(
                    status="disk_full",
                    error="Disk full. Free space or cancel the download.",
                )
            else:
                progress.update(status="failed", error=str(exc))
            raise
        except httpx.HTTPError as exc:
            progress.update(status="failed", error=str(exc))
            raise
        finally:
            if own_client:
                await cli.aclose()

    async def _download_with_resume(
        self,
        spec: ModelSpec,
        part_path: Path,
        client: httpx.AsyncClient,
        progress: DownloadProgress,
    ) -> None:
        existing = part_path.stat().st_size if part_path.exists() else 0
        headers: dict[str, str] = {}
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"

        async with client.stream("GET", spec.url, headers=headers) as resp:
            if existing > 0 and resp.status_code != 206:
                # Server doesn't support Range — restart from scratch.
                existing = 0
                part_path.unlink(missing_ok=True)
            else:
                resp.raise_for_status()

            content_length = resp.headers.get("Content-Length")
            total = int(content_length) + existing if content_length else (spec.size or 0)
            progress.update(downloaded=existing, total=total)

            mode = "ab" if existing > 0 else "wb"
            start_time = time.monotonic()
            bytes_written = existing
            try:
                f = open(part_path, mode)
            except OSError as exc:
                if exc.errno == errno.ENOSPC:
                    progress.update(
                        status="disk_full",
                        error="Insufficient disk space to write the model file.",
                    )
                    return
                raise
            with f:
                chunk_size = config_service.get_setting(
                    "model_download.chunk_size", CHUNK_SIZE
                )
                async for chunk in resp.aiter_bytes(chunk_size):
                    pause_event = self._pause_events.get(spec.name)
                    while pause_event is not None and pause_event.is_set():
                        progress.update(status="paused")
                        await asyncio.sleep(0.1)
                        if self._cancel_events.get(spec.name) is not None:
                            return
                    cancel_event = self._cancel_events.get(spec.name)
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    try:
                        f.write(chunk)
                    except OSError as exc:
                        if exc.errno == errno.ENOSPC:
                            progress.update(
                                status="disk_full",
                                error="Disk full while writing the model file. "
                                "Free space or cancel the download.",
                            )
                            raise
                        raise
                    bytes_written += len(chunk)
                    elapsed = max(time.monotonic() - start_time, 1e-6)
                    speed = (bytes_written - existing) / elapsed
                    remaining = (total - bytes_written) if total else 0
                    eta = remaining / speed if speed > 0 else 0.0
                    progress.update(
                        downloaded=bytes_written,
                        speed=speed,
                        eta=eta,
                        status="downloading",
                    )

    def get_download_progress(self) -> dict[str, DownloadProgress]:
        return dict(self._progress)

    def get_progress_snapshot(self) -> dict[str, dict[str, object]]:
        return {name: p.snapshot() for name, p in self._progress.items()}

    def pause_download(self, name: str) -> None:
        ev = self._pause_events.setdefault(name, threading.Event())
        ev.set()
        if name in self._progress:
            self._progress[name].update(status="paused")

    def resume_download(self, name: str) -> None:
        ev = self._pause_events.get(name)
        if ev is not None:
            ev.clear()
        if name in self._progress and self._progress[name].status == "paused":
            self._progress[name].update(status="downloading")

    def cancel_download(self, name: str) -> None:
        ev = self._cancel_events.setdefault(name, threading.Event())
        ev.set()
        self.pause_events_get(name).set()

    def pause_events_get(self, name: str) -> threading.Event:
        return self._pause_events.setdefault(name, threading.Event())

    def reset(self, name: Optional[str] = None) -> None:
        """Clear progress / control state for one or all models (test helper)."""
        targets = [name] if name else list(self._progress)
        for n in targets:
            self._progress[n] = DownloadProgress(name=n)
            self._pause_events.pop(n, None)
            self._cancel_events.pop(n, None)


_manager: Optional[ModelManager] = None
_manager_lock = threading.Lock()


def get_model_manager() -> ModelManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = ModelManager()
    return _manager


def reset_model_manager() -> None:
    global _manager
    _manager = None
