//! HTML reader: a page as people read it, flat (READING.md, "An HTML page").
//! html5ever builds the tree as a browser does (an unclosed or misnested tag,
//! stray text in a table), then one walk in page order cuts it into the
//! title, text blocks and table rows, each with its place in the page.

use html5ever::tendril::TendrilSink;
use html5ever::{parse_document, ParseOpts};
use markup5ever_rcdom::{Handle, NodeData, RcDom};

use crate::tree::El;
use crate::Rejected;

/// Text transformations take at most 1 MiB, so no block may be larger.
const MAX_BLOCK: usize = 1024 * 1024;

const BLOCKS: &[&str] = &[
    "address", "article", "aside", "blockquote", "body", "br", "caption", "center", "dd", "div", "dl", "dt",
    "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
    "main", "nav", "ol", "p", "pre", "section", "ul",
];
const HIDDEN: &[&str] = &["script", "style", "noscript", "template", "svg", "math", "head"];

/// A kept block or row: its place in the page, its table and row numbers (a
/// row only), and its texts (a block has one).
struct Record {
    place: usize,
    table: Option<(usize, usize)>,
    texts: Vec<String>,
}

/// A row being read: its place, its table's number and its cells so far.
struct OpenRow {
    place: usize,
    table: usize,
    cells: Vec<String>,
}

struct Walk {
    max_records: usize,
    records: Vec<Record>,
    text: String,
    tables: usize,
    rows: Vec<OpenRow>,
    /// Each open table, innermost last: its number and the rows kept so far.
    open: Vec<(usize, usize)>,
    cells: Vec<String>,
    places: usize,
}

/// Collapse whitespace, the no-break space included, to single spaces.
fn clean(text: &str) -> String {
    text.split(|c: char| c.is_whitespace() || c == '\u{a0}').filter(|w| !w.is_empty()).collect::<Vec<_>>().join(" ")
}

impl Walk {
    fn place(&mut self) -> usize {
        self.places += 1;
        self.places
    }

    fn keep(&mut self, record: Record) -> Result<(), Rejected> {
        if self.records.len() == self.max_records {
            return Err(Rejected::new("limit_exceeded", format!("more than {} records", self.max_records)));
        }
        self.records.push(record);
        Ok(())
    }

    fn flush(&mut self) -> Result<(), Rejected> {
        let text = clean(&std::mem::take(&mut self.text));
        if text.len() > MAX_BLOCK {
            return Err(Rejected::new("limit_exceeded", format!("a block of {} bytes is over {MAX_BLOCK}", text.len())));
        }
        if !text.is_empty() {
            let place = self.place();
            self.keep(Record { place, table: None, texts: vec![text] })?;
        }
        Ok(())
    }

    /// Text goes to the innermost open cell, else to the current block.
    fn push(&mut self, text: &str) {
        match self.cells.last_mut() {
            Some(cell) => cell.push_str(text),
            None => self.text.push_str(text),
        }
    }

    /// A block element ends a block of text, or puts a space inside a cell.
    fn separate(&mut self) -> Result<(), Rejected> {
        if self.cells.is_empty() {
            self.flush()
        } else {
            self.push(" ");
            Ok(())
        }
    }

    fn walk(&mut self, node: &Handle, plain: bool) -> Result<(), Rejected> {
        match &node.data {
            NodeData::Text { contents } => {
                let contents = contents.borrow();
                if !plain {
                    self.push(&contents);
                    return Ok(());
                }
                // Plain and preformatted text cut blocks at blank lines.
                let mut parts = contents.split("\n\n").peekable();
                while let Some(part) = parts.next() {
                    self.push(part);
                    if parts.peek().is_some() {
                        self.separate()?;
                    }
                }
                Ok(())
            }
            NodeData::Element { name, attrs, .. } => {
                let tag = &*name.local;
                if HIDDEN.contains(&tag) {
                    return Ok(());
                }
                match tag {
                    "table" => {
                        if self.cells.is_empty() {
                            self.flush()?;
                        }
                        self.tables += 1;
                        self.open.push((self.tables, 0));
                        self.children(node, plain)?;
                        self.open.pop();
                        Ok(())
                    }
                    "tr" if !self.open.is_empty() => {
                        let place = self.place();
                        let table = self.open.last().map_or(0, |open| open.0);
                        self.rows.push(OpenRow { place, table, cells: Vec::new() });
                        self.children(node, plain)?;
                        let row = self.rows.pop().expect("the row opened above");
                        if row.cells.iter().any(|cell| !cell.is_empty()) {
                            let open = self.open.last_mut().expect("the table holding the row");
                            open.1 += 1;
                            let number = open.1;
                            self.keep(Record { place: row.place, table: Some((row.table, number)), texts: row.cells })?;
                        }
                        Ok(())
                    }
                    "td" | "th" if !self.rows.is_empty() => {
                        self.cells.push(String::new());
                        self.children(node, plain)?;
                        let text = clean(&self.cells.pop().expect("the cell opened above"));
                        // A spanning cell keeps the next cells at their columns.
                        let span = attrs.borrow().iter().find(|a| &*a.name.local == "colspan")
                            .and_then(|a| a.value.trim().parse::<usize>().ok()).unwrap_or(1).clamp(1, 1000);
                        let cells = &mut self.rows.last_mut().expect("the row holding the cell").cells;
                        cells.push(text);
                        cells.extend(std::iter::repeat_n(String::new(), span - 1));
                        Ok(())
                    }
                    _ if BLOCKS.contains(&tag) => {
                        self.separate()?;
                        self.children(node, plain || tag == "pre")?;
                        self.separate()
                    }
                    _ => self.children(node, plain),
                }
            }
            NodeData::Document => self.children(node, plain),
            _ => Ok(()),
        }
    }

    fn children(&mut self, node: &Handle, plain: bool) -> Result<(), Rejected> {
        for child in node.children.borrow().iter() {
            self.walk(child, plain)?;
        }
        Ok(())
    }
}

fn find(node: &Handle, tag: &str) -> Option<Handle> {
    if let NodeData::Element { name, .. } = &node.data {
        if &*name.local == tag {
            return Some(node.clone());
        }
    }
    node.children.borrow().iter().find_map(|child| find(child, tag))
}

fn text_of(node: &Handle, out: &mut String) {
    match &node.data {
        NodeData::Text { contents } => out.push_str(&contents.borrow()),
        _ => node.children.borrow().iter().for_each(|child| text_of(child, out)),
    }
}

/// A body of text and no element: a plain-text page.
fn is_plain(body: &Handle) -> bool {
    !body.children.borrow().iter().any(|child| matches!(child.data, NodeData::Element { .. }))
}

fn element(text: String, attrs: &[(&str, usize)]) -> El {
    let mut el = El { text: Some(text), ..El::default() };
    for (name, value) in attrs {
        el.attrs.insert(format!("@{name}"), value.to_string());
    }
    el
}

/// The page's title, blocks and table rows. More blocks and rows together than
/// `max_records` refuses it, as more records than declared do.
pub fn html(bytes: &[u8], max_records: usize) -> Result<El, Rejected> {
    // `formats::decode` hands over UTF-8 only; a direct caller may not.
    let text = std::str::from_utf8(bytes).map_err(|e| Rejected::new("encoding", format!("not UTF-8: {e}")))?;
    let dom = parse_document(RcDom::default(), ParseOpts::default()).one(text);
    let mut walk = Walk { max_records, records: Vec::new(), text: String::new(), tables: 0, rows: Vec::new(),
                          open: Vec::new(), cells: Vec::new(), places: 0 };
    if let Some(body) = find(&dom.document, "body") {
        walk.walk(&body, is_plain(&body))?;
        walk.flush()?;
    }
    let mut document = El::default();
    if let Some(title) = find(&dom.document, "head").and_then(|head| find(&head, "title")) {
        let mut out = String::new();
        text_of(&title, &mut out);
        let title = clean(&out);
        if !title.is_empty() {
            document.add_child("title".into(), El { text: Some(title), ..El::default() });
        }
    }
    walk.records.sort_by_key(|record| record.place);
    for record in walk.records {
        match record.table {
            None => {
                let text = record.texts.into_iter().next().unwrap_or_default();
                document.add_child("block".into(), element(text, &[("at", record.place)]));
            }
            Some((table, number)) => {
                let mut row = element(String::new(), &[("at", record.place), ("table", table), ("row", number)]);
                row.text = None;
                for (position, cell) in record.texts.into_iter().enumerate() {
                    row.add_child(format!("c{}", position + 1), El { text: Some(cell), ..El::default() });
                }
                document.add_child("row".into(), row);
            }
        }
    }
    Ok(document)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tree::Child;

    fn all<'a>(el: &'a El, name: &str) -> Vec<&'a El> {
        match el.children.get(name) {
            None => vec![],
            Some(Child::One(one)) => vec![one],
            Some(Child::Many(many)) => many.iter().collect(),
        }
    }

    fn texts(el: &El, name: &str) -> Vec<String> {
        all(el, name).iter().map(|e| e.text.clone().unwrap_or_default()).collect()
    }

    /// Each row as (table, row, cells).
    fn rows(el: &El) -> Vec<(String, String, Vec<String>)> {
        all(el, "row").iter().map(|row| (row.attrs["@table"].clone(), row.attrs["@row"].clone(),
            (1..=row.children.len()).map(|c| texts(row, &format!("c{c}"))[0].clone()).collect())).collect()
    }

    /// Every block and row in page order, by `@at`, as its first text.
    fn order(el: &El) -> Vec<String> {
        let mut found: Vec<(usize, String)> = all(el, "block").iter()
            .map(|b| (b.attrs["@at"].parse().unwrap(), b.text.clone().unwrap()))
            .chain(all(el, "row").iter().map(|r| (r.attrs["@at"].parse().unwrap(), texts(r, "c1")[0].clone())))
            .collect();
        found.sort();
        found.into_iter().map(|(_, text)| text).collect()
    }

    #[test]
    fn blocks_are_the_visible_text_in_order() {
        let el = html(b"<HTML><HEAD><TITLE> An  invented\nfiling </TITLE><STYLE>p{x:1}</STYLE></HEAD>\
            <BODY><P>First &amp; <B>bold</B>&nbsp;part<P>Second<BR>third<svg><title>icon</title></svg>\
            <script>if (a<b) {}</script></BODY>", 100).unwrap();
        assert_eq!(texts(&el, "title"), ["An invented filing"]);
        assert_eq!(texts(&el, "block"), ["First & bold part", "Second", "third"]);
    }

    #[test]
    fn a_table_is_rows_of_cells_and_a_nested_table_is_its_own() {
        let el = html(b"<p>Before</p><table><caption>The fees</caption><tr><th colspan=2>Title</th><th>Amount</th></tr>\
            <tr><td>Common <div>stock</div></td><td></td><td>$ 1,000\xc2\xa0</td></tr>\
            <tr><td></td><td> </td></tr>\
            <tr><td><table><tr><td>inner</td></tr></table></td><td>outer</td></table><p>After", 100).unwrap();
        assert_eq!(rows(&el), vec![
            ("1".to_string(), "1".to_string(), vec!["Title".to_string(), "".into(), "Amount".into()]),
            ("1".into(), "2".into(), vec!["Common stock".into(), "".into(), "$ 1,000".into()]),
            ("1".into(), "3".into(), vec!["".into(), "outer".into()]),
            ("2".into(), "1".into(), vec!["inner".into()]),
        ]);
        assert_eq!(order(&el), ["Before", "The fees", "Title", "Common stock", "", "inner", "After"]);
    }

    #[test]
    fn misnested_tags_and_stray_table_text_read_as_a_browser_shows_them() {
        // Stray text in a table shows before it; a stray end tag inside the inner table is ignored,
        // so its end tag closes it and later text is in the outer cell, still open, as a browser shows it.
        let el = html(b"<table>stray<tr><td>a<td><table><tr><td>x</td></tr></td></table><p>later", 100).unwrap();
        assert_eq!(texts(&el, "block"), ["stray"]);
        assert_eq!(rows(&el).into_iter().map(|r| r.2).collect::<Vec<_>>(),
                   vec![vec!["a".to_string(), "later".into()], vec!["x".to_string()]]);
    }

    #[test]
    fn plain_and_preformatted_text_cut_blocks_at_blank_lines() {
        let el = html(b"First line\nstill first\n\nSecond", 100).unwrap();
        assert_eq!(texts(&el, "block"), ["First line still first", "Second"]);
        let el = html(b"<p>one\n\nparagraph</p><pre>a\n\nb</pre>", 100).unwrap();
        assert_eq!(texts(&el, "block"), ["one paragraph", "a", "b"]);
    }

    #[test]
    fn records_over_the_bound_and_a_block_over_1_mib_refuse() {
        assert_eq!(html(b"<p>a<p>b<p>c", 2).unwrap_err().code, "limit_exceeded");
        assert!(html(b"<p>a<p>b", 2).is_ok());
        let long = format!("<p>{}</p>", "x ".repeat(MAX_BLOCK));
        assert_eq!(html(long.as_bytes(), 10).unwrap_err().code, "limit_exceeded");
    }
}
