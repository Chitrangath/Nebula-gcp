"""Bounded text uploads for the BERT inference path."""

import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.services.input_upload import InputUploadError, accept_text_upload


@pytest.mark.asyncio
async def test_accept_text_upload_preserves_exact_utf8_bytes():
    value = "An excellent café!\n".encode()
    upload = UploadFile(file=io.BytesIO(value), filename="review.txt", headers=Headers({"content-type": "text/plain"}))
    result = await accept_text_upload(upload, supported_formats=["txt"], max_size_bytes=65536)
    assert result.data == value
    assert result.content_type == "text/plain"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [b"", b"   ", b"\xff", b"hello\0world", b"a" * 65537])
async def test_rejects_invalid_text_before_creating_job(value):
    upload = UploadFile(file=io.BytesIO(value), filename="review.txt", headers=Headers({"content-type": "text/plain"}))
    with pytest.raises(InputUploadError):
        await accept_text_upload(upload, supported_formats=["txt"], max_size_bytes=65536)
