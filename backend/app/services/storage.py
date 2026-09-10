"""
backend/app/services/storage.py

Cloud storage service for Zentrax — uploads generated design assets
to AWS S3 and returns public (or signed) URLs. Swap the backend for
Cloudinary by implementing the same StorageBackend interface if needed.
"""

import logging
import mimetypes
import uuid
from abc import ABC, abstractmethod
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger("zentrax.storage")


class StorageError(Exception):
    """Raised when an upload/delete to the storage backend fails."""


class StorageBackend(ABC):
    """Interface any storage provider (S3, Cloudinary, GCS...) must implement."""

    @abstractmethod
    async def upload(self, content: bytes, key: str, content_type: str) -> str:
        """Upload bytes and return a publicly accessible (or signed) URL."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError


class S3StorageBackend(StorageBackend):
    """
    AWS S3-backed storage. Requires these settings (add to config.py /
    .env): AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
    AWS_S3_BUCKET, and optionally AWS_S3_PUBLIC_BASE_URL (CDN/CloudFront
    domain) if you don't want raw S3 URLs.
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        public_base_url: Optional[str] = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._public_base_url = public_base_url or f"https://{bucket}.s3.{region}.amazonaws.com"

        # boto3 will also happily pick up credentials from the environment
        # or an IAM role — passing them explicitly here is optional.
        self._client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    async def upload(self, content: bytes, key: str, content_type: str = "image/png") -> str:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                ACL="public-read",
                CacheControl="public, max-age=31536000, immutable",
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("S3 upload failed for key=%s: %s", key, exc)
            raise StorageError(f"Failed to upload asset to S3: {exc}") from exc

        return f"{self._public_base_url}/{key}"

    async def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            logger.error("S3 delete failed for key=%s: %s", key, exc)
            raise StorageError(f"Failed to delete asset from S3: {exc}") from exc


class CloudinaryStorageBackend(StorageBackend):
    """
    Cloudinary-backed storage — alternative to S3, useful for built-in
    image transformations (thumbnails, resizing) on the fly.
    Requires `cloudinary` package and CLOUDINARY_URL env var.
    """

    def __init__(self) -> None:
        import cloudinary  # local import: only required if this backend is used
        import cloudinary.uploader

        self._cloudinary = cloudinary
        self._uploader = cloudinary.uploader

    async def upload(self, content: bytes, key: str, content_type: str = "image/png") -> str:
        try:
            result = self._uploader.upload(
                content,
                public_id=key,
                resource_type="image",
                overwrite=True,
            )
        except Exception as exc:  # cloudinary raises generic Error
            logger.error("Cloudinary upload failed for key=%s: %s", key, exc)
            raise StorageError(f"Failed to upload asset to Cloudinary: {exc}") from exc

        return result["secure_url"]

    async def delete(self, key: str) -> None:
        try:
            self._uploader.destroy(key)
        except Exception as exc:
            logger.error("Cloudinary delete failed for key=%s: %s", key, exc)
            raise StorageError(f"Failed to delete asset from Cloudinary: {exc}") from exc


class StorageService:
    """
    High-level, provider-agnostic service used by the rest of the app.
    Generates namespaced keys and delegates to whichever backend is
    configured, so endpoints/business logic never touch boto3/cloudinary
    directly.
    """

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    async def save_generated_asset(
        self,
        content: bytes,
        design_type: str,
        content_type: str = "image/png",
        thumbnail: bool = False,
    ) -> str:
        """
        Uploads a generated image and returns its public URL.
        Keys are namespaced as: generated/{design_type}/{uuid}[_thumb].{ext}
        """
        ext = mimetypes.guess_extension(content_type) or ".png"
        suffix = "_thumb" if thumbnail else ""
        key = f"generated/{design_type}/{uuid.uuid4().hex}{suffix}{ext}"

        try:
            return await self._backend.upload(content, key, content_type)
        except StorageError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to store generated asset. Please try again.",
            )

    async def delete_asset(self, key: str) -> None:
        try:
            await self._backend.delete(key)
        except StorageError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to delete asset.",
            )


def get_storage_service() -> StorageService:
    """
    FastAPI dependency factory: Depends(get_storage_service)

    Reads STORAGE_BACKEND from settings ("s3" | "cloudinary") to decide
    which backend to instantiate. Add these fields to Settings in
    config.py:
        STORAGE_BACKEND: str = "s3"
        AWS_ACCESS_KEY_ID: str | None = None
        AWS_SECRET_ACCESS_KEY: str | None = None
        AWS_REGION: str = "us-east-1"
        AWS_S3_BUCKET: str | None = None
        AWS_S3_PUBLIC_BASE_URL: str | None = None
        CLOUDINARY_URL: str | None = None
    """
    backend_name = getattr(settings, "STORAGE_BACKEND", "s3").lower()

    if backend_name == "cloudinary":
        backend: StorageBackend = CloudinaryStorageBackend()
    else:
        if not getattr(settings, "AWS_S3_BUCKET", None):
            raise RuntimeError("AWS_S3_BUCKET must be set to use the S3 storage backend.")
        backend = S3StorageBackend(
            bucket=settings.AWS_S3_BUCKET,
            region=settings.AWS_REGION,
            access_key_id=settings.AWS_ACCESS_KEY_ID,
            secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            public_base_url=getattr(settings, "AWS_S3_PUBLIC_BASE_URL", None),
        )

    return StorageService(backend)