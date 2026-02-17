"""
API v1 router registration.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, documents, search, system, users


api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(search.router, tags=["search"])
