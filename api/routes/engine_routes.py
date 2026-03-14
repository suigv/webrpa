from fastapi import APIRouter
from engine.action_registry import get_registry, ActionMetadata
from typing import Dict

router = APIRouter()

@router.get("/schema", response_model=Dict[str, ActionMetadata])
def get_action_schema(tag: str | None = None):
    """Returns the metadata of registered actions, optionally filtered by tag."""
    registry = get_registry()
    return registry.describe_all(tag=tag)
