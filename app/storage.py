"""Файловое хранилище (S3/MinIO). Ключи иммутабельны: существующий ключ не перезаписывается."""
from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from .domain.errors import StorageUnavailable


class KeyExists(Exception):
    pass


class BlobStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def presigned_url(self, key: str, expires_seconds: int = 3600) -> str: ...


def raw_key(ext: str = "jpg") -> str:
    return f"raw/{uuid4()}.{ext}"


def sketch_key(sketch_id: str, *, thumbnail: bool = False) -> str:
    return f"sketches/{sketch_id}_thumb.jpg" if thumbnail else f"sketches/{sketch_id}.png"


class InMemoryStorage:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        if key in self.objects:
            raise KeyExists(key)
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        return self.objects[key][0]

    def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        return f"memory://{key}?expires={expires_seconds}"


class S3Storage:
    def __init__(self, endpoint_url: str | None, access_key: str | None, secret_key: str | None,
                 bucket: str, region: str = "us-east-1"):
        import boto3
        from botocore.config import Config

        self._bucket = bucket
        self._client = boto3.client(
            "s3", endpoint_url=endpoint_url, aws_access_key_id=access_key,
            aws_secret_access_key=secret_key, region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                          connect_timeout=3, read_timeout=10, retries={"max_attempts": 2}),
        )

    def _exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put(self, key: str, data: bytes, content_type: str) -> None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            if self._exists(key):
                raise KeyExists(key)
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailable() from exc

    def get(self, key: str) -> bytes:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailable() from exc

    def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires_seconds
        )

    def ensure_bucket(self) -> None:
        """Для dev-окружения: создать bucket, если его нет."""
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
