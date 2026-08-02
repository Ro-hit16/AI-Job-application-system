"""
api/v1/router.py — Aggregate all v1 routers
"""

from fastapi import APIRouter

from app.api.v1.agents import router as agents_router
from app.api.v1.applications import router as applications_router
from app.api.v1.auth import router as auth_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.interview import router as interview_router
api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(resumes_router)
api_router.include_router(jobs_router)
api_router.include_router(applications_router)
api_router.include_router(agents_router)
api_router.include_router(notifications_router)
api_router.include_router(interview_router)
