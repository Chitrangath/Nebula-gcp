"""Behavior tests for the authoritative job-input upload seam."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import Job, SupportedModel
from tests.conftest import seed_authed_user
from tests.vectors import PNG_1X1


@pytest.fixture
def image_model() -> SupportedModel:
    return SupportedModel(
        id="resnet50",
        name="ResNet-50",
        framework="pytorch",
        model_hash_sha256="ab" * 32,
        model_version="1.0",
        preprocessing_version="resnet50-v1",
        max_input_size_mb=1,
        supported_formats=["png", "jpg", "jpeg"],
        price_base_units=50_000,
        input_type="image",
    )


async def _post(client: AsyncClient, token: str, **overrides: Any) -> Response:
    data = {
        "model_id": "resnet50",
        "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    data.update(overrides.pop("data", {}))
    files = overrides.pop("files", {"input_file": ("input.png", PNG_1X1, "image/png")})
    headers = {"Authorization": f"Bearer {token}", **overrides.pop("headers", {})}
    return await client.post("/v1/jobs", data=data, files=files, headers=headers)


@pytest.mark.asyncio
async def test_backend_derives_key_hash_and_fingerprint_from_accepted_bytes(
    db: AsyncSession, image_model: SupportedModel
) -> None:
    db.add(image_model)
    _, token = await seed_authed_user(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, token)

    assert response.status_code == 200, response.text
    job = (await db.execute(select(Job))).scalar_one()
    assert job.input_hash == hashlib.sha256(PNG_1X1).hexdigest()
    assert job.input_file_key == f"inputs/{job.id}/input.png"
    assert response.json()["fingerprint"] == job.expected_fingerprint
    assert await app.state.storage.get_object(job.input_file_key) == PNG_1X1


@pytest.mark.asyncio
async def test_bert_text_job_uses_exact_upload_hash_and_model_fingerprint(db, image_model):
    image_model.id = "bert-base"
    image_model.input_type = "text"
    image_model.supported_formats = ["txt"]
    image_model.preprocessing_version = "bert-sentiment-v1"
    db.add(image_model)
    _, token = await seed_authed_user(db)
    review = "Excellent café, highly recommended!\n".encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(
            client, token, data={"model_id": "bert-base"}, files={"input_file": ("review.txt", review, "text/plain")}
        )
        assert response.status_code == 200, response.text
        job_response = await client.get(
            f"/v1/jobs/{response.json()['id']}", headers={"Authorization": f"Bearer {token}"}
        )
    assert job_response.status_code == 200
    assert job_response.json()["model_id"] == "bert-base"
    job = (await db.execute(select(Job))).scalar_one()
    assert job.input_hash == hashlib.sha256(review).hexdigest()
    assert await app.state.storage.get_object(job.input_file_key) == review


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content_type", "payload", "detail"),
    [
        ("../escape.png", "image/png", PNG_1X1, "filename"),
        ("input.gif", "image/gif", b"GIF89a", "extension"),
        ("input.png", "image/jpeg", PNG_1X1, "MIME"),
        ("input.png", "image/png", b"not-a-png", "magic"),
        ("input.png", "image/png", b"", "magic"),
        ("input.png", "image/png", PNG_1X1[:20], "truncated"),
    ],
)
async def test_rejects_invalid_uploads(
    db: AsyncSession,
    image_model: SupportedModel,
    filename: str,
    content_type: str,
    payload: bytes,
    detail: str,
) -> None:
    db.add(image_model)
    _, token = await seed_authed_user(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, token, files={"input_file": (filename, payload, content_type)})
    assert response.status_code == 422
    assert detail.lower() in response.json()["detail"].lower()
    assert (await db.execute(select(Job))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_rejects_over_limit_and_cleans_partial_object(db: AsyncSession, image_model: SupportedModel) -> None:
    image_model.max_input_size_mb = 0
    db.add(image_model)
    _, token = await seed_authed_user(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, token)
    assert response.status_code == 413
    assert app.state.storage._objects == {}


@pytest.mark.asyncio
async def test_idempotent_duplicate_returns_one_job_and_one_object(
    db: AsyncSession, image_model: SupportedModel
) -> None:
    db.add(image_model)
    _, token = await seed_authed_user(db)
    headers = {"Idempotency-Key": "job-upload-retry-1"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await _post(client, token, headers=headers)
        second = await _post(client, token, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len((await db.execute(select(Job))).scalars().all()) == 1
    assert len(app.state.storage._objects) == 1


@pytest.mark.asyncio
async def test_idempotency_key_rejects_different_bytes(db: AsyncSession, image_model: SupportedModel) -> None:
    db.add(image_model)
    _, token = await seed_authed_user(db)
    headers = {"Idempotency-Key": "job-upload-retry-2"}
    alternate = PNG_1X1[:16] + b"\x00\x00\x00\x02" + PNG_1X1[20:]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await _post(client, token, headers=headers)
        second = await _post(
            client,
            token,
            headers=headers,
            files={"input_file": ("input.png", alternate, "image/png")},
        )
    assert first.status_code == 200
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_storage_failure_does_not_create_job(
    db: AsyncSession, image_model: SupportedModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    db.add(image_model)
    _, token = await seed_authed_user(db)

    async def fail(*_args, **_kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr(app.state.storage, "put_object_once", fail)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, token)
    assert response.status_code == 503
    assert (await db.execute(select(Job))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_immutable_conflict_never_cleans_an_object_created_by_another_request(
    db: AsyncSession, image_model: SupportedModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    db.add(image_model)
    user_id, token = await seed_authed_user(db)
    idempotency_key = "shared-request"
    job_id = uuid.uuid5(uuid.NAMESPACE_URL, f"nebula:job-upload:{user_id}:{idempotency_key}")
    key = f"inputs/{job_id}/input.png"
    await app.state.storage.put_object_once(key, b"winner-bytes", "image/png")
    deleted: list[str] = []
    original_delete = app.state.storage.delete_object

    async def record_delete(object_key: str) -> bool:
        deleted.append(object_key)
        return await original_delete(object_key)

    monkeypatch.setattr(app.state.storage, "delete_object", record_delete)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, token, headers={"Idempotency-Key": idempotency_key})

    assert response.status_code == 503
    assert deleted == []
    assert await app.state.storage.get_object(key) == b"winner-bytes"


@pytest.mark.asyncio
async def test_database_failure_after_upload_removes_abandoned_object(
    db: AsyncSession, image_model: SupportedModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    db.add(image_model)
    _, token = await seed_authed_user(db)

    async def fail_commit() -> None:
        raise OSError("database unavailable")

    monkeypatch.setattr(db, "commit", fail_commit)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, token)
    assert response.status_code == 503
    assert app.state.storage._objects == {}
    assert (await db.execute(select(Job))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_json_job_creation_is_not_a_trusted_upload_path(db: AsyncSession, image_model: SupportedModel) -> None:
    db.add(image_model)
    _, token = await seed_authed_user(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/jobs",
            json={
                "model_id": image_model.id,
                "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "input_file_key": "attacker/chosen",
                "input_hash": "00" * 32,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 422
