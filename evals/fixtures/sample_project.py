"""Small executable target used only by the contract regression suite."""

from datetime import date
from typing import Iterable


def normalize_iso_date(value: str) -> str:
    return date.fromisoformat(value).isoformat()


def fleet_total(values: Iterable[int]) -> int:
    return sum(values)


def batched_query_count(ships: Iterable[object]) -> int:
    return 1 if list(ships) else 0
