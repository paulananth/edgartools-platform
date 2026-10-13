"""A Change Journal held in memory, for tests that need no database (ticket 22)."""

from __future__ import annotations


class MemoryJournal:
    def __init__(self):
        self.events: dict[tuple[str, str], dict] = {}

    def append(self, value: dict) -> dict:
        key = (value["producer"], value["event_key"])
        if self.events.setdefault(key, value) != value:
            raise ValueError("Producer event key already names different content")
        return {"event": value}

    def found(self, producer: str, event_keys: list[str]) -> set[str]:
        return {key for key in event_keys if (producer, key) in self.events}
