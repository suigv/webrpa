from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class AccountRecord(TypedDict):
    device_index: int
    username: str
    password: str
    twofa_secret: NotRequired[str]
    status: NotRequired[Literal["active", "disabled", "cooldown"]]
    tags: NotRequired[list[str]]


class BloggerRecord(TypedDict):
    username: str
    ai_type: Literal["volc", "part_time"]
    source: NotRequired[Literal["scrape", "manual", "seed"]]
    bound_device: NotRequired[int]
    last_scraped_at: NotRequired[str]
    cooling_until: NotRequired[str]


class DedupeRecord(TypedDict):
    namespace: str
    key: str
    first_seen_at: str
    last_seen_at: str
    ttl_seconds: NotRequired[int]


class CounterRecord(TypedDict):
    namespace: str
    key: str
    value: int
    date: NotRequired[str]
    updated_at: str


class AIContextRecord(TypedDict):
    device_index: int
    ai_type: Literal["volc", "part_time"]
    persona: NotRequired[str]
    memory: NotRequired[list[str]]
    last_prompt: NotRequired[str]
    last_response: NotRequired[str]
    updated_at: str


DATA_KEYSPACE = {
    "accounts": "account_records",
    "bloggers": "blogger_records",
    "dedupe": "dedupe_records",
    "counters": "counter_records",
    "ai_context": "ai_context_records",
}
