"""Frozen pre-retirement JSON oracle; qualification only, never a runtime reader.

Copied from gleif_source at cffaf679. Kept independent from the replacement
engine to detect typed-value and refusal regressions.
"""
from typing import IO
import ijson

class Conflict(ValueError):
    pass


class _BoundedReader:
    def __init__(self, stream: IO[bytes], maximum: int, record_limit: int):
        self.stream, self.maximum, self.record_limit = stream, maximum, record_limit
        self.total = self.since_record = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise Conflict("Unbounded native source read")
        raw = self.stream.read(min(size, 65536))
        self.total += len(raw)
        self.since_record += len(raw)
        if self.total > self.maximum or self.since_record > self.record_limit + 65536:
            raise Conflict("GLEIF expanded file or record exceeds bound")
        return raw


def _json_records(stream: _BoundedReader, wrapper: str):
    events = iter(ijson.basic_parse(stream, use_float=True))

    def expect(event, value=None):
        if next(events) != (event, value):
            raise Conflict("Unexpected GLEIF JSON structure")

    def value(first, depth=0):
        if depth > 64:
            raise Conflict("GLEIF nesting exceeds bound")
        event, item = first
        if event == "start_map":
            result = {}
            while (entry := next(events))[0] != "end_map":
                if entry[0] != "map_key" or entry[1] in result:
                    raise Conflict("Duplicate or invalid GLEIF JSON key")
                result[entry[1]] = value(next(events), depth + 1)
            return result
        if event == "start_array":
            items = []
            while (entry := next(events))[0] != "end_array":
                items.append(value(entry, depth + 1))
            return items
        if event not in {"string", "number", "boolean", "null"}:
            raise Conflict("Invalid GLEIF JSON value")
        return item

    expect("start_map")
    expect("map_key", wrapper)
    expect("start_array")
    while (entry := next(events))[0] != "end_array":
        if entry[0] != "start_map":
            raise Conflict("Native GLEIF record must be an object")
        record = value(entry)
        stream.since_record = 0
        yield record
    expect("end_map")
    if next(events, None) is not None:
        raise Conflict("Trailing GLEIF JSON data")
