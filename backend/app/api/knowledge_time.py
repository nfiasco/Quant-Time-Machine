"""GET /v1/knowledge-time: the exact instant an `as_of` value means."""

from fastapi import APIRouter

from app.api.conventions import AsOfResponse, KnowledgeTime

router = APIRouter(tags=["conventions"])


@router.get("/knowledge-time")
def resolve_knowledge_time(knowledge_time: KnowledgeTime) -> AsOfResponse:
    """Resolve `as_of` the way every endpoint does: `2020-06-05` is 2020-06-05T13:30:00Z."""
    return AsOfResponse(knowledge_time=knowledge_time, data_version=None)
