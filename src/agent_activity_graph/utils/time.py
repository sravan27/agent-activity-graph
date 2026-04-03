from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, TypeVar

T = TypeVar("T")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def sort_by_timestamp(items: Iterable[T], key: str = "timestamp") -> list[T]:
    return sorted(
        items,
        key=lambda item: (ensure_utc(getattr(item, key)), getattr(item, "event_id", "")),
    )

