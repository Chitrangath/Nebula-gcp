"""Contract tests for provider-neutral local and durable object storage."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.services.storage import (
    FileStorage,
    S3Storage,
    StorageConfigurationError,
    StorageRuntimeConfig,
    StorageUnavailableError,
    build_storage,
    make_input_key,
    make_model_key,
    make_proof_key,
    make_result_key,
)


@pytest.fixture(autouse=True)
def _override_get_db() -> None:
    """This unit suite does not need the repository's async database fixture."""


class FakeS3Client:
    """Small shared-state S3 fake; no credentials or network are involved."""

    def __init__(self, objects: dict[tuple[str, str], bytes] | None = None) -> None:
        self.objects = objects if objects is not None else {}
        self.put_calls: list[dict[str, Any]] = []
        self.presign_calls: list[tuple[str, dict[str, Any], int]] = []
        self.fail_next_put = False

    def put_object(self, **kwargs: Any) -> None:
        self.put_calls.append(kwargs)
        if self.fail_next_put:
            self.fail_next_put = False
            raise EndpointConnectionError(endpoint_url="https://storage.invalid")
        object_id = (kwargs["Bucket"], kwargs["Key"])
        if kwargs.get("IfNoneMatch") == "*" and object_id in self.objects:
            raise ClientError(
                {"Error": {"Code": "PreconditionFailed", "Message": "exists"}},
                "PutObject",
            )
        self.objects[object_id] = kwargs["Body"]

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        object_id = (kwargs["Bucket"], kwargs["Key"])
        if object_id not in self.objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "GetObject",
            )
        return {"Body": io.BytesIO(self.objects[object_id])}

    def delete_object(self, **kwargs: Any) -> None:
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)

    def head_object(self, **kwargs: Any) -> None:
        if (kwargs["Bucket"], kwargs["Key"]) not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "missing"}},
                "HeadObject",
            )

    def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        params = kwargs["Params"]
        expires_in = kwargs["ExpiresIn"]
        self.presign_calls.append((operation, params, expires_in))
        return f"https://capability.invalid/{operation}/{params['Key']}"


def remote_config() -> StorageRuntimeConfig:
    return StorageRuntimeConfig(
        adapter="s3",
        bucket="nebula-demo-private",
        endpoint_url="https://example-account.r2.cloudflarestorage.com",
        region="auto",
        access_key_id="fake-access-key",
        secret_access_key="fake-secret-key",
        key_prefix="demo",
        capability_ttl_seconds=120,
    )


@pytest.mark.asyncio
async def test_file_storage_remains_compatible_for_every_nebula_object_type(
    tmp_path: Path,
) -> None:
    storage = FileStorage(tmp_path)
    keys = (
        make_input_key("job-1", "input.png"),
        make_model_key("resnet50", "model.pt"),
        make_result_key("job-1", "attempt-1"),
        make_proof_key("job-1", "attempt-1"),
    )

    for index, key in enumerate(keys):
        payload = f"object-{index}".encode()
        assert await storage.put_object(key, payload) == key
        assert await storage.get_object(key) == payload
        assert await storage.delete_object(key) is True


@pytest.mark.asyncio
async def test_remote_objects_are_private_and_capabilities_are_exact_and_short_lived() -> None:
    client = FakeS3Client()
    storage = S3Storage(remote_config(), client=client)
    key = make_input_key("job-1", "input.png")

    await storage.put_object(key, b"input", "image/png")
    upload = await storage.generate_upload_url(key, "image/png", expires_in=60)
    download = await storage.generate_download_url(key, expires_in=60)

    assert "ACL" not in client.put_calls[0]
    assert client.put_calls[0]["Bucket"] == "nebula-demo-private"
    assert client.put_calls[0]["Key"] == "demo/inputs/job-1/input.png"
    assert upload.startswith("https://capability.invalid/put_object/")
    assert download.startswith("https://capability.invalid/get_object/")
    assert client.presign_calls == [
        (
            "put_object",
            {
                "Bucket": "nebula-demo-private",
                "Key": "demo/inputs/job-1/input.png",
                "ContentType": "image/png",
            },
            60,
        ),
        (
            "get_object",
            {"Bucket": "nebula-demo-private", "Key": "demo/inputs/job-1/input.png"},
            60,
        ),
    ]


@pytest.mark.asyncio
async def test_remote_put_once_is_idempotent_but_rejects_different_bytes() -> None:
    storage = S3Storage(remote_config(), client=FakeS3Client())
    key = make_result_key("job-1", "attempt-1")

    first = await storage.put_object_once(key, b"same")
    retry = await storage.put_object_once(key, b"same")
    assert (first.key, first.created) == (key, True)
    assert (retry.key, retry.created) == (key, False)
    with pytest.raises(ValueError, match="different bytes"):
        await storage.put_object_once(key, b"different")


@pytest.mark.asyncio
async def test_remote_failed_write_leaves_no_partial_object() -> None:
    client = FakeS3Client()
    client.fail_next_put = True
    storage = S3Storage(remote_config(), client=client)
    key = make_result_key("job-1", "attempt-1")

    with pytest.raises(StorageUnavailableError, match="write failed"):
        await storage.put_object(key, b"partial")
    assert client.objects == {}


@pytest.mark.asyncio
async def test_transport_outages_are_normalized_across_remote_operations() -> None:
    def outage(*args: Any, **kwargs: Any) -> None:
        raise EndpointConnectionError(endpoint_url="https://storage.invalid")

    key = make_input_key("job-1", "input.png")
    for operation in ("put_object", "get_object", "head_object", "generate_presigned_url"):
        client = FakeS3Client()
        setattr(client, operation, outage)
        storage = S3Storage(remote_config(), client=client)
        with pytest.raises(StorageUnavailableError):
            if operation == "put_object":
                await storage.put_object_once(key, b"input")
            elif operation == "get_object":
                await storage.get_object(key)
            elif operation == "head_object":
                await storage.delete_object(key)
            else:
                await storage.generate_download_url(key, expires_in=60)


@pytest.mark.asyncio
async def test_service_side_write_and_delete_failures_are_normalized() -> None:
    def access_denied(*args: Any, **kwargs: Any) -> None:
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "ObjectOperation")

    key = make_input_key("job-1", "input.png")
    write_client = FakeS3Client()
    write_client.put_object = access_denied  # type: ignore[method-assign]
    with pytest.raises(StorageUnavailableError, match="write failed"):
        await S3Storage(remote_config(), client=write_client).put_object(key, b"input")

    delete_client = FakeS3Client({("nebula-demo-private", "demo/inputs/job-1/input.png"): b"input"})
    delete_client.delete_object = access_denied  # type: ignore[method-assign]
    with pytest.raises(StorageUnavailableError, match="cleanup failed"):
        await S3Storage(remote_config(), client=delete_client).delete_object(key)


@pytest.mark.asyncio
async def test_api_and_laptop_runtime_share_the_same_remote_object_contract() -> None:
    objects: dict[tuple[str, str], bytes] = {}
    api_storage = build_storage(remote_config(), client=FakeS3Client(objects))
    laptop_storage = build_storage(remote_config(), client=FakeS3Client(objects))
    key = make_model_key("resnet50", "model.pt")

    await api_storage.put_object(key, b"model")
    assert await laptop_storage.get_object(key) == b"model"
    await laptop_storage.put_object(make_result_key("job-1", "attempt-1"), b"result")
    assert await api_storage.get_object(make_result_key("job-1", "attempt-1")) == b"result"


@pytest.mark.parametrize(
    "key",
    ("", "/inputs/job/input", "../secret", "inputs/../secret", "inputs\\secret", "inputs//secret", "x" * 1025),
)
@pytest.mark.asyncio
async def test_all_adapters_reject_unbounded_or_traversing_keys(tmp_path: Path, key: str) -> None:
    for storage in (FileStorage(tmp_path), S3Storage(remote_config(), client=FakeS3Client())):
        with pytest.raises(ValueError, match="storage key"):
            await storage.put_object(key, b"data")


@pytest.mark.parametrize(
    "config",
    (
        StorageRuntimeConfig(adapter="unknown"),
        StorageRuntimeConfig(adapter="s3"),
        StorageRuntimeConfig(adapter="s3", bucket="bucket", endpoint_url="http://not-secure.invalid"),
        StorageRuntimeConfig(adapter="s3", bucket="bucket", endpoint_url="https://storage.invalid"),
    ),
)
def test_missing_or_unsupported_storage_configuration_fails_closed(
    config: StorageRuntimeConfig,
) -> None:
    with pytest.raises(StorageConfigurationError):
        build_storage(config, client=FakeS3Client())


def test_file_adapter_requires_an_explicit_local_root(tmp_path: Path) -> None:
    storage = build_storage(StorageRuntimeConfig(adapter="file", local_root=str(tmp_path)))
    assert isinstance(storage, FileStorage)
    with pytest.raises(StorageConfigurationError):
        build_storage(StorageRuntimeConfig(adapter="file", local_root=""))
