"""
Structured Intelligence - Main Application
Production-grade NotebookLM alternative with SMC integration
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
from loguru import logger

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.redis_client import init_redis, close_redis
from app.api.v1 import api_router
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("🚀 Starting Structured Intelligence...")
    
    # Initialize database
    await init_db()
    logger.info("✅ Database initialized")
    
    # Initialize Redis
    await init_redis()
    logger.info("✅ Redis initialized")
    
    # Initialize SMC integration
    if settings.SMC_ENABLED:
        logger.info("🔐 SMC Integration enabled")
        # SMC initialization happens in the service layer
    
    logger.info("🎯 Structured Intelligence ready!")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down Structured Intelligence...")
    await close_db()
    await close_redis()
    logger.info("✅ Cleanup complete")


# Initialize FastAPI app
app = FastAPI(
    title="Structured Intelligence API",
    description="Production-grade document analysis and AI chat platform with SMC memory integration",
    version="1.0.0",
    docs_url="/api/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/api/redoc" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan
)

# ============================================
# MIDDLEWARE
# ============================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# Request timing
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# ============================================
# ROUTES
# ============================================

# Health check
@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "smc_enabled": settings.SMC_ENABLED,
        "version": "1.0.0"
    }

# Readiness check
@app.get("/ready", tags=["health"])
async def readiness_check():
    """Readiness check for container orchestration"""
    # TODO: Add actual checks for DB, Redis, etc.
    return {
        "status": "ready",
        "database": "connected",
        "redis": "connected",
        "vector_db": "connected"
    }

# Include API router
app.include_router(api_router, prefix="/api/v1")


# ============================================
# ERROR HANDLERS
# ============================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Global exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.DEBUG else "An error occurred",
            "request_id": getattr(request.state, "request_id", None)
        }
    )


# ============================================
# ROOT ENDPOINT
# ============================================

@app.get("/", tags=["root"])
async def root():
    """Root endpoint"""
    return {
        "name": "Structured Intelligence API",
        "version": "1.0.0",
        "description": "Production-grade document analysis and AI chat platform",
        "docs": "/api/docs" if settings.ENVIRONMENT == "development" else None,
        "health": "/health",
        "ready": "/ready"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
