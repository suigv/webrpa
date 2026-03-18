from fastapi import APIRouter

from engine.action_registry import ActionMetadata, get_registry

router = APIRouter()


@router.get("/schema", response_model=dict[str, ActionMetadata])
def get_action_schema(tag: str | None = None):
    """Returns metadata for registered actions, optionally filtered by tag."""
    registry = get_registry()
    return registry.describe_all(tag=tag)


@router.get("/skills", response_model=dict[str, ActionMetadata])
def get_skill_schema():
    """Returns only actions explicitly promoted as AI-facing skills."""
    registry = get_registry()
    return registry.describe_all(tag="skill")
