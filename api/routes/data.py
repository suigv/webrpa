from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import json

from core.account_parser import parse_accounts_lines, parse_accounts_advanced, parse_accounts_text
from core.data_store import read_lines, read_text, write_lines, write_text
from datetime import datetime
import threading

router = APIRouter()
_accounts_lock = threading.Lock()


class DataUpdate(BaseModel):
    content: str


class AccountsImportRequest(BaseModel):
    content: str
    overwrite: bool = True
    delimiter: str | None = None
    mapping: Dict[int, str] | None = None


class AccountStatusUpdate(BaseModel):
    account: str
    status: str
    error_msg: Optional[str] = None


@router.get("/accounts")
def get_accounts():
    """获取原始存储文本"""
    return {"data": read_text("accounts")}


@router.post("/accounts/import")
def import_accounts(data: AccountsImportRequest):
    """通过高级解析逻辑导入账号"""
    # 关键修复：JSON 传输会将 mapping 的 Key 转为字符串，需转回 int
    clean_mapping = {}
    if data.mapping:
        for k, v in data.mapping.items():
            try:
                clean_mapping[int(k)] = v
            except ValueError:
                continue
    
    parsed: dict[str, Any]
    if data.delimiter is None and not clean_mapping:
        parsed = parse_accounts_text(data.content)
    else:
        parsed = parse_accounts_advanced(data.content, delimiter=data.delimiter or "", mapping=clean_mapping or None)

    normalized_lines_obj = parsed.get("normalized_lines", [])
    if isinstance(normalized_lines_obj, list):
        new_lines: list[str] = [line for line in normalized_lines_obj if isinstance(line, str)]
    else:
        new_lines = []
    errors = parsed.get("errors", [])
    valid_raw = parsed.get("valid", len(new_lines))
    if isinstance(valid_raw, (int, float, str)):
        valid = int(valid_raw)
    else:
        valid = len(new_lines)
    invalid_raw = parsed.get("invalid", 0)
    if isinstance(invalid_raw, (int, float, str)):
        invalid = int(invalid_raw)
    else:
        invalid = 0

    if data.overwrite:
        merged_lines: list[str] = new_lines
    else:
        existing_lines = [line for line in read_lines("accounts") if isinstance(line, str)]
        merged_lines = existing_lines + new_lines

    write_lines("accounts", merged_lines)
    return {
        "status": "ok",
        "stored": len(merged_lines),
        "imported": len(new_lines),
        "valid": valid,
        "invalid": invalid,
        "errors": errors if isinstance(errors, list) else [],
    }


@router.post("/accounts/status")
def update_account_status(data: AccountStatusUpdate):
    """更新账号状态 (要求存储格式为 JSON 行)"""
    lines = read_lines("accounts")
    updated_lines = []
    found = False
    
    for line in lines:
        try:
            item = json.loads(line)
            if item.get("account") == data.account:
                item["status"] = data.status
                if data.error_msg:
                    item["error_msg"] = data.error_msg
                updated_lines.append(json.dumps(item, ensure_ascii=False))
                found = True
            else:
                updated_lines.append(line)
        except Exception:
            # 非 JSON 行在严谨模式下不再尝试猜测，直接原样保留或过滤
            updated_lines.append(line)
                
    if found:
        write_lines("accounts", updated_lines)
        return {"status": "ok", "message": f"Account {data.account} status updated to {data.status}"}
    return {"status": "error", "message": "Account not found"}


@router.post("/accounts/pop")
def pop_account():
    """原子化获取下一个待处理账号，实现‘账号池-1’逻辑"""
    global _accounts_lock
    with _accounts_lock:
        lines = read_lines("accounts")
        updated_lines = []
        target_account = None
        
        for line in lines:
            try:
                item = json.loads(line)
                if target_account is None and item.get("status") == "ready":
                    item["status"] = "in_progress"
                    item["last_used"] = str(datetime.now()) # 简单记录时间
                    target_account = item
                    updated_lines.append(json.dumps(item, ensure_ascii=False))
                else:
                    updated_lines.append(line)
            except Exception:
                updated_lines.append(line)
        
        if target_account:
            write_lines("accounts", updated_lines)
            return {"status": "ok", "account": target_account}
        
    return {"status": "error", "message": "No ready accounts available in pool"}


@router.get("/accounts/parsed")
def get_accounts_parsed():
    """获取所有解析后的账号对象"""
    return {"accounts": parse_accounts_lines(read_lines("accounts"))}


@router.get("/location")
def get_location():
    return {"data": read_text("location")}


@router.put("/location")
def update_location(data: DataUpdate):
    write_text("location", data.content)
    return {"status": "ok"}


@router.get("/website")
def get_website():
    return {"data": read_text("website")}


@router.put("/website")
def update_website(data: DataUpdate):
    write_text("website", data.content)
    return {"status": "ok"}
