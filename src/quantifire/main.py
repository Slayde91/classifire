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

from . import ATTRIBUTION, __version__
from . import canonical_models as _canonical_models  # noqa: F401
from . import commercial_models as _commercial_models  # noqa: F401
from .api import router as api_router
from .api.guarded_technical import router as guarded_technical_router
from .api.physical_model import router as physical_model_router
from .api.productivity import router as productivity_router
from .api.quantity_labour import router as quantity_labour_router
from .api.repair_strategy import router as repair_strategy_router
from .api.workflow import router as workflow_router
from .api.workflow_actions import router as workflow_actions_router
from .config import get_settings
from .db import Base, SessionLocal, engine
from .importers.seed import seed_database
from .models import User
from .ui import router as ui_router
from .estimate_pinning import router as estimate_pinning_router
from .release_admin import router as release_admin_router
from .technical_admin import router as technical_admin_router
from .library_ui import router as library_ui_router

settings = get_settings()
package_dir = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Development/local installer convenience. Production deployment must run Alembic first.
    Base.metadata.create_all(bind=engine)
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
    max_age=60 * 60 * 12,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts or ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "If-Match", "X-CSRF-Token"],
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


# Guarded transition routes are registered before the legacy v1 router so the
# v2.13 hard gates cannot be bypassed through an older duplicate path.
app.include_router(guarded_technical_router)
app.include_router(physical_model_router)
app.include_router(repair_strategy_router)
app.include_router(quantity_labour_router)
app.include_router(productivity_router)
app.include_router(api_router)
app.include_router(workflow_router)
app.include_router(workflow_actions_router)
app.include_router(ui_router)
app.include_router(estimate_pinning_router)
app.include_router(release_admin_router)
app.include_router(technical_admin_router)
app.include_router(library_ui_router)
