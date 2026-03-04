from fastapi import APIRouter
from pydantic import BaseModel

from new.core.account_parser import parse_accounts_lines, parse_accounts_text
from new.core.data_store import read_lines, read_text, write_lines, write_text

router = APIRouter()


class DataUpdate(BaseModel):
    content: str


class AccountsImportRequest(BaseModel):
    content: str
    overwrite: bool = True


@router.get("/accounts")
def get_accounts():
    return {"data": read_text("accounts")}


@router.put("/accounts")
def update_accounts(data: DataUpdate):
    write_text("accounts", data.content)
    return {"status": "ok"}


@router.post("/accounts/import")
def import_accounts(data: AccountsImportRequest):
    parsed = parse_accounts_text(data.content)
    new_lines = parsed["normalized_lines"]

    if data.overwrite:
        merged_lines = new_lines
    else:
        merged_lines = read_lines("accounts") + new_lines

    write_lines("accounts", merged_lines)
    return {
        "status": "ok",
        "overwrite": data.overwrite,
        "stored": len(merged_lines),
        "imported": len(new_lines),
        "valid": parsed["valid"],
        "invalid": parsed["invalid"],
        "errors": parsed["errors"],
    }


@router.get("/accounts/parsed")
def get_accounts_parsed():
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
