//! HTML reader: a document as people read it, not as its tags nest. Paths have
//! no any-depth step, and a web page nests its text and tables at any depth,
//! so the tree is flat:
//!
//! - `title`: the document's title text;
//! - `block`: each run of text outside a table, in document order, cut where
//!   a block element (a paragraph, a heading, a list item, a line break...)
//!   starts or ends;
//! - `row`: each table row in document order, as one record: `@table` is its
//!   table's number in the document and `@row` its number in the table (from
//!   1), and its cells are `c1`, `c2`... by position, as a CSV without a
//!   header names them. A table inside a cell is a table of its own, numbered
//!   after the one that holds it, and its text is not in the cell.
//!
//! Each value is an element holding its text (`$`), so `each: block` and
//! `each: row` iterate them; nothing repeats inside a record.
//!
//! Text is the visible text: entities decoded, script and style dropped,
//! whitespace (no-break space too) collapsed to one space and trimmed. An
//! empty block, row or cell is left out. The tokenizer is HTML5's, so an
//! unclosed or misnested tag never refuses the document.

use html5ever::tendril::StrTendril;
use html5ever::tokenizer::states::RawKind;
use html5ever::tokenizer::{BufferQueue, Tag, TagKind, Token, TokenSink, TokenSinkResult, Tokenizer, TokenizerOpts};

use crate::tree::El;
use crate::Rejected;

const BLOCKS: &[&str] = &[
    "address", "article", "aside", "blockquote", "body", "br", "caption", "center", "dd", "div", "dl", "dt",
    "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "html", "li",
    "main", "nav", "ol", "p", "pre", "section", "title", "ul",
];

#[derive(Default)]
struct Table {
    rows: Vec<Vec<String>>,
    row: Option<Vec<String>>,
    cell: Option<String>,
}

#[derive(Default)]
struct Sink {
    title: Option<String>,
    in_title: bool,
    skipping: Option<String>,
    text: String,
    blocks: Vec<String>,
    /// Open tables, innermost last; a closed table is kept in `done` at the
    /// place it opened, so tables stay in document order.
    open: Vec<(usize, Table)>,
    done: Vec<Option<Vec<Vec<String>>>>,
    max_records: usize,
    records: usize,
    over: bool,
}

/// Collapse whitespace, the no-break space included, to single spaces.
fn clean(text: &str) -> String {
    text.split(|c: char| c.is_whitespace() || c == '\u{a0}').filter(|w| !w.is_empty()).collect::<Vec<_>>().join(" ")
}

impl Sink {
    fn count(&mut self) {
        self.records += 1;
        self.over |= self.records > self.max_records;
    }

    fn flush_block(&mut self) {
        let text = clean(&std::mem::take(&mut self.text));
        if !text.is_empty() {
            self.count();
            self.blocks.push(text);
        }
    }

    fn end_cell(&mut self) {
        if let Some((_, table)) = self.open.last_mut() {
            if let Some(cell) = table.cell.take() {
                table.row.get_or_insert_with(Vec::new).push(clean(&cell));
            }
        }
    }

    fn end_row(&mut self) {
        self.end_cell();
        let finished = self.open.last_mut().and_then(|(_, table)| table.row.take());
        if let Some(row) = finished {
            if row.iter().any(|cell| !cell.is_empty()) {
                self.count();
                if let Some((_, table)) = self.open.last_mut() {
                    table.rows.push(row);
                }
            }
        }
    }

    fn start(&mut self, tag: &Tag) -> TokenSinkResult<()> {
        let name = &*tag.name;
        match name {
            "script" | "style" | "noscript" | "template" => {
                self.skipping = Some(name.to_string());
                return TokenSinkResult::RawData(if name == "script" { RawKind::ScriptData } else { RawKind::Rawtext });
            }
            "title" => self.in_title = true,
            "table" => {
                if self.open.is_empty() {
                    self.flush_block();
                }
                self.done.push(None);
                self.open.push((self.done.len() - 1, Table::default()));
            }
            "tr" if !self.open.is_empty() => self.end_row(),
            "td" | "th" if !self.open.is_empty() => {
                self.end_cell();
                if let Some((_, table)) = self.open.last_mut() {
                    table.cell = Some(String::new());
                }
            }
            _ if BLOCKS.contains(&name) => self.separate(),
            _ => {}
        }
        TokenSinkResult::Continue
    }

    fn end(&mut self, tag: &Tag) {
        let name = &*tag.name;
        match name {
            "title" => self.in_title = false,
            "table" if !self.open.is_empty() => {
                self.end_row();
                if let Some((at, table)) = self.open.pop() {
                    self.done[at] = Some(table.rows);
                }
            }
            "tr" if !self.open.is_empty() => self.end_row(),
            "td" | "th" if !self.open.is_empty() => self.end_cell(),
            _ if BLOCKS.contains(&name) => self.separate(),
            _ => {}
        }
    }

    /// A block element ends a block of text, or puts a space inside a cell.
    fn separate(&mut self) {
        match self.open.last_mut() {
            Some((_, table)) => {
                if let Some(cell) = table.cell.as_mut() {
                    cell.push(' ');
                }
            }
            None => self.flush_block(),
        }
    }

    fn characters(&mut self, text: &str) {
        if self.skipping.is_some() {
            return;
        }
        if self.in_title {
            self.title.get_or_insert_with(String::new).push_str(text);
            return;
        }
        match self.open.last_mut() {
            // Text in a table but outside a cell (stray text) belongs to no cell: kept out.
            Some((_, table)) => {
                if let Some(cell) = table.cell.as_mut() {
                    cell.push_str(text);
                }
            }
            None => self.text.push_str(text),
        }
    }
}

impl TokenSink for Sink {
    type Handle = ();

    fn process_token(&mut self, token: Token, _line: u64) -> TokenSinkResult<()> {
        match token {
            Token::TagToken(tag) => match tag.kind {
                TagKind::StartTag => return self.start(&tag),
                TagKind::EndTag => {
                    if self.skipping.as_deref() == Some(&*tag.name) {
                        self.skipping = None;
                    } else if self.skipping.is_none() {
                        self.end(&tag);
                    }
                }
            },
            Token::CharacterTokens(text) => self.characters(&text),
            Token::NullCharacterToken => {}
            Token::CommentToken(_) | Token::DoctypeToken(_) | Token::EOFToken | Token::ParseError(_) => {}
        }
        TokenSinkResult::Continue
    }
}

/// The document's title, blocks and tables. More than `max_records` blocks
/// and table rows together refuses it, as more records than declared do.
pub fn html(bytes: &[u8], max_records: usize) -> Result<El, Rejected> {
    let text = std::str::from_utf8(bytes).map_err(|e| Rejected::new("encoding", format!("not UTF-8: {e}")))?;
    let mut tokenizer = Tokenizer::new(Sink { max_records, ..Sink::default() }, TokenizerOpts::default());
    let mut queue = BufferQueue::default();
    queue.push_back(StrTendril::from_slice(text));
    let _ = tokenizer.feed(&mut queue);
    tokenizer.end();
    let mut sink = tokenizer.sink;
    sink.flush_block();
    while !sink.open.is_empty() {
        sink.end_row();
        if let Some((at, table)) = sink.open.pop() {
            sink.done[at] = Some(table.rows);
        }
    }
    if sink.over {
        return Err(Rejected::new("limit_exceeded", format!("more than {max_records} records")));
    }
    let text = |value: String| El { text: Some(value), ..El::default() };
    let mut document = El::default();
    if let Some(title) = sink.title.map(|t| clean(&t)).filter(|t| !t.is_empty()) {
        document.add_child("title".into(), text(title));
    }
    for block in sink.blocks {
        document.add_child("block".into(), text(block));
    }
    for (number, rows) in sink.done.into_iter().flatten().enumerate() {
        for (index, cells) in rows.into_iter().enumerate() {
            let mut row = El::default();
            row.attrs.insert("@table".into(), (number + 1).to_string());
            row.attrs.insert("@row".into(), (index + 1).to_string());
            for (position, cell) in cells.into_iter().enumerate() {
                row.add_child(format!("c{}", position + 1), text(cell));
            }
            document.add_child("row".into(), row);
        }
    }
    Ok(document)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tree::Child;

    fn texts(el: &El, name: &str) -> Vec<String> {
        match el.children.get(name) {
            None => vec![],
            Some(Child::One(one)) => vec![one.text.clone().unwrap_or_default()],
            Some(Child::Many(many)) => many.iter().map(|e| e.text.clone().unwrap_or_default()).collect(),
        }
    }

    /// Each table's rows of cell texts, regrouped by `@table` and checked against `@row`.
    fn rows(el: &El) -> Vec<Vec<Vec<String>>> {
        let rows = match el.children.get("row") {
            None => return vec![],
            Some(Child::One(one)) => vec![one],
            Some(Child::Many(many)) => many.iter().collect(),
        };
        let mut tables: Vec<Vec<Vec<String>>> = vec![];
        for row in rows {
            let table: usize = row.attrs["@table"].parse().unwrap();
            tables.resize(tables.len().max(table), vec![]);
            assert_eq!(row.attrs["@row"], (tables[table - 1].len() + 1).to_string());
            tables[table - 1].push((1..=row.children.len()).map(|c| texts(row, &format!("c{c}"))[0].clone()).collect());
        }
        tables
    }

    #[test]
    fn blocks_are_the_visible_text_in_order() {
        let el = html(b"<HTML><HEAD><TITLE> An  invented\nfiling </TITLE><STYLE>p{x:1}</STYLE></HEAD>\
            <BODY><P>First &amp; <B>bold</B>&nbsp;part<P>Second<BR>third<script>if (a<b) {}</script></BODY>", 100).unwrap();
        assert_eq!(texts(&el, "title"), ["An invented filing"]);
        assert_eq!(texts(&el, "block"), ["First & bold part", "Second", "third"]);
    }

    #[test]
    fn a_table_is_rows_of_cells_and_a_nested_table_comes_after() {
        let el = html(b"<p>Before</p><table><tr><th>Title</th><th>Amount</th></tr>\
            <tr><td>Common <div>stock</div></td><td>$ 1,000\xc2\xa0</td></tr>\
            <tr><td></td><td> </td></tr>\
            <tr><td><table><tr><td>inner</td></tr></table></td><td>outer</td></table><p>After", 100).unwrap();
        assert_eq!(texts(&el, "block"), ["Before", "After"]);
        assert_eq!(rows(&el), vec![
            vec![vec!["Title".to_string(), "Amount".into()], vec!["Common stock".into(), "$ 1,000".into()],
                 vec!["".into(), "outer".into()]],
            vec![vec!["inner".to_string()]],
        ]);
    }

    #[test]
    fn unclosed_and_misnested_tags_are_read() {
        // A cell tag outside any table means nothing, as in a browser: its text runs on.
        let el = html(b"<div><p>one<td>stray cell<table><tr><td>a<td>b<tr><td>c</div>", 100).unwrap();
        assert_eq!(texts(&el, "block"), ["onestray cell"]);
        assert_eq!(rows(&el), vec![vec![vec!["a".to_string(), "b".into()], vec!["c".into()]]]);
    }

    #[test]
    fn records_over_the_bound_refuse_and_non_utf8_refuses() {
        assert_eq!(html(b"<p>a<p>b<p>c", 2).unwrap_err().code, "limit_exceeded");
        assert!(html(b"<p>a<p>b", 2).is_ok());
        assert_eq!(html(b"<p>caf\xe9", 10).unwrap_err().code, "encoding");
    }
}
