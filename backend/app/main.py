
from __future__ import annotations

import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import get_logger, setup_logging
from app.database import check_database_health, create_tables
from app.tasks.scheduler import start_scheduler, stop_scheduler


settings = get_settings()

setup_logging(
    log_level=settings.LOG_LEVEL,
    environment=settings.ENVIRONMENT,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application")

    # Step 1: Resolve Neon database hostname
    addresses = []

    try:
        host = (
            settings.DATABASE_URL
            .split("@")[-1]
            .split("/")[0]
            .split(":")[0]
            .split("?")[0]
        )

        addresses = socket.getaddrinfo(
            host,
            5432,
            type=socket.SOCK_STREAM,
        )

        for address in addresses:
            logger.info(
                "Neon DNS result: family=%s address=%s",
                address[0],
                address[4][0],
            )

    except Exception:
        logger.exception("Neon DNS resolution failed")

    # Step 2: Test TCP connectivity
    for address in addresses:
        family, socktype, proto, canonname, sockaddr = address

        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.settimeout(5)

                result = sock.connect_ex(sockaddr)

                logger.info(
                    "Neon TCP test: address=%s port=%s result=%s",
                    sockaddr[0],
                    sockaddr[1],
                    result,
                )

        except Exception:
            logger.exception("Neon TCP test failed")

    # Step 3: Initialize database tables
    if settings.ENVIRONMENT == "production":
        try:
            await create_tables()
            logger.info("Database tables initialized")
        except Exception:
            logger.exception("Database table initialization failed")

    # Step 4: Check database health
    db_health = await check_database_health()

    if db_health["status"] != "healthy":
        logger.warning("Database unavailable at startup")
    else:
        logger.info("Database connection healthy")

    # Step 5: Start scheduler
    start_scheduler()

    logger.info("Application ready")

    yield

    # Shutdown
    stop_scheduler()

    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception",
        extra={
            "error": str(exc),
            "path": str(request.url),
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred",
        },
    )


app.include_router(api_router)


@app.get("/health")
async def health():
    db = await check_database_health()

    return {
        "status": "ok" if db["status"] == "healthy" else "degraded",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db,
    }
