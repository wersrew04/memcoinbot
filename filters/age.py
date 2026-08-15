"""Token / pair yoshi filtri – 1–15 daqiqa oralig'i."""
from __future__ import annotations

from typing import Dict, Any, Tuple
from datetime import datetime, timezone
from config.settings import settings
from utils.helpers import safe_float, utc_now


def _age_minutes(data: Dict[str, Any]) -> float | None:
    """pair_created_at (ms yoki s) yoki token_age_minutes dan yoshni hisoblash."""
    # Allaqachon hisoblangan
    if data.get("token_age_minutes") is not None:
        return safe_float(data.get("token_age_minutes"))

    created = data.get("pair_created_at")
    if created is None:
        raw = data.get("raw") or {}
        created = raw.get("pairCreatedAt")
    if created is None:
        return None

    try:
        ts = float(created)
        # ms vs s
        if ts > 1e12:
            ts = ts / 1000.0
        created_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return max(0.0, (utc_now() - created_dt).total_seconds() / 60.0)
    except (TypeError, ValueError, OSError):
        return None


def check_token_age(data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Tavsiya: token yoshi 1–15 daqiqa.
    Ma'lumot yo'q bo'lsa – o'tkaziladi (scanner yangi juftliklarga qaratilgan).
    """
    min_m = getattr(settings, "MIN_TOKEN_AGE_MINUTES", 1.0)
    max_m = getattr(settings, "MAX_TOKEN_AGE_MINUTES", 15.0)

    age = _age_minutes(data)
    if age is None:
        return True, "Token yoshi ma'lumot yo'q (o'tkazildi)"

    data["token_age_minutes"] = age

    if age < min_m:
        return False, f"Token juda yangi: {age:.1f} daq < {min_m:.0f}"
    if age > max_m:
        return False, f"Token eski: {age:.1f} daq > {max_m:.0f}"
    return True, f"Token yoshi OK: {age:.1f} daq"
