"""Provider-neutral private object storage for Nebula protocol artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import BotoCoreError, ClientError

MAX_STORAGE_KEY_BYTES = 1024
MAX_CAPABILITY_TTL_SECONDS = 900


class StorageBackend(Protocol):
    """Private object operations shared by local and durable adapters."""

    async def put_object(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Atomically replace one validated object and return its key."""
        ...

    async def put_object_once(self, key: str, data: bytes, content_type: str | None = None) -> ImmutableWriteResult:
        """Create an immutable object or accept an exact retry."""
        ...

    async def get_object(self, key: str) -> bytes:
        """Read one validated private object."""
        ...

    async def delete_object(self, key: str) -> bool:
        """Delete one validated object and report whether it existed."""
        ...

    async def generate_upload_url(self, key: str, content_type: str, expires_in: int = 300) -> str:
        """Create a bounded upload capability for one exact key."""
        ...

    async def generate_download_url(self, key: str, expires_in: int = 300) -> str:
        """Create a bounded download capability for one exact key."""
        ...


class StorageConfigurationError(ValueError):
    """Raised when a storage adapter cannot be constructed safely."""


class StorageUnavailableError(RuntimeError):
    """Raised when a configured provider cannot complete an object operation."""


@dataclass(frozen=True)
class StorageRuntimeConfig:
    """Provider-neutral runtime inputs for the selected storage adapter."""

    adapter: str
    local_root: str = ""
    bucket: str = ""
    endpoint_url: str = ""
    region: str = ""
    access_key_id: str = field(default="", repr=False)
    secret_access_key: str = field(default="", repr=False)
    key_prefix: str = ""
    capability_ttl_seconds: int = 300


@dataclass(frozen=True)
class ImmutableWriteResult:
    """Ownership result used to keep compensating cleanup safe."""

    key: str
    created: bool


def validate_storage_key(key: str) -> str:
    """Return a canonical relative object key or reject unsafe input."""
    if not key or len(key.encode("utf-8")) > MAX_STORAGE_KEY_BYTES:
        raise ValueError("storage key is empty or exceeds the size limit")
    if key.startswith("/") or "\\" in key or any(ord(char) < 32 for char in key):
        raise ValueError("storage key must be a clean relative POSIX path")
    path = PurePosixPath(key)
    if any(part in ("", ".", "..") for part in key.split("/")) or path.is_absolute():
        raise ValueError("storage key contains an unsafe path segment")
    return str(path)


class InMemoryStorage:
    """Private in-memory adapter for tests."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put_object(self, key: str, data: bytes, content_type: str | None = None) -> str:
        key = validate_storage_key(key)
        self._objects[key] = data
        return key

    async def put_object_once(self, key: str, data: bytes, content_type: str | None = None) -> ImmutableWriteResult:
        key = validate_storage_key(key)
        existing = self._objects.get(key)
        if existing is not None and existing != data:
            raise ValueError("immutable object already exists with different bytes")
        created = existing is None
        self._objects[key] = data
        return ImmutableWriteResult(key=key, created=created)

    async def get_object(self, key: str) -> bytes:
        key = validate_storage_key(key)
        if key not in self._objects:
            raise KeyError(f"Object not found: {key}")
        return self._objects[key]

    async def delete_object(self, key: str) -> bool:
        key = validate_storage_key(key)
        return self._objects.pop(key, None) is not None

    async def generate_upload_url(self, key: str, content_type: str, expires_in: int = 300) -> str:
        key = validate_storage_key(key)
        return f"fake://storage/upload/{key}?content_type={content_type}&expires={expires_in}"

    async def generate_download_url(self, key: str, expires_in: int = 300) -> str:
        key = validate_storage_key(key)
        return f"fake://storage/download/{key}?expires={expires_in}"


class FileStorage:
    """Private local-development storage with atomic immutable writes."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        key = validate_storage_key(key)
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("storage key escapes configured root")
        return path

    async def put_object(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def put_object_once(self, key: str, data: bytes, content_type: str | None = None) -> ImmutableWriteResult:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        created = False
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".upload-", delete=False) as handle:
                temporary_name = handle.name
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_name, path)
                created = True
            except FileExistsError:
                if path.read_bytes() != data:
                    raise ValueError("immutable object already exists with different bytes") from None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
        return ImmutableWriteResult(key=key, created=created)

    async def get_object(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def delete_object(self, key: str) -> bool:
        path = self._path(key)
        if not path.exists():
            return False
        path.unlink()
        return True

    async def generate_upload_url(self, key: str, content_type: str, expires_in: int = 300) -> str:
        validate_storage_key(key)
        raise NotImplementedError("local storage is accessed through authenticated backend routes")

    async def generate_download_url(self, key: str, expires_in: int = 300) -> str:
        validate_storage_key(key)
        raise NotImplementedError("local storage is accessed through authenticated backend routes")


class S3Storage:
    """Private durable adapter for S3-compatible object stores such as R2."""

    def __init__(self, config: StorageRuntimeConfig, *, client: Any | None = None) -> None:
        _validate_remote_config(config)
        self._bucket = config.bucket
        self._prefix = config.key_prefix.strip("/")
        self._maximum_ttl = config.capability_ttl_seconds
        self._client = client or boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            region_name=config.region,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
        )

    def _remote_key(self, key: str) -> str:
        key = validate_storage_key(key)
        return f"{self._prefix}/{key}" if self._prefix else key

    async def put_object(self, key: str, data: bytes, content_type: str | None = None) -> str:
        remote_key = self._remote_key(key)
        request: dict[str, Any] = {"Bucket": self._bucket, "Key": remote_key, "Body": data}
        if content_type:
            request["ContentType"] = content_type
        try:
            await asyncio.to_thread(self._client.put_object, **request)
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("durable object write failed") from exc
        return key

    async def put_object_once(self, key: str, data: bytes, content_type: str | None = None) -> ImmutableWriteResult:
        remote_key = self._remote_key(key)
        request: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": remote_key,
            "Body": data,
            "IfNoneMatch": "*",
        }
        if content_type:
            request["ContentType"] = content_type
        created = True
        try:
            await asyncio.to_thread(self._client.put_object, **request)
        except ClientError as exc:
            if _error_code(exc) not in {"409", "412", "ConditionalRequestConflict", "PreconditionFailed"}:
                raise StorageUnavailableError("durable immutable object write failed") from exc
            if await self.get_object(key) != data:
                raise ValueError("immutable object already exists with different bytes") from None
            created = False
        except BotoCoreError as exc:
            raise StorageUnavailableError("durable immutable object write failed") from exc
        return ImmutableWriteResult(key=key, created=created)

    async def get_object(self, key: str) -> bytes:
        remote_key = self._remote_key(key)

        def read() -> bytes:
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=remote_key)
            except ClientError as exc:
                if _error_code(exc) in {"404", "NoSuchKey", "NotFound"}:
                    raise KeyError(f"Object not found: {key}") from None
                raise StorageUnavailableError("durable object read failed") from exc
            except BotoCoreError as exc:
                raise StorageUnavailableError("durable object read failed") from exc
            body = response["Body"]
            try:
                try:
                    return cast(bytes, body.read())
                except (BotoCoreError, OSError) as exc:
                    raise StorageUnavailableError("durable object body read failed") from exc
            finally:
                close = getattr(body, "close", None)
                if close:
                    close()

        return await asyncio.to_thread(read)

    async def delete_object(self, key: str) -> bool:
        remote_key = self._remote_key(key)
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=remote_key)
        except ClientError as exc:
            if _error_code(exc) in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise StorageUnavailableError("durable object existence check failed") from exc
        except BotoCoreError as exc:
            raise StorageUnavailableError("durable object existence check failed") from exc
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=remote_key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("durable object cleanup failed") from exc
        return True

    async def generate_upload_url(self, key: str, content_type: str, expires_in: int = 300) -> str:
        ttl = self._capability_ttl(expires_in)
        params = {"Bucket": self._bucket, "Key": self._remote_key(key), "ContentType": content_type}
        try:
            return cast(
                str,
                await asyncio.to_thread(
                    self._client.generate_presigned_url,
                    "put_object",
                    Params=params,
                    ExpiresIn=ttl,
                ),
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("durable upload capability creation failed") from exc

    async def generate_download_url(self, key: str, expires_in: int = 300) -> str:
        ttl = self._capability_ttl(expires_in)
        params = {"Bucket": self._bucket, "Key": self._remote_key(key)}
        try:
            return cast(
                str,
                await asyncio.to_thread(
                    self._client.generate_presigned_url,
                    "get_object",
                    Params=params,
                    ExpiresIn=ttl,
                ),
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("durable download capability creation failed") from exc

    def _capability_ttl(self, requested: int) -> int:
        if requested <= 0 or requested > self._maximum_ttl:
            raise ValueError("capability expiry exceeds the configured bounded lifetime")
        return requested


def _error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def _validate_remote_config(config: StorageRuntimeConfig) -> None:
    required = (config.bucket, config.endpoint_url, config.region, config.access_key_id, config.secret_access_key)
    if not all(required):
        raise StorageConfigurationError("durable storage configuration is incomplete")
    parsed = urlsplit(config.endpoint_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise StorageConfigurationError("storage endpoint must be a credential-free HTTPS origin")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise StorageConfigurationError("storage endpoint must not include a path, query, or fragment")
    if not 1 <= config.capability_ttl_seconds <= MAX_CAPABILITY_TTL_SECONDS:
        raise StorageConfigurationError("storage capability TTL is outside the allowed range")
    if config.key_prefix:
        validate_storage_key(config.key_prefix.strip("/"))


def build_storage(config: StorageRuntimeConfig, *, client: Any | None = None) -> StorageBackend:
    """Build exactly one configured adapter; unsupported profiles fail closed."""
    if config.adapter == "file":
        if not config.local_root:
            raise StorageConfigurationError("file storage requires an explicit local root")
        return FileStorage(config.local_root)
    if config.adapter == "s3":
        return S3Storage(config, client=client)
    raise StorageConfigurationError(f"unsupported storage adapter: {config.adapter!r}")


def storage_config_from_settings(settings: Any) -> StorageRuntimeConfig:
    """Translate application settings into the provider-neutral storage contract."""
    return StorageRuntimeConfig(
        adapter=settings.STORAGE_ADAPTER,
        local_root=settings.LOCAL_STORAGE_PATH,
        bucket=settings.R2_BUCKET_NAME,
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if settings.R2_ACCOUNT_ID else "",
        region=settings.OBJECT_STORAGE_REGION,
        access_key_id=settings.R2_ACCESS_KEY_ID,
        secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        key_prefix=settings.OBJECT_STORAGE_PREFIX,
        capability_ttl_seconds=settings.OBJECT_STORAGE_CAPABILITY_TTL_SECONDS,
    )


def compute_object_hash(data: bytes) -> str:
    """Compute the protocol SHA-256 digest from accepted bytes."""
    return hashlib.sha256(data).hexdigest()


def make_input_key(job_id: str, filename: str) -> str:
    """Build a validated accepted-input object key."""
    return validate_storage_key(f"inputs/{job_id}/{filename}")


def make_model_key(model_id: str, filename: str) -> str:
    """Build a validated model-artifact object key."""
    return validate_storage_key(f"models/{model_id}/{filename}")


def make_result_key(job_id: str, attempt_id: str) -> str:
    """Build a validated immutable result object key."""
    return validate_storage_key(f"results/{job_id}/{attempt_id}/output")


def make_proof_key(job_id: str, attempt_id: str) -> str:
    """Build a validated proof-envelope object key."""
    return validate_storage_key(f"proofs/{job_id}/{attempt_id}/envelope.json")
