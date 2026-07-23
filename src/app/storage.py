from __future__ import annotations

from io import BytesIO
from typing import Protocol

from minio import Minio

from app.core.config import get_settings


class Storage(Protocol):
    def put(self, object_key: str, content: bytes, content_type: str = "text/markdown") -> None: ...
    def get(self, object_key: str) -> bytes: ...
    def delete(self, object_key: str) -> None: ...
    def presign(self, object_key: str) -> str: ...
    def healthy(self) -> bool: ...


class MinioStorage:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def _ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, object_key: str, content: bytes, content_type: str = "text/markdown") -> None:
        self._ensure_bucket()
        self.client.put_object(self.bucket, object_key, BytesIO(content), len(content), content_type=content_type)

    def get(self, object_key: str) -> bytes:
        response = self.client.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, object_key: str) -> None:
        self.client.remove_object(self.bucket, object_key)

    def presign(self, object_key: str) -> str:
        return self.client.presigned_get_object(self.bucket, object_key)

    def healthy(self) -> bool:
        try:
            return self.client.bucket_exists(self.bucket)
        except Exception:
            return False


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, object_key: str, content: bytes, content_type: str = "text/markdown") -> None:
        self.objects[object_key] = content

    def get(self, object_key: str) -> bytes:
        return self.objects[object_key]

    def delete(self, object_key: str) -> None:
        self.objects.pop(object_key, None)

    def presign(self, object_key: str) -> str:
        return f"memory://{object_key}"

    def healthy(self) -> bool:
        return True


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = MinioStorage()
    return _storage


def set_storage(storage: Storage | None) -> None:
    global _storage
    _storage = storage
