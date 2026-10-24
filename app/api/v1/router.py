"""Aggregation router for API v1 endpoints.
"""

from fastapi import APIRouter
from app.api.v1.versions import router as versions_router
from app.api.v1.nodes import router as nodes_router
from app.api.v1.selections import router as selections_router
from app.api.v1.test_cases import router as test_cases_router

api_v1_router = APIRouter()

api_v1_router.include_router(versions_router)
api_v1_router.include_router(nodes_router)
api_v1_router.include_router(selections_router)
api_v1_router.include_router(test_cases_router)
