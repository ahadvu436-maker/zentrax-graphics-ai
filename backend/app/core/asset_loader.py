"""
asset_loader.py
----------------
Asynchronous loading and caching of 3D models, textures, and media assets
for the ZentraX graphics backend.

Design goals:
  - Non-blocking I/O (asyncio + aiofiles) so the render pipeline and
    websocket streams never stall on disk/network fetches.
  - A bounded, thread/coroutine-safe LRU cache to keep memory use predictable.
  - Pluggable "upload hooks" so a GPU/graphics backend can transform raw
    bytes into GPU-resident handles without this module knowing about GPUs.
  - Clear, typed error hierarchy so callers can distinguish between
    "not found", "corrupt", and "transient" failures and react accordingly.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

try:
    import aiofiles
except ImportError:  # pragma: no cover - surfaced clearly at runtime
    aiofiles = None

logger = logging.getLogger("zentrax.asset_loader")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class AssetError(Exception):
    """Base class for all asset-related failures."""


class AssetNotFoundError(AssetError):
    """Raised when the requested asset does not exist at the given path."""


class AssetLoadError(AssetError):
    """Raised when an asset exists but fails to load or decode."""


class AssetTooLargeError(AssetError):
    """Raised when an asset exceeds the configured size limit."""


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------

class AssetType(str, Enum):
    MODEL = "model"
    TEXTURE = "texture"
    AUDIO = "audio"
    VIDEO = "video"
    OTHER = "other"

    @classmethod
    def from_suffix(cls, suffix: str) -> "AssetType":
        suffix = suffix.lower().lstrip(".")
        model_ext = {"gltf", "glb", "fbx", "obj", "usdz", "usd"}
        texture_ext = {"png", "jpg", "jpeg", "ktx", "ktx2", "basis", "dds", "hdr"}
        audio_ext = {"wav", "mp3", "ogg", "flac"}
        video_ext = {"mp4", "webm", "mov", "hls"}
        if suffix in model_ext:
            return cls.MODEL
        if suffix in texture_ext:
            return cls.TEXTURE
        if suffix in audio_ext:
            return cls.AUDIO
        if suffix in video_ext:
            return cls.VIDEO
        return cls.OTHER


@dataclass
class AssetMetadata:
    path: str
    asset_type: AssetType
    size_bytes: int
    checksum: str
    loaded_at: float = field(default_factory=time.time)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CachedAsset:
    metadata: AssetMetadata
    data: Any  # raw bytes, or an uploaded GPU handle if an upload hook ran
    last_accessed: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_accessed = time.time()


# A hook that turns raw bytes into whatever representation the renderer
# wants (e.g. a GPU texture handle). Must be a coroutine.
UploadHook = Callable[[AssetType, bytes, AssetMetadata], Awaitable[Any]]


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

class AssetCache:
    """A bounded, coroutine-safe LRU cache keyed by resolved asset path."""

    def __init__(self, max_size_bytes: int = 512 * 1024 * 1024):
        self._max_size_bytes = max_size_bytes
        self._current_size_bytes = 0
        self._store: "Dict[str, CachedAsset]" = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CachedAsset]:
        async with self._lock:
            asset = self._store.get(key)
            if asset is not None:
                asset.touch()  # eviction uses last_accessed, so touching is enough
            return asset

    async def put(self, key: str, asset: CachedAsset) -> None:
        async with self._lock:
            if key in self._store:
                self._current_size_bytes -= self._store[key].metadata.size_bytes
            self._store[key] = asset
            self._current_size_bytes += asset.metadata.size_bytes
            await self._evict_if_needed_locked()

    async def invalidate(self, key: str) -> None:
        async with self._lock:
            existing = self._store.pop(key, None)
            if existing:
                self._current_size_bytes -= existing.metadata.size_bytes

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            self._current_size_bytes = 0

    async def _evict_if_needed_locked(self) -> None:
        """Caller must hold self._lock. Evicts least-recently-used entries."""
        if self._current_size_bytes <= self._max_size_bytes:
            return
        # Sort by last_accessed ascending; evict oldest first.
        for key in sorted(self._store, key=lambda k: self._store[k].last_accessed):
            if self._current_size_bytes <= self._max_size_bytes:
                break
            evicted = self._store.pop(key)
            self._current_size_bytes -= evicted.metadata.size_bytes
            logger.debug("Evicted asset %s from cache (LRU)", key)

    @property
    def size_bytes(self) -> int:
        return self._current_size_bytes

    @property
    def count(self) -> int:
        return len(self._store)


# --------------------------------------------------------------------------
# Loader
# --------------------------------------------------------------------------

class AssetLoader:
    """
    Loads assets from disk (or a remote source, via a pluggable fetcher)
    asynchronously, with retries, size limits, and LRU caching.
    """

    def __init__(
        self,
        base_path: Optional[str] = None,
        cache: Optional[AssetCache] = None,
        max_concurrent_loads: int = 8,
        max_asset_size_bytes: int = 256 * 1024 * 1024,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.25,
        upload_hook: Optional[UploadHook] = None,
    ):
        self._base_path = Path(base_path) if base_path else None
        self.cache = cache or AssetCache()
        self._semaphore = asyncio.Semaphore(max_concurrent_loads)
        self._max_asset_size_bytes = max_asset_size_bytes
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._upload_hook = upload_hook
        # Prevents duplicate concurrent loads of the same asset ("thundering herd").
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._in_flight_lock = asyncio.Lock()

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if self._base_path and not p.is_absolute():
            p = self._base_path / p
        return p

    @staticmethod
    def _checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    async def load(self, path: str, *, force_reload: bool = False) -> CachedAsset:
        """
        Load an asset by path, returning a CachedAsset. Concurrent callers
        requesting the same path share a single in-flight load.
        """
        key = str(self._resolve_path(path))

        if not force_reload:
            cached = await self.cache.get(key)
            if cached is not None:
                logger.debug("Cache hit for asset %s", key)
                return cached

        async with self._in_flight_lock:
            future = self._in_flight.get(key)
            if future is None:
                future = asyncio.ensure_future(self._load_uncached(key, path))
                self._in_flight[key] = future

        try:
            return await future
        finally:
            async with self._in_flight_lock:
                self._in_flight.pop(key, None)

    async def load_model(self, path: str, **kwargs) -> CachedAsset:
        return await self._load_typed(path, AssetType.MODEL, **kwargs)

    async def load_texture(self, path: str, **kwargs) -> CachedAsset:
        return await self._load_typed(path, AssetType.TEXTURE, **kwargs)

    async def load_media(self, path: str, **kwargs) -> CachedAsset:
        """Loads audio or video; type is inferred from the file suffix."""
        return await self.load(path, **kwargs)

    async def _load_typed(self, path: str, expected_type: AssetType, **kwargs) -> CachedAsset:
        asset = await self.load(path, **kwargs)
        if asset.metadata.asset_type != expected_type:
            logger.warning(
                "Asset %s loaded as %s but %s was requested",
                path, asset.metadata.asset_type, expected_type,
            )
        return asset

    async def _load_uncached(self, key: str, original_path: str) -> CachedAsset:
        async with self._semaphore:
            last_error: Optional[Exception] = None
            for attempt in range(1, self._max_retries + 1):
                try:
                    return await self._read_and_prepare(key, original_path)
                except AssetNotFoundError:
                    raise  # Not retryable.
                except AssetTooLargeError:
                    raise  # Not retryable.
                except AssetError as exc:
                    last_error = exc
                    logger.warning(
                        "Load attempt %d/%d failed for %s: %s",
                        attempt, self._max_retries, key, exc,
                    )
                    if attempt < self._max_retries:
                        await asyncio.sleep(self._retry_backoff_seconds * attempt)
            raise AssetLoadError(
                f"Failed to load asset '{original_path}' after {self._max_retries} attempts"
            ) from last_error

    async def _read_and_prepare(self, key: str, original_path: str) -> CachedAsset:
        resolved = self._resolve_path(original_path)

        if not resolved.exists():
            raise AssetNotFoundError(f"Asset not found: {resolved}")

        size_bytes = resolved.stat().st_size
        if size_bytes > self._max_asset_size_bytes:
            raise AssetTooLargeError(
                f"Asset '{resolved}' is {size_bytes} bytes, "
                f"exceeds limit of {self._max_asset_size_bytes}"
            )

        try:
            data = await self._read_bytes(resolved)
        except AssetError:
            raise
        except Exception as exc:
            raise AssetLoadError(f"Failed reading '{resolved}': {exc}") from exc

        asset_type = AssetType.from_suffix(resolved.suffix)
        metadata = AssetMetadata(
            path=str(resolved),
            asset_type=asset_type,
            size_bytes=len(data),
            checksum=self._checksum(data),
        )

        payload: Any = data
        if self._upload_hook is not None:
            try:
                payload = await self._upload_hook(asset_type, data, metadata)
            except Exception as exc:
                raise AssetLoadError(
                    f"Upload hook failed for '{resolved}': {exc}"
                ) from exc

        cached_asset = CachedAsset(metadata=metadata, data=payload)
        await self.cache.put(key, cached_asset)
        logger.info(
            "Loaded asset %s (%s, %d bytes)",
            resolved, asset_type.value, metadata.size_bytes,
        )
        return cached_asset

    @staticmethod
    async def _read_bytes(path: Path) -> bytes:
        if aiofiles is not None:
            async with aiofiles.open(path, "rb") as f:
                return await f.read()
        # Fallback if aiofiles isn't installed: run blocking read in a thread
        # so we still don't block the event loop.
        return await asyncio.to_thread(path.read_bytes)

    async def preload(self, paths: list[str]) -> Dict[str, CachedAsset]:
        """Load many assets concurrently; failures are collected, not raised."""
        results: Dict[str, CachedAsset] = {}

        async def _load_one(p: str) -> None:
            try:
                results[p] = await self.load(p)
            except AssetError as exc:
                logger.error("Preload failed for %s: %s", p, exc)

        await asyncio.gather(*(_load_one(p) for p in paths))
        return results
