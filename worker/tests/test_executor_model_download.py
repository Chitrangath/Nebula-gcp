from types import SimpleNamespace

import pytest
from core.executor import JobExecutor


class Response:
    class Content:
        async def iter_chunked(self, _size):
            yield b"verified-model"

    content = Content()

    def raise_for_status(self):
        return None

    def close(self):
        return None


class Session:
    def __init__(self):
        self.urls = []

    async def get(self, url, **_kwargs):
        self.urls.append(url)
        return Response()


@pytest.mark.asyncio
async def test_model_loader_downloads_explicit_signed_url_directly():
    settings = SimpleNamespace(EXECUTOR_ADAPTER="fixture")
    worker = JobExecutor(settings)
    worker.session = Session()
    spec = SimpleNamespace(artifact_url="https://private.example/model.safetensors")

    chunks = [chunk async for chunk in worker._download_model_chunks(spec)]

    assert chunks == [b"verified-model"]
    assert worker.session.urls == ["https://private.example/model.safetensors"]
