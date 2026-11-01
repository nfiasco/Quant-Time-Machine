"""Version 1 of the research API. Every route here follows `app.api.conventions`."""

from fastapi import APIRouter

from app.api import examples, filings, fundamentals, knowledge_time, macro, prices

router = APIRouter(prefix="/v1", responses=examples.V1_ERRORS)
router.include_router(knowledge_time.router)
router.include_router(macro.router)
router.include_router(prices.router)
router.include_router(filings.router)
router.include_router(fundamentals.router)
