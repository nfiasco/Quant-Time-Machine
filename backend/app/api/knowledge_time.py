"""GET /v1/knowledge-time: the exact instant an `as_of` value means."""

from fastapi import APIRouter

from app.api.conventions import AsOfResponse, DataVersion, KnowledgeTime

router = APIRouter(tags=["conventions"])


@router.get("/knowledge-time")
def resolve_knowledge_time(
    knowledge_time: KnowledgeTime, data_version: DataVersion
) -> AsOfResponse:
    """Resolve `as_of` the way every endpoint does: `2020-06-05` is
    2020-06-05T09:30:00-04:00. `data_version` is the one the data endpoints read now.
    The only /v1 response without `data` and `reason`."""
    return AsOfResponse(knowledge_time=knowledge_time, data_version=data_version)
