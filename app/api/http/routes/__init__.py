from fastapi import APIRouter

from app.api.http.routes.audit import router as audit_router
from app.api.http.routes.conversations import router as conversations_router
from app.api.http.routes.debug_im import router as debug_im_router
from app.api.http.routes.health import router as health_router
from app.api.http.routes.integrations import router as integrations_router
from app.api.http.routes.memories import router as memories_router
from app.api.http.routes.overview import router as overview_router
from app.api.http.routes.reminders import router as reminders_router
from app.api.http.routes.tasks import router as tasks_router

api_router = APIRouter()
api_router.include_router(audit_router)
api_router.include_router(conversations_router)
api_router.include_router(debug_im_router)
api_router.include_router(integrations_router)
api_router.include_router(memories_router)
api_router.include_router(overview_router)
api_router.include_router(reminders_router)
api_router.include_router(tasks_router)

__all__ = [
    "api_router",
    "audit_router",
    "conversations_router",
    "debug_im_router",
    "health_router",
    "integrations_router",
    "memories_router",
    "overview_router",
    "tasks_router",
]
