"""FastAPI Application Entry Point.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import init_db
from app.api.v1.router import api_v1_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown routines."""
    # Initialize SQLite database schema
    init_db()
    yield


app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    description=(
        "Backend API to parse medical device manuals (e.g. CardioTrack CT-200) "
        "into versioned, hierarchical trees, track cross-version differences, "
        "submit version-pinned node selections, and generate QA test cases."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 Router
app.include_router(api_v1_router, prefix=settings.api_v1_str)


@app.get("/", tags=["Health"])
def root():
    """Root endpoint returning API service status and metadata."""
    return {
        "service": settings.project_name,
        "version": settings.version,
        "status": "online",
        "docs": "/docs",
        "api_v1": settings.api_v1_str,
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for liveness and readiness probes."""
    return {"status": "healthy"}
