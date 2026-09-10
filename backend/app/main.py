"""
backend/app/main.py

Zentrax AI Graphics — FastAPI application entrypoint.
Initializes the app, configures CORS, wires up routers, and exposes
a health check endpoint used by the Docker HEALTHCHECK / load balancer.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from app.api import endpoints
from app.core.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("zentrax.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events. Use this for startup/shutdown logic
    (e.g. warming up a local diffusers pipeline, opening a DB pool)
    instead of the deprecated @app.on_event decorators.
    """
    logger.info(
        "Starting %s (env=%s, debug=%s)",
        settings.PROJECT_NAME,
        settings.ENVIRONMENT,
        settings.DEBUG,
    )
    # --- startup ---
    # e.g. await database.connect()
    # e.g. app.state.ai_engine = AIEngine()  # if you want a single shared instance

    yield

    # --- shutdown ---
    logger.info("Shutting down %s", settings.PROJECT_NAME)
    # e.g. await database.disconnect()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-powered logo and banner generation for the Zentrax platform.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #
# BACKEND_CORS_ORIGINS is a list[AnyHttpUrl] from Settings — cast to str
# since Starlette's middleware expects plain strings.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# Routers
# --------------------------------------------------------------------------- #
app.include_router(endpoints.router)


# --------------------------------------------------------------------------- #
# Health check
# --------------------------------------------------------------------------- #
@app.get(
    "/health",
    status_code=status.HTTP_200_OK,
    tags=["Health"],
    summary="Health check",
)
async def health_check() -> dict:
    """
    Lightweight liveness/readiness probe. Used by the Docker HEALTHCHECK,
    load balancers, and orchestrators (k8s, ECS) to verify the service
    is up. Keep this fast and dependency-free — it should not call the
    AI generation service or storage backend.
    """
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/", tags=["Health"], include_in_schema=False)
async def root() -> dict:
    """Root endpoint — simple confirmation the API is reachable."""
    return {"message": f"{settings.PROJECT_NAME} API is running. See /docs."}