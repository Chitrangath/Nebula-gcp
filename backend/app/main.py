from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.routers import auth, earnings, health, jobs, models, network, nodes, worker
from app.schemas import ProblemResponse
from app.services.blockchain_service import Web3Backend
from app.services.storage import build_storage, storage_config_from_settings


def _problem(
    request: Request,
    *,
    status: int,
    detail: Any,
    title: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a stable, trace-free problem document for browser clients."""
    return JSONResponse(
        status_code=status,
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": request.url.path,
        },
        headers=headers,
        media_type="application/problem+json",
    )


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
        responses={
            status: {
                "description": "Problem response",
                "content": {
                    "application/problem+json": {
                        "schema": {"$ref": "#/components/schemas/ProblemResponse"}
                    }
                },
            }
            for status in (401, 403, 404, 409, 422, 429, 503)
        },
    )

    def custom_openapi() -> dict[str, Any]:
        if application.openapi_schema is None:
            schema = get_openapi(
                title=application.title,
                version=application.version,
                description=application.description,
                routes=application.routes,
            )
            schemas = schema.setdefault("components", {}).setdefault("schemas", {})
            schemas["ProblemResponse"] = ProblemResponse.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = custom_openapi  # type: ignore[method-assign]

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

    @application.exception_handler(StarletteHTTPException)
    async def http_problem_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(
            request,
            status=exc.status_code,
            detail=exc.detail,
            title="Request failed",
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_problem_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(
            request,
            status=422,
            detail=exc.errors(),
            title="Request validation failed",
        )

    application.include_router(health.router, tags=["Health"])
    application.include_router(auth.router, prefix="/v1/auth", tags=["Authentication"])
    application.include_router(nodes.router, prefix="/v1/nodes", tags=["Nodes"])
    application.include_router(models.router, prefix="/v1/models", tags=["Models"])
    application.include_router(jobs.router, prefix="/v1/jobs", tags=["Jobs"])
    application.include_router(earnings.router, prefix="/v1/earnings", tags=["Earnings"])
    application.include_router(network.router, prefix="/v1/network", tags=["Network"])
    application.include_router(worker.router, prefix="/v1/worker", tags=["Worker"])

    @application.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return _problem(
            request,
            status=429,
            detail=f"Rate limit exceeded: {exc.detail}",
            title="Rate limit exceeded",
        )

    @application.get("/")
    async def root():
        return {"message": "Nebula AI Cloud API", "version": "0.1.0"}

    return application


app = create_app()
