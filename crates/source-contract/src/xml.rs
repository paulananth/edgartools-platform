//! XML reader from the Source Contract spec, §8.
//!
//! Contracts address elements by local name (`infoTable`, `cusip`). A
//! namespace prefix on the tag is removed before the name is stored; the
//! root's namespace is kept so a contract can require it. CDATA is text. A
//! DTD, an unclosed element or a mismatched end tag fails the document.

use quick_xml::events::Event;
use quick_xml::Reader;

use crate::tree::El;
use crate::Rejected;

/// One parsed document: its root's local name, its namespace and its tree.
pub struct Document {
    pub root: String,
    pub namespace: Option<String>,
    pub el: El,
}

fn local_name(qname: &[u8]) -> String {
    let bare = match qname.iter().rposition(|b| *b == b':') {
        Some(i) => &qname[i + 1..],
        None => qname,
    };
    String::from_utf8_lossy(bare).into_owned()
}

fn prefix(qname: &[u8]) -> Option<String> {
    let i = qname.iter().position(|b| *b == b':')?;
    Some(String::from_utf8_lossy(&qname[..i]).into_owned())
}

fn malformed(detail: impl ToString) -> Rejected {
    Rejected::new("malformed", detail)
}

/// The element's attributes, and its namespace declarations apart.
fn read_attrs(
    el: &mut El,
    attrs: quick_xml::events::attributes::Attributes,
) -> Result<Vec<(String, String)>, Rejected> {
    let mut declarations = Vec::new();
    for attr in attrs {
        let attr = attr.map_err(malformed)?;
        let key = attr.key.as_ref();
        let value = attr.unescape_value().map_err(malformed)?.into_owned();
        if key == b"xmlns" {
            declarations.push((String::new(), value));
        } else if let Some(name) = key.strip_prefix(b"xmlns:") {
            declarations.push((String::from_utf8_lossy(name).into_owned(), value));
        } else {
            el.attrs.insert(format!("@{}", local_name(key)), value);
        }
    }
    Ok(declarations)
}

struct Frame {
    name: String,
    el: El,
}

/// Parse one XML document.
pub fn parse_xml(bytes: &[u8]) -> Result<Document, Rejected> {
    let mut reader = Reader::from_reader(bytes);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut stack = vec![Frame { name: String::new(), el: El::default() }];
    let mut root: Option<(String, Option<String>)> = None;
    loop {
        let event = reader.read_event_into(&mut buf).map_err(malformed)?;
        match event {
            Event::DocType(_) => return Err(Rejected::new("dtd", "a DTD is not accepted")),
            Event::Start(_) | Event::Empty(_) => {
                let (start, empty) = match &event {
                    Event::Start(start) => (start, false),
                    Event::Empty(start) => (start, true),
                    _ => unreachable!(),
                };
                let raw = start.name().as_ref().to_vec();
                let mut el = El::default();
                let declarations = read_attrs(&mut el, start.attributes())?;
                if stack.len() == 1 {
                    if root.is_some() {
                        return Err(malformed("more than one root element"));
                    }
                    let wanted = prefix(&raw).unwrap_or_default();
                    let namespace = declarations.into_iter().find(|(p, _)| *p == wanted).map(|(_, uri)| uri);
                    root = Some((local_name(&raw), namespace));
                }
                if empty {
                    stack.last_mut().unwrap().el.add_child(local_name(&raw), el);
                } else {
                    stack.push(Frame { name: local_name(&raw), el });
                }
            }
            Event::Text(text) => {
                let text = text.unescape().map_err(malformed)?;
                stack.last_mut().unwrap().el.push_text(&text);
            }
            Event::CData(data) => {
                let text = String::from_utf8(data.into_inner().into_owned()).map_err(malformed)?;
                stack.last_mut().unwrap().el.push_text(&text);
            }
            Event::End(_) => {
                let frame = stack.pop().unwrap();
                let parent = stack.last_mut().ok_or_else(|| malformed("unbalanced end tag"))?;
                parent.el.add_child(frame.name, frame.el);
            }
            Event::Eof => break,
            _ => {}
        }
        buf.clear();
    }
    if stack.len() != 1 {
        return Err(malformed("an element is not closed"));
    }
    let (name, namespace) = root.ok_or_else(|| malformed("no root element"))?;
    let mut top = stack.pop().unwrap().el;
    let el = top.take_only_child(&name).ok_or_else(|| malformed("no root element"))?;
    Ok(Document { root: name, namespace, el })
}

pub fn strip_control_chars(bytes: &[u8]) -> Vec<u8> {
    bytes
        .iter()
        .copied()
        .filter(|b| !matches!(b, 0x00..=0x08 | 0x0b | 0x0c | 0x0e..=0x1f))
        .collect()
}
