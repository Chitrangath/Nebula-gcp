"""Worker configuration from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    NODE_ID: str
    API_KEY: str
    PRIVATE_KEY: str
    BACKEND_URL: str = "https://api.nebula.ai"
    CUDA_VISIBLE_DEVICES: str = "0"
    MODEL_CACHE_DIR: str = "/tmp/nebula-models"
    LOG_LEVEL: str = "INFO"
    TZ: str = "UTC"
    POLL_INTERVAL_SECONDS: float = 2.0
    CHAIN_ID: int = 421614
    VERIFYING_CONTRACT: str
    EXECUTOR_ADAPTER: Literal["fixture", "resnet50"] = "fixture"
    EXECUTOR_DEVICE: Literal["cpu", "cuda"] = "cpu"
    MAX_MODEL_ARTIFACT_BYTES: int = 256 * 1024 * 1024

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
