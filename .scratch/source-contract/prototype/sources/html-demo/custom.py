"""PROTOTYPE — a table reader (ticket 04 Q4's second custom shape): Bronze Artifact bytes → rows."""

from html.parser import HTMLParser

from source_engine import Reject, table_reader


class _Cells(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell, self._in = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._in, self._cell = True, []
        elif tag == "br" and self._in:
            self._cell.append("\n")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._row.append("".join(self._cell).strip())
            self._in = False
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)

    def handle_data(self, data):
        if self._in:
            self._cell.append(data)


@table_reader("summary_comp_table", version=1)
def summary_comp_table(raw: bytes):
    p = _Cells()
    p.feed(raw.decode("utf-8"))
    body = [r for r in p.rows[1:] if r and r[0] != "Total"]
    if not body:
        raise Reject("no executive rows in the table")
    for name_and_title, year, salary in body:
        name, _, title = name_and_title.partition("\n")
        yield {"exec_name": name.strip(), "title": title.strip() or None, "fiscal_year": int(year),
               "salary": float(salary.replace(",", "")) if salary else None}
