from fastapi import APIRouter
from pydantic import BaseModel

from new.core.data_store import read_text, write_text

router = APIRouter()


class DataUpdate(BaseModel):
    content: str


@router.get("/accounts")
def get_accounts():
    return {"data": read_text("accounts")}


@router.put("/accounts")
def update_accounts(data: DataUpdate):
    write_text("accounts", data.content)
    return {"status": "ok"}


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
