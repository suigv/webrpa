from __future__ import annotations

import re
from typing import Any


def derive_blogger_profile_data(
    candidate: dict[str, Any],
    fallback_username: str = "",
    fallback_display_name: str = "",
    fallback_profile: str = "",
) -> dict[str, Any] | None:
    text = str(candidate.get("text") or "").strip()
    desc = str(candidate.get("desc") or "").strip()
    combined = " ".join(part for part in (text, desc) if part).strip()

    username_matches = re.findall(r"@([A-Za-z0-9_]{1,32})", combined)
    username = username_matches[0] if username_matches else fallback_username

    display_name = fallback_display_name
    if not display_name:
        if username and text:
            marker = f"@{username}"
            if marker in text:
                prefix = text.split(marker, 1)[0].strip(" |-:")
                if prefix:
                    display_name = prefix
        if not display_name:
            display_name = username or (text[:32].strip() if text else "")

    profile = fallback_profile or combined
    if not username and not display_name:
        return None

    return {
        "username": username,
        "display_name": display_name,
        "profile": profile,
        "source_candidate": candidate,
    }
