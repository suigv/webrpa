from __future__ import annotations

from functools import partial
from typing import Any, Literal, cast

from anyio import to_thread as _to_thread
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.device_profile_generator import (
    generate_contact,
    generate_env_bundle,
    generate_fingerprint,
)
from core.device_profile_inventory import get_phone_models, refresh_phone_models
from core.device_profile_selector import select_phone_model

to_thread = cast(Any, _to_thread)

router = APIRouter()


class InventoryResponse(BaseModel):
    inventory_type: str
    source: str
    device_ip: str
    sdk_port: int
    count: int
    items: list[dict[str, Any]] = Field(default_factory=list)
    refreshed_at: str
    from_cache: bool = False


class PhoneModelSelectRequest(BaseModel):
    source: Literal["online", "local"] = "online"
    device_ip: str = ""
    sdk_port: int = 8000
    refresh_inventory: bool = False
    seed: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] | None = None


class PhoneModelSelectionResponse(BaseModel):
    source: str
    seed: str
    candidate_count: int
    selected_index: int
    filters: dict[str, Any] = Field(default_factory=dict)
    selected: dict[str, Any]
    apply: dict[str, str]


class FingerprintGenerateRequest(BaseModel):
    country_profile: str = "jp_mobile"
    seed: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class ContactGenerateRequest(BaseModel):
    country_profile: str = "jp_mobile"
    seed: str | None = None
    count: int = 1


class EnvBundleGenerateRequest(BaseModel):
    country_profile: str = "jp_mobile"
    seed: str | None = None
    contact_count: int = 1
    language: str | None = None
    country: str | None = None
    timezone: str | None = None
    shake_enabled: bool = False
    fingerprint_overrides: dict[str, Any] = Field(default_factory=dict)


def _unwrap_or_raise(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": str(result.get("code") or "request_failed"),
                "message": str(result.get("message") or "request failed"),
                "data": result.get("data") or {},
            },
        )
    data = result.get("data")
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="unexpected response shape")
    return data


@router.post("/inventory/phone-models/{source}/refresh", response_model=InventoryResponse)
async def refresh_phone_model_inventory(
    source: Literal["online", "local"],
    device_ip: str,
    sdk_port: int = 8000,
):
    result = await to_thread.run_sync(
        partial(refresh_phone_models, source, device_ip=device_ip, sdk_port=sdk_port)
    )
    return InventoryResponse.model_validate(_unwrap_or_raise(result))


@router.get("/inventory/phone-models/{source}", response_model=InventoryResponse)
async def get_phone_model_inventory(
    source: Literal["online", "local"],
    device_ip: str,
    sdk_port: int = 8000,
    refresh: bool = Query(default=False),
):
    result = await to_thread.run_sync(
        partial(
            get_phone_models,
            source,
            device_ip=device_ip,
            sdk_port=sdk_port,
            refresh=refresh,
        )
    )
    return InventoryResponse.model_validate(_unwrap_or_raise(result))


@router.post("/selectors/phone-model", response_model=PhoneModelSelectionResponse)
async def select_phone_model_route(request: PhoneModelSelectRequest):
    result = await to_thread.run_sync(
        partial(
            select_phone_model,
            source=request.source,
            device_ip=request.device_ip,
            sdk_port=request.sdk_port,
            refresh_inventory=request.refresh_inventory,
            seed=request.seed,
            filters=dict(request.filters),
            items=request.items,
        )
    )
    return PhoneModelSelectionResponse.model_validate(_unwrap_or_raise(result))


@router.post("/generators/fingerprint")
async def generate_fingerprint_route(request: FingerprintGenerateRequest):
    return generate_fingerprint(
        country_profile=request.country_profile,
        seed=request.seed,
        overrides=dict(request.overrides),
    )


@router.post("/generators/contact")
async def generate_contact_route(request: ContactGenerateRequest):
    return generate_contact(
        country_profile=request.country_profile,
        seed=request.seed,
        count=request.count,
    )


@router.post("/generators/env-bundle")
async def generate_env_bundle_route(request: EnvBundleGenerateRequest):
    return generate_env_bundle(
        country_profile=request.country_profile,
        seed=request.seed,
        contact_count=request.contact_count,
        language=request.language,
        country=request.country,
        timezone=request.timezone,
        shake_enabled=request.shake_enabled,
        fingerprint_overrides=dict(request.fingerprint_overrides),
    )
