"""The input step: every input becomes one DuckDB table per part.

Each part is read once into a table (a remote database stays a read-only view),
and later steps read tables only, never asking what format a part came from.

- CSV and Parquet are read by DuckDB directly, with a full type scan; a zip of
  CSV or Parquet files gives each member as a file. Any other file beside the
  tables (a readme, a metadata file, records) is listed as not read, with its
  reason; records there can be profiled as their own input. A CSV that is not UTF-8 is
  read as Windows-1252 (or Latin-1), and the findings say so. A table DuckDB
  cannot read is reported as not read, and the rest of the input is profiled.
- JSON, JSON Lines, XML and zip members are read by the Python standard
  library, flattened (nested objects become dotted columns, lists become child
  parts) and written as JSON Lines for DuckDB.
- A database is attached read-only from an environment variable, which is never
  printed; each of its tables is a part.

An input larger than the size limit is read once: a reservoir sample of its
records is kept, and `full_pass` reads it again for named columns only.
"""

from __future__ import annotations

import codecs
import csv
import gzip
import hashlib
import io
import json
import os
import random
import re
import shutil
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
TABULAR = {"csv", "parquet"}


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
    derived_from: str | None = None  # an entity found inside this part (embedded.py), not an input
    encoding: dict | None = None  # a CSV read from bytes that are not UTF-8: as what, and the evidence
    not_read: str | None = None  # why DuckDB could not read this table; it has no table

    @property
    def is_input(self) -> bool:
        """A part read from an input as it is: not a nested list, not an entity found inside a part."""
        return self.parent is None and self.derived_from is None

    @property
    def declared_format(self) -> str:
        """The format a Dataset Contract declares to read it: a tab-separated file is read as CSV
        here, and as `tsv` by the engine, which splits on tabs and does not unquote."""
        return "tsv" if self.format == "csv" and self.location.lower().rsplit("#", 1)[-1].endswith(".tsv") else self.format

    def finding(self, rows: int) -> dict:
        return {"kind": "table" if self.format in {"sqlite", "postgres", "duckdb"} else "file",
                "location": self.location, "format": self.declared_format, "bytes": self.bytes, "rows": rows,
                "sha256": self.sha256} | ({"encoding": self.encoding} if self.encoding else {})


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
    """An object of two or more lists of plain values, of one equal length: a table stored by column.

    Lists of records are not columns: two lists of objects that happen to be
    equally long (a document's transactions and its holdings) are separate parts.
    """
    lists = [v for v in value.values() if isinstance(v, list)]
    return (len(lists) >= 2 and len(lists) == len(value) and len({len(v) for v in lists}) == 1
            and all(not isinstance(_scalar(item), (dict, list)) for v in lists for item in v))


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
    if not suffix and path.is_file():
        return _sniff(path)
    return {"ndjson": "jsonl", "db": "sqlite", "sqlite3": "sqlite", "txt": "csv", "tsv": "csv"}.get(suffix, suffix)


def _sniff(path: Path) -> str:
    """A file with no suffix (captured files often have none): XML or JSON by its first character."""
    with path.open("rb") as handle:
        head = handle.read(512).lstrip(b"\xef\xbb\xbf \t\r\n")
    return "xml" if head.startswith(b"<") else "json" if head[:1] in (b"{", b"[") else ""


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


@dataclass
class Table:
    """One CSV or Parquet table of an input: the file read, where it came from, its part name."""
    file: Path  # on disk: the input's own file, or a zip member copied out to the work folder
    location: str  # the input's file, or `<zip>#<member>`
    name: str = ""
    readable: Path | None = None  # the file DuckDB reads (a UTF-8 copy of a CSV that is not UTF-8)
    encoding: dict | None = None
    unreadable: str | None = None  # why the bytes are no text the reader can take


RECORDS = {"json", "jsonl", "xml"}


def _set_aside(location: str, fmt: str, size: int) -> Part:
    """A file beside an input's tables that is not one of them: listed with its reason, never read."""
    why = ("records beside the tables; profile this file as its own input to read it" if fmt in RECORDS
           else "a document beside the tables, not profiled")
    stem = re.sub(r"[^0-9A-Za-z]+", "_", Path(location.rpartition("#")[2] or location).stem).strip("_") or "file"
    return Part(stem, location, fmt, size, not_read=f"not a table ({fmt}); {why}")


def _tables(path: Path, work: Path) -> tuple[list[Table], list[Part]] | None:
    """The CSV or Parquet tables of an input, a zip's members copied out to `work`, and every
    other file beside them, set aside with its reason (a readme, a metadata file); None when
    the input holds no table at all."""
    tables: list[Table] = []
    aside: list[Part] = []
    for file in _members(path):
        if format_of(file) != "zip":
            if format_of(file) in TABULAR:
                tables.append(Table(file, str(file)))
            else:
                aside.append(_set_aside(str(file), format_of(file), file.stat().st_size))
            continue
        with zipfile.ZipFile(file) as archive:
            # A zip made on a Mac carries `__MACOSX/._name` resource entries: no data.
            members = [i for i in archive.infolist() if not i.is_dir()
                       and not i.filename.startswith("__MACOSX/") and not Path(i.filename).name.startswith("._")]
            for info in members:
                fmt = format_of(Path(info.filename))
                if fmt not in TABULAR:
                    aside.append(_set_aside(f"{file}#{info.filename}", fmt, info.file_size))
                    continue
                # One folder per member: two members (or two zips) may share a file name.
                target = work / "members" / str(len(tables)) / Path(info.filename).name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as copy:
                    shutil.copyfileobj(source, copy)
                tables.append(Table(target, f"{file}#{info.filename}"))
    if not tables or len({format_of(t.file) for t in tables}) != 1:
        return None
    _name_tables(tables)
    taken = {t.name for t in tables}
    for part in aside:
        while part.name in taken:
            part.name += "_file"
        taken.add(part.name)
    return tables, aside


def _name_tables(tables: list[Table]) -> None:
    """Each table's part name: its file's stem, or, when two share a stem, the zip and the
    member's path (`2025_06_sched`, `a_t`). Names are never empty and never repeat."""
    stems = [t.file.stem for t in tables]
    for table in tables:
        if stems.count(table.file.stem) == 1:
            name = table.file.stem
        else:
            outer, _, member = table.location.rpartition("#")
            name = f"{Path(outer).stem}_{member}" if outer else "_".join(Path(table.location).parts[-2:])
            name = re.sub(r"\.(csv|parquet|txt|tsv)$", "", name, flags=re.I)
        table.name = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_") or "table"
    taken: set[str] = set()
    for table in tables:
        name, n = table.name, 1
        while table.name in taken:
            n += 1
            table.name = f"{name}_{n}"
        taken.add(table.name)


def _decode(table: Table, work: Path, index: int) -> None:
    """Set the file DuckDB reads. A CSV whose bytes are not UTF-8 is copied as UTF-8 from
    Windows-1252 when every byte is one of its characters, else Latin-1, and the encoding
    is recorded as inferred, with the first byte that is not UTF-8. A byte-order mark of
    UTF-16 or UTF-32, or a NUL byte, is no text these read: the table is not read."""
    table.readable = table.file
    if format_of(table.file) != "csv":
        return
    decoder = codecs.getincrementaldecoder("utf-8")()
    offset = 0
    with table.file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            if offset == 0 and chunk.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
                table.unreadable = "starts with a UTF-16 or UTF-32 byte-order mark; not read as text"
                return
            if b"\x00" in chunk:
                table.unreadable = f"a NUL byte at offset {offset + chunk.index(b'\x00')}; binary or UTF-16, not read as text"
                return
            try:
                decoder.decode(chunk)
            except UnicodeDecodeError as exc:
                if table.encoding is None:
                    table.encoding = {"first_invalid_byte_offset": offset + exc.start}
                decoder = codecs.getincrementaldecoder("utf-8")()  # keep scanning for NUL bytes
            offset += len(chunk)
    if table.encoding is None:
        return
    for encoding in ("windows-1252", "latin-1"):
        target = work / "utf8" / str(index) / table.file.name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with table.file.open("r", encoding=encoding, newline="") as source, \
                    target.open("w", encoding="utf-8", newline="") as copy:
                shutil.copyfileobj(source, copy, 1 << 20)
        except UnicodeDecodeError:
            continue
        table.readable = target
        table.encoding = {"read_as": encoding, "inferred": True, **table.encoding}
        return
    raise AssertionError("Latin-1 reads every byte")


def _irregular(con, file: Path, rows: int | None) -> str | None:
    """Why a CSV DuckDB loaded does not have one shape, or None. DuckDB reads leniently
    (a ragged file can load as one column, a preamble is skipped, an open quote kept),
    so the file is read again with the standard library in the dialect DuckDB found:
    every record must have the header's field count, a quote must close, nothing is
    skipped, and (when the whole file was loaded) the record count must equal the rows."""
    delimiter, quote, skipped, header = con.execute(
        f"SELECT Delimiter, Quote, SkipRows, HasHeader FROM sniff_csv({sql_text(str(file))}, sample_size=-1)").fetchone()
    if skipped:
        return f"the reader would skip its first {skipped} lines; not one table"
    if len(delimiter) != 1:
        return None  # a delimiter of several characters: the standard library cannot check it
    def shape(**quoting) -> tuple[str | None, int, int | None]:
        quote_char = quoting.get("quotechar")
        quotes = 0

        def lines(handle):
            nonlocal quotes
            for line in handle:
                quotes += line.count(quote_char) if quote_char else 0
                yield line

        with file.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(lines(handle), delimiter=delimiter, **quoting)
            width, records = None, 0
            try:
                for record in reader:
                    if width is None:
                        width = len(record)
                    elif record and len(record) != width:
                        return f"line {reader.line_num} has {len(record)} fields, the first line {width}", records, width
                    records += record != []
            except csv.Error as exc:
                return f"line {reader.line_num}: {exc}", records, width
        if quotes % 2:  # an escaped quote is doubled, so an odd count leaves one open
            return f"a quote that does not close (an odd number of {quote_char} in the file)", records, width
        return None, records, width

    if len(quote or "") == 1 and quote != "\x00":
        why, records, width = shape(quotechar=quote)
    else:
        # The reader found no quoting; a double quote that does not close would then be data.
        quoted, _, _ = shape(quotechar='"')
        if quoted:
            return f"read without quoting, but with double quotes {quoted}; not one way to read it"
        why, records, width = shape(quoting=csv.QUOTE_NONE)
    if why:
        return why
    if width == 1:
        with file.open(encoding="utf-8", newline="") as handle:
            first, second = handle.readline(), handle.readline()
        held = sorted(d for d in {",", ";", "|", "\t"} - {delimiter} if d in first and d in second)
        if held:
            return f"read as one column, but its first two lines hold {held[0]!r}; not one way to read it"
    if rows is not None and records - (1 if header else 0) != rows:
        return f"{records} records, but {rows} rows loaded"
    return None


def _encoding(tables: list[Table]) -> dict | None:
    """How a part's CSV files not in UTF-8 were read, and the `read.encoding` a reading
    contract declares for them: the engine reads utf-8 and windows-1252 only."""
    found = [t.encoding for t in tables if t.encoding]
    if not found:
        return None
    read_as = sorted({e["read_as"] for e in found})
    if read_as != ["windows-1252"]:
        declare = "none: a byte no encoding the engine reads defines; ask the publisher"
    else:
        declare = "windows-1252" if len(found) == len(tables) else ["utf-8", "windows-1252"]
    return {"read_as": read_as[0] if len(read_as) == 1 else read_as, "inferred": True,
            "files_not_utf8": len(found), "files": len(tables),
            "first_invalid_byte_offset": found[0]["first_invalid_byte_offset"], "declare": declare}


def _tabular(con, name: str, tables: list[Table], limit: int, sample: int, seed: int, location: str) -> list[Part]:
    """CSV or Parquet: tables with one header are one part; otherwise each table is its own part.

    Over the size limit, a seeded reservoir sample of rows is kept; the full file
    stays readable through `source_sql` for the key candidates' full passes. A
    table the reader cannot read, or reads as more than one shape, is a part with
    `not_read` and no table.
    """
    def header(table: Table) -> tuple:
        return tuple(r[0] for r in con.execute(
            f"DESCRIBE SELECT * FROM {_reader(table.readable, str(table.readable))}").fetchall())

    def each() -> list[Part]:
        return [p for t in tables for p in _tabular(con, t.name, [t], limit, sample, seed, t.location)]

    def unread(reason: str) -> list[Part]:
        (table,) = tables
        for t in tables:
            reason = reason.replace(str(t.readable), t.location).replace(str(t.file), t.location)
        return [Part(name, table.location, format_of(table.file), table.file.stat().st_size, not_read=reason[:300])]

    if len(tables) == 1 and tables[0].unreadable:
        return unread(tables[0].unreadable)
    if len(tables) > 1:
        if any(t.unreadable for t in tables):
            return each()
        try:
            if len({header(t) for t in tables}) > 1:
                return each()
        except duckdb.Error:
            return each()
    fmt = format_of(tables[0].file)
    size = sum(t.file.stat().st_size for t in tables)
    source = _reader(tables[0].file, [str(t.readable) for t in tables])
    sampled = size > limit
    rows = f" USING SAMPLE reservoir({int(sample)} ROWS) REPEATABLE ({int(seed)})" if sampled else ""
    try:
        con.execute(f"CREATE TABLE {sql_name(name)} AS SELECT * FROM {source}{rows}")
        problems = [] if fmt != "csv" else [
            (t, why) for t in tables
            if (why := _irregular(con, t.readable, None if sampled or len(tables) > 1 else
                                  con.execute(f"SELECT count(*) FROM {sql_name(name)}").fetchone()[0]))]
    except duckdb.Error as exc:
        if len(tables) > 1:
            return each()
        return unread(str(exc).splitlines()[0])
    if problems:
        con.execute(f"DROP TABLE {sql_name(name)}")
        if len(tables) > 1:
            return each()
        return unread(problems[0][1])
    part = Part(name, tables[0].location if len(tables) == 1 else location, fmt, size,
                scan="sampled" if sampled else "full", source_sql=source if sampled else None,
                encoding=_encoding(tables))
    if len(tables) == 1:
        part.sha256 = digest(tables[0].file)  # the table's own bytes: a zip member, or one file of a folder
    return [part]


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
    found = _tables(path, work)
    if found is not None:
        tables, aside = found
        for index, table in enumerate(tables):
            _decode(table, work, index)
        return _tabular(con, name, tables, limit, sample, seed, str(path)) + aside
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
        _load_json_lines(con, part, path)
        path.unlink()
    for part in sorted(files, key=lambda n: -n.count(".")):  # deepest first
        _fold_single_items(con, part)
        parts.append(Part(part, "", "", 0, scan=scan, parent=_enclosing(part, files) if part != name else None))
    return parts


def _enclosing(part: str, parts) -> str:
    """The nearest part a child part sits in: a list inside a nested object skips the object's name."""
    parent = part.rsplit(".", 1)[0]
    while parent not in parts and "." in parent:
        parent = parent.rsplit(".", 1)[0]
    return parent


def _load_json_lines(con, part: str, path: Path) -> None:
    """Load flattened rows with types from a full read.

    DuckDB fixes one format per date column; if a later value has another
    format (with or without milliseconds), that column is loaded as text and the
    profile judges its shape instead.
    """
    source = f"read_json({sql_text(str(path))}, format='newline_delimited', sample_size=-1, union_by_name=true"
    try:
        con.execute(f"CREATE TABLE {sql_name(part)} AS SELECT * FROM {source})")
    except duckdb.InvalidInputException:
        described = con.execute(f"DESCRIBE SELECT * FROM {source})").fetchall()
        types = {name: ("VARCHAR" if kind in {"DATE", "TIME", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE"} else kind)
                 for name, kind, *_ in described}
        columns = "{" + ", ".join(f"{sql_text(n)}: {sql_text(t)}" for n, t in types.items()) + "}"
        con.execute(f"CREATE TABLE {sql_name(part)} AS SELECT * FROM {source}, columns={columns})")


def _fold_single_items(con, child: str) -> None:
    """A list of one written as a single object (XML read as JSON often does this).

    Where the parent holds dotted columns `<list>.<field>` for the same list
    that became this child part, those rows move into the child as items at
    position 0, and the dotted columns are dropped, so every item is in one place.
    """
    if "." not in child:
        return
    parent, path = child.rsplit(".", 1)
    while not _exists(con, parent) and "." in parent:  # the list may sit inside a nested object
        parent, path = parent.rsplit(".", 1)[0], f"{parent.rsplit('.', 1)[1]}.{path}"
    if not _exists(con, parent):
        return
    columns = {r[0]: r[1] for r in con.execute(f"DESCRIBE {sql_name(parent)}").fetchall()}
    dotted = {c[len(path) + 1:]: c for c in columns if c.startswith(f"{path}.")}
    if not dotted:
        return
    child_columns = {r[0]: r[1] for r in con.execute(f"DESCRIBE {sql_name(child)}").fetchall()}
    for field, source in dotted.items():
        if field not in child_columns:
            con.execute(f"ALTER TABLE {sql_name(child)} ADD COLUMN {sql_name(field)} {columns[source]}")
            child_columns[field] = columns[source]
        elif child_columns[field] != columns[source]:
            # The two reads typed the field apart (a field null in every list item reads as JSON):
            # the child takes the single items' type when it holds no value, a number type both
            # can hold when both are numbers, else text, so no value is lost or quoted.
            f, kind = sql_name(field), _common_type(con, child, field, child_columns[field], columns[source])
            using = f" USING json_extract_string({f}, '$')" if child_columns[field] == "JSON" and kind == "VARCHAR" else ""
            con.execute(f"ALTER TABLE {sql_name(child)} ALTER {f} TYPE {kind}{using}")
            child_columns[field] = kind
    start = con.execute(f"SELECT coalesce(max({ROW}) + 1, 0) FROM {sql_name(child)}").fetchone()[0]
    filled = " OR ".join(f"{sql_name(c)} IS NOT NULL" for c in dotted.values())
    targets = ", ".join(sql_name(f) for f in dotted)
    values = ", ".join(f"json_extract_string({sql_name(c)}, '$')" if columns[c] == "JSON" and child_columns[f] == "VARCHAR"
                       else f"TRY_CAST({sql_name(c)} AS {child_columns[f]})" for f, c in dotted.items())
    con.execute(f"INSERT INTO {sql_name(child)} ({ROW}, {PARENT}, {POSITION}, {targets}) "
                f"SELECT {start} + row_number() OVER (ORDER BY {ROW}) - 1, {ROW}, 0, {values} "
                f"FROM {sql_name(parent)} WHERE {filled}")
    for source in dotted.values():
        con.execute(f"ALTER TABLE {sql_name(parent)} DROP COLUMN {sql_name(source)}")


NUMBERS = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "FLOAT", "DOUBLE")


def _common_type(con, child: str, field: str, held: str, single: str) -> str:
    if not con.execute(f"SELECT count({sql_name(field)}) FROM {sql_name(child)}").fetchone()[0]:
        return single
    if held in NUMBERS and single in NUMBERS:
        return "DOUBLE" if {"DOUBLE", "FLOAT"} & {held, single} else "HUGEINT" if "HUGEINT" in (held, single) else "BIGINT"
    return "VARCHAR"


def _exists(con, table: str) -> bool:
    return bool(con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [table]).fetchone()[0])


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
    paths = {c: c.split(".") for c in columns}
    for record in part.reopen():
        rows += 1
        for c, path in paths.items():
            value = _at(record, path)
            if value is None:
                nulls[c] += 1
            else:
                values[c].add(value)
    return {c: (values[c], rows, nulls[c]) for c in columns}


def _at(record: dict, path: list[str]):
    """The value of a flattened column in one record, read without flattening the rest."""
    value = record
    for i, key in enumerate(path):
        if not isinstance(value, dict):
            return None
        if key not in value:  # a key holding a dot itself
            joined = ".".join(path[i:])
            return _scalar(value.get(joined)) if joined in value else None
        value = _scalar(value[key])
    return None if isinstance(value, (dict, list)) else value
