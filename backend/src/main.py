"""
FastAPI Core Gateway for Mắt Phố (AI Surveillance & Fire Emergency Platform)
Synchronized with API_SPECIFICATION.md v1.2 and Clean Architecture
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.error_handlers import register_exception_handlers
from .services.firebase_service import init_firebase
from .routers import health, auth, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager: handles startup and shutdown gracefully.
    """
    logger.info(f"Initializing {settings.PROJECT_NAME} (v{settings.VERSION})...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # 1. Initialize Firebase Admin SDK
    try:
        init_firebase()
        logger.info("Firebase Admin SDK initialized successfully.")
    except Exception as e:
        logger.warning(f"Firebase initialization warning: {e}")

    logger.info("Backend services ready to serve requests.")
    yield

    # Shutdown sequence
    logger.info("Shutting down Backend services...")


# Initialize FastAPI instance
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="FastAPI Core Gateway, AI Fire Event Ingestion & Surveillance Services",
    lifespan=lifespan,
)

# 1. Register Unified Error Handlers (Section 1.2 in API_SPECIFICATION.md)
register_exception_handlers(app)

# 2. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Include Routers
app.include_router(health.router)
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(users.router, prefix=settings.API_V1_STR)
