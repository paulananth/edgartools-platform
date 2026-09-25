//! XML reader from the Source Contract spec, §8.
//!
//! The 13F contract addresses elements by local name (`infoTable`, `cusip`).
//! A namespace prefix on the tag is removed before the name is stored.

use std::collections::BTreeMap;

use quick_xml::events::Event;
use quick_xml::Reader;

#[derive(Clone, Debug)]
pub struct El {
    pub text: Option<String>,
    pub attrs: BTreeMap<String, String>,
    pub children: BTreeMap<String, Child>,
}

#[derive(Clone, Debug)]
pub enum Child {
    One(El),
    Many(Vec<El>),
}

impl El {
    fn new() -> Self {
        Self {
            text: None,
            attrs: BTreeMap::new(),
            children: BTreeMap::new(),
        }
    }
}

struct Frame {
    name: String,
    el: El,
}

fn local_name(qname: &[u8]) -> String {
    let bare = match qname.iter().rposition(|b| *b == b':') {
        Some(i) => &qname[i + 1..],
        None => qname,
    };
    String::from_utf8_lossy(bare).into_owned()
}

fn add_child(parent: &mut El, name: String, child: El) {
    match parent.children.remove(&name) {
        None => {
            parent.children.insert(name, Child::One(child));
        }
        Some(Child::One(prev)) => {
            parent.children.insert(name, Child::Many(vec![prev, child]));
        }
        Some(Child::Many(mut rows)) => {
            rows.push(child);
            parent.children.insert(name, Child::Many(rows));
        }
    }
}

fn apply_attrs(el: &mut El, attrs: quick_xml::events::attributes::Attributes) {
    for attr in attrs.flatten() {
        let key = format!("@{}", local_name(attr.key.as_ref()));
        let value = String::from_utf8_lossy(attr.value.as_ref()).into_owned();
        el.attrs.insert(key, value);
    }
}

/// Parse one XML document. `Err` means the bytes are not XML.
pub fn parse_xml(bytes: &[u8]) -> Result<(String, El), String> {
    let mut reader = Reader::from_reader(bytes);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut stack = vec![Frame {
        name: String::new(),
        el: El::new(),
    }];
    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(event)) => {
                let raw = event.name().as_ref().to_vec();
                let mut el = El::new();
                apply_attrs(&mut el, event.attributes());
                stack.push(Frame {
                    name: local_name(&raw),
                    el,
                });
            }
            Ok(Event::Empty(event)) => {
                let raw = event.name().as_ref().to_vec();
                let mut el = El::new();
                apply_attrs(&mut el, event.attributes());
                let name = local_name(&raw);
                add_child(&mut stack.last_mut().unwrap().el, name, el);
            }
            Ok(Event::Text(event)) => {
                let text = event.unescape().map_err(|e| e.to_string())?;
                if !text.is_empty() {
                    let current = &mut stack.last_mut().unwrap().el.text;
                    match current {
                        Some(existing) => existing.push_str(&text),
                        None => *current = Some(text.into_owned()),
                    }
                }
            }
            Ok(Event::End(_)) => {
                let frame = stack.pop().ok_or_else(|| "unbalanced xml".to_string())?;
                if stack.is_empty() {
                    return Err("closed the document root twice".into());
                }
                add_child(&mut stack.last_mut().unwrap().el, frame.name, frame.el);
            }
            Ok(Event::Eof) => break,
            Err(err) => return Err(err.to_string()),
            _ => {}
        }
        buf.clear();
    }
    let root = stack.pop().ok_or_else(|| "empty xml stack".to_string())?;
    let mut children = root.el.children.into_iter();
    let Some((name, child)) = children.next() else {
        return Err("xml document has no root".into());
    };
    if children.next().is_some() {
        return Err("xml document has more than one root".into());
    }
    let Child::One(el) = child else {
        return Err("xml root was repeated".into());
    };
    Ok((name, el))
}

pub fn strip_control_chars(bytes: &[u8]) -> Vec<u8> {
    bytes
        .iter()
        .copied()
        .filter(|b| !matches!(b, 0x00..=0x08 | 0x0b | 0x0c | 0x0e..=0x1f))
        .collect()
}
