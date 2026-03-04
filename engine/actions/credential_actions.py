from __future__ import annotations

import logging
from typing import Any, Dict

from new.core.credentials_loader import load_credentials_from_ref
from new.engine.models.runtime import ActionResult, ExecutionContext

logger = logging.getLogger(__name__)


def credentials_load(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    """Load credentials from a secure reference file and store in context.vars.

    Params:
        credentials_ref: path to credential JSON file (required)
        save_as: var name to store result under (default: "creds")
    """
    credentials_ref = str(params.get("credentials_ref", ""))
    save_as = str(params.get("save_as", "creds"))

    if not credentials_ref:
        return ActionResult(ok=False, code="missing_ref", message="credentials_ref param required")

    try:
        creds = load_credentials_from_ref(credentials_ref)
    except ValueError as exc:
        return ActionResult(ok=False, code="credential_error", message=str(exc))
    except Exception as exc:
        logger.exception("unexpected error loading credentials")
        return ActionResult(ok=False, code="credential_error", message=str(exc))

    context.vars[save_as] = {
        "username_or_email": creds.username_or_email,
        "password": creds.password,
    }
    return ActionResult(ok=True, code="ok", message=f"credentials loaded as {save_as}")
