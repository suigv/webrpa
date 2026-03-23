from anyio.to_thread import run_sync
from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.account_service import (
    get_accounts_raw_text,
    import_accounts_content,
    list_accounts,
    update_account_fields,
)
from core.account_service import (
    pop_account as pop_account_from_pool,
)
from core.account_service import (
    reset_accounts as reset_accounts_store,
)
from core.account_service import (
    update_account_status as set_account_status,
)
from core.data_text_service import (
    get_location_text,
    get_website_text,
    set_location_text,
    set_website_text,
)

router = APIRouter()


class DataUpdate(BaseModel):
    content: str


class AccountsImportRequest(BaseModel):
    content: str
    overwrite: bool = True
    delimiter: str | None = None
    mapping: dict[int, str] | None = None
    app_id: str = Field(default="default", min_length=1)


class AccountStatusUpdate(BaseModel):
    account: str
    status: str
    error_msg: str | None = None


class AccountScopeRequest(BaseModel):
    app_id: str | None = None


@router.get("/accounts")
async def get_accounts():
    """获取原始存储文本 (兼容性接口)"""
    text = await run_sync(get_accounts_raw_text)
    return {"data": text}


@router.post("/accounts/import")
async def import_accounts(data: AccountsImportRequest):
    """通过高级解析逻辑导入账号"""
    return await run_sync(
        import_accounts_content,
        data.content,
        data.overwrite,
        data.delimiter,
        data.mapping,
        data.app_id,
    )


class AccountUpdate(BaseModel):
    old_account: str
    new_data: dict[str, object]


@router.post("/accounts/update")
async def update_account(data: AccountUpdate):
    """更新账号所有字段"""
    ok = await run_sync(update_account_fields, data.old_account, data.new_data)
    if ok:
        return {"status": "ok", "message": f"Account {data.old_account} updated"}
    return {"status": "error", "message": "Account not found"}


@router.post("/accounts/status")
async def update_account_status(data: AccountStatusUpdate):
    """更新账号状态"""
    ok = await run_sync(set_account_status, data.account, data.status, data.error_msg)
    if ok:
        return {
            "status": "ok",
            "message": f"Account {data.account} status updated to {data.status}",
        }
    return {"status": "error", "message": "Account not found"}


@router.post("/accounts/pop")
async def pop_account(data: AccountScopeRequest | None = None):
    """原子化获取下一个待处理账号"""
    account = await run_sync(pop_account_from_pool, data.app_id if data else None)
    if account:
        return {"status": "ok", "account": account}
    return {"status": "error", "message": "No ready accounts available in pool"}


@router.get("/accounts/parsed")
async def get_accounts_parsed(app_id: str | None = None):
    """获取所有解析后的账号对象"""
    accounts = await run_sync(list_accounts, app_id)
    return {"accounts": accounts}


@router.post("/accounts/reset")
async def reset_accounts():
    """将所有账号状态重置为就绪 (ready)"""
    count = await run_sync(reset_accounts_store)
    return {"status": "ok", "message": f"Successfully reset {count} accounts to ready"}


@router.get("/location")
def get_location():
    return {"data": get_location_text()}


@router.put("/location")
def update_location(data: DataUpdate):
    set_location_text(data.content)
    return {"status": "ok"}


@router.get("/website")
def get_website():
    return {"data": get_website_text()}


@router.put("/website")
def update_website(data: DataUpdate):
    set_website_text(data.content)
    return {"status": "ok"}
