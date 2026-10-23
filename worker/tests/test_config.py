import os

os.environ.setdefault("NODE_ID", "worker-test")
os.environ.setdefault("API_KEY", "api-key")
os.environ.setdefault("PRIVATE_KEY", "legacy")
os.environ.setdefault("VERIFYING_CONTRACT", "0x0000000000000000000000000000000000000001")

from config import Settings


def base_env() -> dict[str, str]:
    return {
        "NODE_ID": "worker-test",
        "API_KEY": "api-key",
        "BACKEND_URL": "http://localhost",
        "VERIFYING_CONTRACT": "0x0000000000000000000000000000000000000001",
    }


def test_new_worker_signing_key_is_preferred(monkeypatch):
    for key, value in base_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PRIVATE_KEY", "legacy")
    monkeypatch.setenv("WORKER_SIGNING_PRIVATE_KEY", "new")
    assert Settings().PRIVATE_KEY == "new"


def test_legacy_private_key_remains_compatible(monkeypatch):
    for key, value in base_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("WORKER_SIGNING_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("PRIVATE_KEY", "legacy")
    assert Settings().PRIVATE_KEY == "legacy"
