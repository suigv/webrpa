from fastapi import APIRouter
from engine.action_registry import get_registry, ActionMetadata
from typing import Dict

router = APIRouter()

@router.get("/schema", response_model=Dict[str, ActionMetadata])
def get_action_schema():
    """Returns the full metadata of all registered and metadata-fied actions."""
    registry = get_registry()
    return registry.describe_all()
