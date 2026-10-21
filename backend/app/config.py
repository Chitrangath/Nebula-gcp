from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # Database
    DATABASE_URL: str

    # Blockchain
    ARBITRUM_SEPOLIA_RPC: str = "https://sepolia-rollup.arbitrum.io/rpc"
    ARBITRUM_SEPOLIA_WS: str = "wss://sepolia-rollup.arbitrum.io/ws"
    USDC_SEPOLIA_ADDRESS: str = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"
    NEBULA_PAYMENT_CONTRACT: str = ""
    BACKEND_EXECUTOR_ADDRESS: str = ""
    BACKEND_PRIVATE_KEY: str = ""
    CHAIN_ID: int = 421614
    CONTRACT_DEPLOYMENT_BLOCK: int = 0
    CONTRACT_OWNER_ADDRESS: str = ""
    CONTRACT_VERIFIER_ADDRESS: str = ""
    CONFIRMATION_DEPTH: int = 1
    FINALITY_DEPTH: int = 10
    EVENT_BLOCK_RANGE: int = 500
    EVENT_OVERLAP_BLOCKS: int = 2
    RUNNER_POLL_INTERVAL_SECONDS: float = 2.0
    RUNNER_BATCH_SIZE: int = 25
    PROOF_CLAIM_TTL_SECONDS: int = 300
    NODE_HEARTBEAT_TTL_SECONDS: int = 90
    RPC_TIMEOUT_SECONDS: float = 10.0
    RUNNERS_ENABLED: bool = False

    # Storage (private local or S3-compatible durable adapter)
    STORAGE_ADAPTER: Literal["file", "s3"] = "file"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "nebula-models"
    R2_PUBLIC_URL: str = "https://r2.nebula.ai"
    LOCAL_STORAGE_PATH: str = "/tmp/nebula-storage"
    OBJECT_STORAGE_REGION: str = "auto"
    OBJECT_STORAGE_PREFIX: str = "nebula-demo"
    OBJECT_STORAGE_CAPABILITY_TTL_SECONDS: int = 300

    # IPFS (Pinata)
    PINATA_API_KEY: str = ""
    PINATA_API_SECRET: str = ""

    # Auth
    JWT_SECRET: str
    JWT_EXPIRY_HOURS: int = 24
    JWT_REFRESH_EXPIRY_HOURS: int = 168

    # Frontend URL (CORS)
    FRONTEND_URL: str = "https://nebula-app.vercel.app"

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_MINUTES: int = 15

    # Logging
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
