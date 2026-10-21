from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.routers import auth, earnings, health, jobs, models, nodes, worker
from app.services.blockchain_service import Web3Backend
from app.services.storage import build_storage, storage_config_from_settings


def create_app(*, blockchain=None, storage=None) -> FastAPI:
    """Application factory — creates a fresh FastAPI instance.

    Routers are imported at module level so their ``Depends(get_db)`` bindings
    are resolved against whatever ``app.database.get_db`` is live at request
    time.  Patching ``app.database.async_session`` before calling this factory
    (or before requests hit the module-level *app*) is sufficient to redirect
    all database traffic to a test engine.
    """
    application = FastAPI(
        title="Nebula AI Cloud API",
        description="Blockchain-backed distributed GPU compute platform with PoAE",
        version="0.1.0",
    )

    limiter = Limiter(key_func=get_remote_address)
    application.state.limiter = limiter
    application.state.blockchain = blockchain or (
        Web3Backend(settings.ARBITRUM_SEPOLIA_RPC, timeout=settings.RPC_TIMEOUT_SECONDS)
        if settings.NEBULA_PAYMENT_CONTRACT
        else None
    )
    application.state.storage = storage or build_storage(storage_config_from_settings(settings))

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router, tags=["Health"])
    application.include_router(auth.router, prefix="/v1/auth", tags=["Authentication"])
    application.include_router(nodes.router, prefix="/v1/nodes", tags=["Nodes"])
    application.include_router(models.router, prefix="/v1/models", tags=["Models"])
    application.include_router(jobs.router, prefix="/v1/jobs", tags=["Jobs"])
    application.include_router(earnings.router, prefix="/v1/earnings", tags=["Earnings"])
    application.include_router(worker.router, prefix="/v1/worker", tags=["Worker"])

    @application.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request, exc):
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded: {exc.detail}"},
        )

    @application.get("/")
    async def root():
        return {"message": "Nebula AI Cloud API", "version": "0.1.0"}

    return application


app = create_app()
