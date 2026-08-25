from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import (
    ATTRIBUTION,
    __version__,
    physical_models,  # noqa: F401
)
from .api import router as api_router
from .api.agent_api import router as agent_api_router
from .api.physical_model import router as physical_model_router
from .api.workflow import router as workflow_router
from .api.workflow_actions import router as workflow_actions_router
from .config import get_settings
from .db import SessionLocal, engine
from .estimate_pinning import router as estimate_pinning_router
from .importers.seed import seed_database
from .library_ui import router as library_ui_router
from .models import User
from .release_admin import router as release_admin_router
from .security import HUMAN_SESSION_MAX_AGE_SECONDS
from .services.schema_bootstrap import prepare_application_schema
from .technical_admin import router as technical_admin_router
from .ui import router as ui_router

settings = get_settings()
package_dir = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    prepare_application_schema(engine, settings.env)
    with SessionLocal() as db:
        if not db.scalar(select(User.id).limit(1)):
            seed_database(db, settings)
    yield


app = FastAPI(
    title="QUANTIFIRE API",
    summary="Passive-fire estimating and technical decision-support system",
    description=ATTRIBUTION,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=settings.session_https_only,
    max_age=HUMAN_SESSION_MAX_AGE_SECONDS,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts or ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "If-Match",
        "X-CSRF-Token",
        "X-Classifire-Agent-ID",
    ],
)
app.mount("/static", StaticFiles(directory=str(package_dir / "static")), name="static")
app.mount("/brand", StaticFiles(directory=str(package_dir / "static" / "brand")), name="brand")


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if settings.session_https_only:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok", "product": "QUANTIFIRE", "version": __version__}


app.include_router(api_router)
app.include_router(physical_model_router)
app.include_router(agent_api_router)
app.include_router(workflow_router)
app.include_router(workflow_actions_router)
app.include_router(ui_router)
app.include_router(estimate_pinning_router)
app.include_router(release_admin_router)
app.include_router(technical_admin_router)
app.include_router(library_ui_router)
