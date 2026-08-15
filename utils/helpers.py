from datetime import datetime, timezone
from typing import Any
import json


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_json(data: Any) -> str:
    return json.dumps(data, default=str, ensure_ascii=False)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def percent_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old
