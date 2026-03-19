from fastapi import APIRouter

from app.api.http.routes.health import router as health_router
from app.api.http.routes.reminders import router as reminders_router

api_router = APIRouter()
api_router.include_router(reminders_router)

__all__ = ["api_router", "health_router"]
