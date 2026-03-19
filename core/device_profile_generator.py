from __future__ import annotations

import hashlib
import random
import uuid
from typing import Any

COUNTRY_PROFILES: dict[str, dict[str, Any]] = {
    "jp_mobile": {
        "country": "JP",
        "language": "ja",
        "timezone": "Asia/Tokyo",
        "cities": [
            {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
            {"name": "Osaka", "lat": 34.6937, "lon": 135.5023},
            {"name": "Yokohama", "lat": 35.4437, "lon": 139.6380},
            {"name": "Fukuoka", "lat": 33.5904, "lon": 130.4017},
            {"name": "Sapporo", "lat": 43.0618, "lon": 141.3545},
        ],
        "operators": [
            {"mcc": "440", "mnc": "10", "opercode": "44010", "opername": "NTT DOCOMO"},
            {"mcc": "440", "mnc": "20", "opercode": "44020", "opername": "SoftBank"},
            {"mcc": "440", "mnc": "50", "opercode": "44050", "opername": "KDDI"},
        ],
        "phone_prefixes": ["070", "080", "090"],
        "family_names": [
            "Sato",
            "Suzuki",
            "Takahashi",
            "Tanaka",
            "Watanabe",
            "Ito",
            "Nakamura",
            "Kobayashi",
        ],
        "given_names": [
            "Haruto",
            "Yuto",
            "Sota",
            "Yui",
            "Akari",
            "Aoi",
            "Ren",
            "Hinata",
        ],
    },
    "us_mobile": {
        "country": "US",
        "language": "en",
        "timezone": "America/Los_Angeles",
        "cities": [
            {"name": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
            {"name": "Seattle", "lat": 47.6062, "lon": -122.3321},
            {"name": "Austin", "lat": 30.2672, "lon": -97.7431},
        ],
        "operators": [
            {"mcc": "310", "mnc": "260", "opercode": "310260", "opername": "T-Mobile"},
            {"mcc": "310", "mnc": "410", "opercode": "310410", "opername": "AT&T"},
            {"mcc": "311", "mnc": "480", "opercode": "311480", "opername": "Verizon"},
        ],
        "phone_prefixes": ["206", "213", "310", "425", "512"],
        "family_names": ["Smith", "Johnson", "Brown", "Miller", "Davis", "Wilson"],
        "given_names": ["Liam", "Olivia", "Noah", "Emma", "Sophia", "James"],
    },
}


def _normalize_profile_name(profile: str | None) -> str:
    raw = str(profile or "").strip().lower()
    if raw in {"", "jp", "ja", "ja_jp", "japan", "jp_mobile"}:
        return "jp_mobile"
    if raw in {"us", "en_us", "usa", "us_mobile"}:
        return "us_mobile"
    return raw if raw in COUNTRY_PROFILES else "jp_mobile"


def _rng(seed: str | None) -> tuple[random.Random, str]:
    seed_used = str(seed or "").strip() or uuid.uuid4().hex
    digest = hashlib.sha256(seed_used.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big")), seed_used


def _digits(rand: random.Random, length: int) -> str:
    return "".join(str(rand.randint(0, 9)) for _ in range(length))


def _luhn_check_digit(number: str) -> str:
    total = 0
    reverse_digits = list(reversed(number))
    for index, char in enumerate(reverse_digits):
        digit = int(char)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - (total % 10)) % 10)


def _generate_imei(rand: random.Random) -> str:
    base = _digits(rand, 14)
    return base + _luhn_check_digit(base)


def _generate_iccid(rand: random.Random, mcc: str, mnc: str) -> str:
    body = f"8981{mcc}{mnc}{_digits(rand, 20 - 4 - len(mcc) - len(mnc))}"
    return body[:20]


def _generate_imsi(rand: random.Random, mcc: str, mnc: str) -> str:
    body_length = max(0, 15 - len(mcc) - len(mnc))
    return f"{mcc}{mnc}{_digits(rand, body_length)}"


def _generate_phone_number(rand: random.Random, prefixes: list[str], country: str) -> str:
    prefix = rand.choice(prefixes)
    if country == "JP":
        return prefix + _digits(rand, 8)
    if len(prefix) == 3:
        return prefix + _digits(rand, 7)
    return prefix + _digits(rand, 8)


def _generate_contact_name(rand: random.Random, profile: dict[str, Any]) -> str:
    family = rand.choice(list(profile["family_names"]))
    given = rand.choice(list(profile["given_names"]))
    return f"{family} {given}"


def generate_fingerprint(
    *,
    country_profile: str = "jp_mobile",
    seed: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_name = _normalize_profile_name(country_profile)
    profile = COUNTRY_PROFILES[profile_name]
    rand, seed_used = _rng(seed)
    city = dict(rand.choice(list(profile["cities"])))
    operator = dict(rand.choice(list(profile["operators"])))
    lat = round(float(city["lat"]) + rand.uniform(-0.08, 0.08), 6)
    lon = round(float(city["lon"]) + rand.uniform(-0.08, 0.08), 6)
    phone_number = _generate_phone_number(
        rand,
        list(profile["phone_prefixes"]),
        str(profile["country"]),
    )

    fingerprint = {
        "lac": str(rand.randint(1000, 65535)),
        "cid": str(rand.randint(10000, 268435455)),
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "mcc": operator["mcc"],
        "mnc": operator["mnc"],
        "phonenumber": phone_number,
        "country": profile["country"],
        "language": profile["language"],
        "timezone": profile["timezone"],
        "opercode": operator["opercode"],
        "opername": operator["opername"],
        "iccid": _generate_iccid(rand, str(operator["mcc"]), str(operator["mnc"])),
        "imsi": _generate_imsi(rand, str(operator["mcc"]), str(operator["mnc"])),
        "imei": _generate_imei(rand),
        "gaid": str(uuid.UUID(int=rand.getrandbits(128))),
    }
    if isinstance(overrides, dict):
        fingerprint.update({key: value for key, value in overrides.items() if value is not None})
    return {
        "country_profile": profile_name,
        "seed": seed_used,
        "city": city["name"],
        "fingerprint": fingerprint,
    }


def generate_contact(
    *,
    country_profile: str = "jp_mobile",
    seed: str | None = None,
    count: int = 1,
) -> dict[str, Any]:
    profile_name = _normalize_profile_name(country_profile)
    profile = COUNTRY_PROFILES[profile_name]
    rand, seed_used = _rng(seed)
    normalized_count = max(1, min(int(count), 20))
    contacts: list[dict[str, str]] = []
    seen_numbers: set[str] = set()
    while len(contacts) < normalized_count:
        number = _generate_phone_number(
            rand,
            list(profile["phone_prefixes"]),
            str(profile["country"]),
        )
        if number in seen_numbers:
            continue
        seen_numbers.add(number)
        contacts.append({"user": _generate_contact_name(rand, profile), "tel": number})
    return {
        "country_profile": profile_name,
        "seed": seed_used,
        "count": len(contacts),
        "contacts": contacts,
        "primary_contact": contacts[0],
    }


def generate_env_bundle(
    *,
    country_profile: str = "jp_mobile",
    seed: str | None = None,
    contact_count: int = 1,
    language: str | None = None,
    country: str | None = None,
    timezone: str | None = None,
    shake_enabled: bool = False,
    fingerprint_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_name = _normalize_profile_name(country_profile)
    bundle_seed = str(seed or "").strip() or uuid.uuid4().hex
    fingerprint_result = generate_fingerprint(
        country_profile=profile_name,
        seed=f"{bundle_seed}:fingerprint",
        overrides=fingerprint_overrides,
    )
    contact_result = generate_contact(
        country_profile=profile_name,
        seed=f"{bundle_seed}:contact",
        count=contact_count,
    )
    fingerprint = dict(fingerprint_result["fingerprint"])
    if language:
        fingerprint["language"] = str(language).strip()
    if country:
        fingerprint["country"] = str(country).strip().upper()
    if timezone:
        fingerprint["timezone"] = str(timezone).strip()
    return {
        "country_profile": profile_name,
        "seed": bundle_seed,
        "language": fingerprint["language"],
        "country": fingerprint["country"],
        "timezone": fingerprint["timezone"],
        "shake_enabled": bool(shake_enabled),
        "fingerprint": fingerprint,
        "google_adid": str(fingerprint["gaid"]),
        "contacts": list(contact_result["contacts"]),
        "primary_contact": dict(contact_result["primary_contact"]),
    }
