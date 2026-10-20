"""Version 1 of the research API. Every route here follows `app.api.conventions`."""

from fastapi import APIRouter

from app.api import knowledge_time

router = APIRouter(prefix="/v1")
router.include_router(knowledge_time.router)
