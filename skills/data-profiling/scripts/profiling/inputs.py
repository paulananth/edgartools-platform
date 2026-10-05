"""The input step: every input becomes one DuckDB table per part.

Each part is read once into a table (a remote database stays a read-only view),
and later steps read tables only, never asking what format a part came from.

- CSV and Parquet are read by DuckDB directly, with a full type scan.
- JSON, JSON Lines, XML and zip members are read by the Python standard
  library, flattened (nested objects become dotted columns, lists become child
  parts) and written as JSON Lines for DuckDB.
- A database is attached read-only from an environment variable, which is never
  printed; each of its tables is a part.

An input larger than the size limit is read once: a reservoir sample of its
records is kept, and `full_pass` reads it again for named columns only.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import random
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator
from xml.etree import ElementTree

import duckdb

GB = 1024**3
DEFAULT_LIMIT = 5 * GB
SAMPLE_RECORDS = 100_000
ROW = "_row"  # the row number a flattened record gets in its part
PARENT = "_parent_row"  # a child row's parent row number
POSITION = "_position"  # a child row's place in its list


@dataclass
class Part:
    name: str
    location: str
    format: str
    bytes: int
    scan: str = "full"  # or "sampled"
    parent: str | None = None
    wrapper: str | None = None  # a top-level object key holding the records
    reopen: Callable[[], Iterator[dict]] | None = field(default=None, repr=False)
    source_sql: str | None = None  # a sampled table file, read again in full by this reader
    sha256: str | None = None

    def finding(self, rows: int) -> dict:
        return {"kind": "table" if self.format in {"sqlite", "postgres", "duckdb"} else "file",
                "location": self.location, "format": self.format, "bytes": self.bytes, "rows": rows,
                "sha256": self.sha256}


def digest(path: Path) -> str:
    """sha256 of a file, or of a folder's files (each relative path and content, in order)."""
    total = hashlib.sha256()
    for file in _members(path):
        if path.is_dir():
            total.update(str(file.relative_to(path)).encode() + b"\0")
        with open(file, "rb") as handle:
            while chunk := handle.read(1 << 22):
                total.update(chunk)
    return total.hexdigest()


# ---------------------------------------------------------------- flattening

def _scalar(value):
    """A `{"$": value}` wrapper (XML written as JSON) reads as its value."""
    if isinstance(value, dict) and "$" in value and all(k == "$" or k.startswith("@") for k in value):
        return value["$"]
    return value


def _columnar(value: dict) -> bool:
    """An object of two or more lists of one equal length: a table stored by column."""
    lists = [v for v in value.values() if isinstance(v, list)]
    return len(lists) >= 2 and len(lists) == len(value) and len({len(v) for v in lists}) == 1


class Flattener:
    """Turns records into flat rows per part; lists become child parts.

    Row numbers are kept per part across calls, so rows written in batches stay
    unique, and each child row names its parent row and its place in the list.
    """

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.out: dict[str, list[dict]] = {}

    def add(self, record: dict, part: str, parent: tuple[int, int] | None = None) -> dict:
        row = self.counts.get(part, 0)
        self.counts[part] = row + 1
        flat: dict = {ROW: row}
        if parent is not None:
            flat[PARENT], flat[POSITION] = parent
        self._columns(record, part, row, "", flat)
        self.out.setdefault(part, []).append(flat)
        return flat

    def _columns(self, record: dict, part: str, row: int, prefix: str, flat: dict) -> None:
        for key, value in record.items():
            name = f"{prefix}{key}"
            value = _scalar(value)
            if isinstance(value, dict) and _columnar(value):
                columns = list(value)
                for i in range(len(value[columns[0]])):
                    self.add({c: value[c][i] for c in columns}, f"{part}.{name}", (row, i))
            elif isinstance(value, dict):
                self._columns(value, part, row, f"{name}.", flat)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    item = _scalar(item)
                    self.add(item if isinstance(item, dict) else {"value": item}, f"{part}.{name}", (row, i))
            else:
                flat[name] = value

    def take(self) -> dict[str, list[dict]]:
        out, self.out = self.out, {}
        return out


# ---------------------------------------------------------------- record streams

WHOLE = 256 * 1024**2  # a JSON text up to this size is parsed whole


def _json_records(stream, size: int) -> tuple[str | None, Iterator[dict]]:
    """Records from a JSON text: an array, one object, or an object wrapping one array.

    A text up to WHOLE bytes is parsed whole. A larger one must be an array, or an
    object whose first key holds the array of records; it is read in chunks, one
    record at a time, so it never has to fit in memory.
    """
    if size <= WHOLE:
        data = json.load(stream)
        if isinstance(data, dict) and (table := _split_table(data)) is not None:
            return None, iter(table)
        if isinstance(data, list):
            return None, (d if isinstance(d, dict) else {"value": d} for d in data)
        if len(data) == 1 and isinstance(next(iter(data.values())), list):
            wrapper = next(iter(data))
            return wrapper, (d if isinstance(d, dict) else {"value": d} for d in data[wrapper])
        return None, iter([data])
    return _stream_json(stream)


def _split_table(data: dict) -> list[dict] | None:
    """A table written as one list of column names and one list of rows of that length."""
    lists = [v for v in data.values() if isinstance(v, list)]
    if len(lists) != 2:
        return None
    header = next((v for v in lists if v and all(isinstance(x, str) for x in v)), None)
    rows = next((v for v in lists if v is not header), None)
    if header is None or not rows or not all(isinstance(r, list) and len(r) == len(header) for r in rows):
        return None
    return [dict(zip(header, row)) for row in rows]


_BLANK = re.compile(r"[\s,]*")


def _stream_json(stream) -> tuple[str | None, Iterator[dict]]:
    """Records of a large JSON array, one at a time, in linear time.

    The reader moves an index through a buffer and drops what it has read only
    when it refills, so no record costs a copy of the buffer.
    """
    if not isinstance(stream, io.TextIOBase):
        stream = io.TextIOWrapper(stream, encoding="utf-8")  # a character may span two chunks
    decoder = json.JSONDecoder()
    buffer, pos = "", 0

    def fill() -> bool:
        nonlocal buffer, pos
        chunk = stream.read(1 << 22)
        buffer, pos = buffer[pos:] + chunk, 0
        return bool(chunk)

    def array() -> Iterator[dict]:
        nonlocal pos
        while True:
            pos = _BLANK.match(buffer, pos).end()  # blanks and the commas between records
            if pos >= len(buffer):
                if not fill():
                    return
                continue
            if buffer[pos] == "]":
                pos += 1
                return
            while True:
                try:
                    item, end = decoder.raw_decode(buffer, pos)
                    break
                except json.JSONDecodeError:
                    if not fill():
                        raise
            pos = end
            yield item if isinstance(item, dict) else {"value": item}

    fill()
    pos = len(buffer) - len(buffer.lstrip())
    if buffer.startswith("[", pos):
        pos += 1
        return None, array()
    while not (head := re.compile(r'\s*\{\s*"((?:[^"\\]|\\.)*)"\s*:\s*\[').match(buffer, pos)) \
            and len(buffer) < 4096 and fill():
        pass
    if not head:
        raise ValueError("a JSON text this large must be an array, or an object whose first key holds the records")
    pos = head.end()
    return json.loads(f'"{head.group(1)}"'), array()


def _jsonl_records(stream) -> Iterator[dict]:
    for line in stream:
        line = line.decode("utf-8") if isinstance(line, bytes) else line
        if line.strip():
            item = json.loads(line)
            yield item if isinstance(item, dict) else {"value": item}


def _xml_records(stream) -> Iterator[dict]:
    """Each child of the root element is one record; attributes become `@name` columns."""
    def convert(element) -> dict | str | None:
        tag = lambda e: e.tag.rsplit("}", 1)[-1]  # noqa: E731  (namespaces dropped)
        item: dict = {f"@{k.rsplit('}', 1)[-1]}": v for k, v in element.attrib.items()}
        children = list(element)
        for child in children:
            value = convert(child)
            key = tag(child)
            if key in item:
                item[key] = item[key] if isinstance(item[key], list) else [item[key]]
                item[key].append(value)
            else:
                item[key] = value
        text = (element.text or "").strip()
        if not children:
            return {**item, "$": text} if item else (text or None)
        return item

    depth, root = 0, None
    for event, element in ElementTree.iterparse(stream, events=("start", "end")):
        if event == "start":
            depth += 1
            root = element if depth == 1 else root
        else:
            depth -= 1
            if depth == 1:
                value = convert(element)
                yield value if isinstance(value, dict) else {"value": value}
                root.clear()


# ---------------------------------------------------------------- registering

def format_of(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return {"ndjson": "jsonl", "db": "sqlite", "sqlite3": "sqlite", "txt": "csv", "tsv": "csv"}.get(suffix, suffix)


def sql_name(part: str) -> str:
    return '"' + part.replace('"', '""') + '"'


def sql_text(value) -> str:
    """A SQL literal: a string, or a list of strings (views and ATTACH take no parameters)."""
    if isinstance(value, list):
        return "[" + ", ".join(sql_text(v) for v in value) + "]"
    return "'" + str(value).replace("'", "''") + "'"


def _members(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*") if p.is_file() and not p.name.startswith(".")) if path.is_dir() else [path]


def _open_streams(path: Path) -> list[tuple[str, int, Callable]]:
    """(format, bytes, opener) for each file, zip members included."""
    found = []
    for file in _members(path):
        if format_of(file) == "zip":
            with zipfile.ZipFile(file) as archive:
                found += [(format_of(Path(i.filename)), i.file_size,
                           lambda f=file, n=i.filename: zipfile.ZipFile(f).open(n))
                          for i in archive.infolist() if not i.is_dir()]
        else:
            found.append((format_of(file), file.stat().st_size, lambda f=file: open(f, "rb")))
    return found


def _record_reader(path: Path) -> tuple[str, Callable[[], Iterator[dict]], list]:
    """The format of a record input, a function that reads its records afresh, and the wrapper keys seen."""
    streams = _open_streams(path)
    formats = {fmt for fmt, _, _ in streams}
    if len(formats) != 1 or not formats <= {"json", "jsonl", "xml"}:
        raise ValueError(f"{path}: one part holds JSON, JSON Lines or XML records of one format, found {sorted(formats)}")
    fmt = formats.pop()
    wrappers: list = []

    def records() -> Iterator[dict]:
        for _, size, opener in streams:
            with opener() as stream:
                if fmt == "json":
                    wrapper, items = _json_records(stream, size)
                    wrappers.append(wrapper)
                    yield from items
                elif fmt == "jsonl":
                    yield from _jsonl_records(stream)
                else:
                    yield from _xml_records(stream)
    return fmt, records, wrappers


def size_of(path: Path) -> int:
    return sum(size for _, size, _ in _open_streams(path))


def _tabular(con, name: str, files: list[Path], size: int, limit: int, sample: int, seed: int) -> list[Part]:
    """CSV or Parquet: files with one header are one part; otherwise each file is its own part.

    Over the size limit, a seeded reservoir sample of rows is kept; the full file
    stays readable through `source_sql` for the key candidates' full passes.
    """
    def header(file: Path) -> tuple:
        return tuple(r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {_reader(file, str(file))}").fetchall())

    if len(files) > 1 and len({header(f) for f in files}) > 1:
        return [p for f in files for p in _tabular(con, f.stem, [f], f.stat().st_size, limit, sample, seed)]
    fmt = format_of(files[0])
    source = _reader(files[0], [str(f) for f in files])
    sampled = size > limit
    rows = f" USING SAMPLE reservoir({int(sample)} ROWS) REPEATABLE ({int(seed)})" if sampled else ""
    con.execute(f"CREATE TABLE {sql_name(name)} AS SELECT * FROM {source}{rows}")
    return [Part(name, str(files[0]) if len(files) == 1 else str(files[0].parent), fmt, size,
                 scan="sampled" if sampled else "full", source_sql=source if sampled else None)]


def _reader(file: Path, source) -> str:
    """The DuckDB reader for a tabular file; CSV types come from a full scan, not a sample."""
    if format_of(file) == "parquet":
        return f"read_parquet({sql_text(source)})"
    return f"read_csv({sql_text(source)}, sample_size=-1)"


def register(con: duckdb.DuckDBPyConnection, name: str, location: str, work: Path,
             limit: int = DEFAULT_LIMIT, sample: int = SAMPLE_RECORDS, seed: int = 0) -> list[Part]:
    """Register one input as tables; returns its parts, child parts included.

    `location` is a file, a folder, a zip, or `env:<VARIABLE>` naming a database.
    """
    if location.startswith("env:"):
        return _attach(con, name, location[4:])
    path = Path(location).expanduser()
    if format_of(path) in {"sqlite", "duckdb"}:
        return _attach_file(con, name, path, format_of(path))
    files = _members(path)
    if {format_of(f) for f in files} <= {"csv", "parquet"} and len({format_of(f) for f in files}) == 1:
        return _tabular(con, name, files, sum(f.stat().st_size for f in files), limit, sample, seed)
    fmt, records, wrappers = _record_reader(path)
    size = size_of(path)
    scan = "sampled" if size > limit else "full"
    parts = _write_records(con, name, records(), work, scan, sample, seed)
    for part in parts:
        part.location, part.bytes, part.format = str(path), size, fmt
        part.wrapper = next((w for w in wrappers if w), None)
        part.reopen = records
    return parts


def _write_records(con, name: str, records: Iterator[dict], work: Path, scan: str, sample: int, seed: int) -> list[Part]:
    work.mkdir(parents=True, exist_ok=True)
    flattener = Flattener()
    files: dict[str, Path] = {}

    def spill() -> None:
        # Compressed, and deleted once loaded: flattened rows repeat their column names.
        for part, rows in flattener.take().items():
            target = files.setdefault(part, work / f"{part}.jsonl.gz")
            with gzip.open(target, "at", encoding="utf-8", compresslevel=1) as handle:
                handle.writelines(json.dumps(row, default=str) + "\n" for row in rows)

    if scan == "sampled":
        chosen: list[dict] = []
        rng = random.Random(seed)
        for i, record in enumerate(records):  # reservoir sampling (algorithm R)
            if i < sample:
                chosen.append(record)
            elif (j := rng.randint(0, i)) < sample:
                chosen[j] = record
        records = iter(chosen)
    for row, record in enumerate(records):
        flattener.add(record, name)
        if row % 10_000 == 9_999:
            spill()
    spill()
    parts = []
    for part, path in sorted(files.items()):
        con.execute(f"CREATE TABLE {sql_name(part)} AS SELECT * FROM read_json({sql_text(str(path))}, "
                    "format='newline_delimited', sample_size=-1, union_by_name=true)")
        path.unlink()
        parts.append(Part(part, "", "", 0, scan=scan, parent=part.rsplit(".", 1)[0] if part != name else None))
    return parts


def _attach_file(con, name: str, path: Path, fmt: str) -> list[Part]:
    con.execute(f"ATTACH {sql_text(str(path))} AS {sql_name(name)} (TYPE {fmt}, READ_ONLY)")
    return _attached(con, name, str(path), fmt, copy=True)


def _attach(con, name: str, variable: str) -> list[Part]:
    """A database whose address is in an environment variable; the address is never printed."""
    url = os.environ.get(variable)
    if not url:
        raise SystemExit(f"set {variable} to the read-only database address (outside the chat)")
    kind = "postgres" if url.startswith(("postgres://", "postgresql://")) else "sqlite"
    try:
        con.execute(f"ATTACH {sql_text(url)} AS {sql_name(name)} (TYPE {kind}, READ_ONLY)")
    except duckdb.Error as exc:
        raise SystemExit(f"{variable}: the database did not answer ({type(exc).__name__})") from None
    return _attached(con, name, f"${variable}", kind)


def _attached(con, name: str, location: str, fmt: str, copy: bool = False) -> list[Part]:
    """Each table of an attached database is a part: copied when the file is local, else a view."""
    tables = con.execute("SELECT schema_name, table_name, estimated_size FROM duckdb_tables() "
                         "WHERE database_name = ? ORDER BY 1, 2", [name]).fetchall()
    parts = []
    for schema, table, _ in tables:
        part = table if schema in {"main", "public"} else f"{schema}.{table}"
        con.execute(f"CREATE {'TABLE' if copy else 'VIEW'} {sql_name(part)} AS "
                    f"SELECT * FROM {sql_name(name)}.{sql_name(schema)}.{sql_name(table)}")
        parts.append(Part(part, f"{location}#{schema}.{table}", fmt, 0))
    return parts


def full_values(part: Part, columns: list[str], con=None) -> dict[str, tuple[set, int, int]]:
    """Read a sampled top-level part again, whole, once: per column its distinct values, rows and empty rows."""
    if part.source_sql is not None:
        found = {}
        for c in columns:
            rows, filled = con.execute(f"SELECT count(*), count({sql_name(c)}) FROM {part.source_sql}").fetchone()
            values = {r[0] for r in con.execute(f"SELECT DISTINCT CAST({sql_name(c)} AS VARCHAR) FROM "
                                                f"{part.source_sql} WHERE {sql_name(c)} IS NOT NULL").fetchall()}
            found[c] = (values, rows, rows - filled)
        return found
    if part.reopen is None or part.parent is not None:
        raise ValueError(f"{part.name}: a full pass reads a top-level part")
    values: dict[str, set] = {c: set() for c in columns}
    nulls = dict.fromkeys(columns, 0)
    rows = 0
    for record in part.reopen():
        flat = Flattener().add(record, part.name)
        rows += 1
        for c in columns:
            if flat.get(c) is None:
                nulls[c] += 1
            else:
                values[c].add(flat[c])
    return {c: (values[c], rows, nulls[c]) for c in columns}
