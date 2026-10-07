//! Bounded XML envelopes with configured names and namespace-aware records.
//! Callbacks prepare candidates. Only a successful EOF receipt permits publication.
use std::cell::Cell;
use std::io::{self, BufReader, Read};

use quick_xml::{events::Event, Reader};
use serde_json::{Map, Value};

use crate::{json_sequence::{encoded_len, RecordEncoding, Stats}, Rejected};

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Envelope {
    pub namespace: String,
    pub root: String,
    pub header: String,
    pub container: String,
    pub record: String,
    /// Some feeds put the XML record under an additional JSON wrapper.
    pub record_wrapper: Option<String>,
}

#[derive(Clone, Copy)]
pub struct Limits {
    pub max_bytes: usize,
    pub max_record: usize,
    pub max_header: usize,
    pub max_records: usize,
    pub max_depth: usize,
}

fn node_bound(stack: &[Frame], envelope: &Envelope, limits: Limits) -> usize {
    if stack.len() >= 3 && stack[1].name == envelope.container { limits.max_record }
    else { limits.max_header }
}

fn reject(detail: impl ToString) -> Rejected { Rejected::new("xml_stream", detail) }

struct Budget<'a, R> {
    source: R,
    total: &'a Cell<usize>,
    since_record: &'a Cell<usize>,
    limits: Limits,
}

impl<R: Read> Read for Budget<'_, R> {
    fn read(&mut self, target: &mut [u8]) -> io::Result<usize> {
        let size = target.len().min(65536);
        let n = self.source.read(&mut target[..size])?;
        let total = self.total.get().checked_add(n);
        let since = self.since_record.get().checked_add(n);
        if total.is_none_or(|n| n > self.limits.max_bytes)
            || since.is_none_or(|n| n > self.limits.max_record.saturating_add(65536)) {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "XML byte budget exceeded"));
        }
        self.total.set(total.unwrap());
        self.since_record.set(since.unwrap());
        Ok(n)
    }
}

fn resolved(raw: &[u8], attribute: bool, bindings: &[(String, String)], stack: &[Frame]) -> Result<(Option<String>, String), Rejected> {
    qname(raw)?;
    let raw = std::str::from_utf8(raw).map_err(reject)?;
    let (prefix, local) = raw.split_once(':').unwrap_or(("", raw));
    if prefix == "xml" { return Ok((Some("http://www.w3.org/XML/1998/namespace".into()), local.into())); }
    if prefix.is_empty() && attribute { return Ok((None, local.into())); }
    let uri = bindings.iter().rev().find(|(p, _)| p == prefix).map(|(_, uri)| uri)
        .or_else(|| stack.iter().rev().find_map(|frame| frame.bindings.iter().rev().find(|(p, _)| p == prefix).map(|(_, uri)| uri)));
    match uri {
        Some(uri) if !uri.is_empty() => Ok((Some(uri.clone()), local.into())),
        _ if prefix.is_empty() => Ok((None, local.into())),
        _ => Err(reject("undeclared XML namespace prefix")),
    }
}

fn xml_chars(text: &str) -> Result<(), Rejected> {
    if text.chars().any(|c| !matches!(c, '\u{9}' | '\u{a}' | '\u{d}' | '\u{20}'..='\u{d7ff}' | '\u{e000}'..='\u{fffd}' | '\u{10000}'..='\u{10ffff}')) {
        return Err(reject("invalid XML 1.0 character"));
    }
    Ok(())
}

// XML 1.0 Fifth Edition NameStartChar / NameChar. A QName permits one
// separating colon; each side is an NCName, including namespace declarations.
fn name_start(c: char) -> bool {
    matches!(c, 'A'..='Z' | '_' | 'a'..='z' | '\u{c0}'..='\u{d6}' | '\u{d8}'..='\u{f6}' |
        '\u{f8}'..='\u{2ff}' | '\u{370}'..='\u{37d}' | '\u{37f}'..='\u{1fff}' |
        '\u{200c}'..='\u{200d}' | '\u{2070}'..='\u{218f}' | '\u{2c00}'..='\u{2fef}' |
        '\u{3001}'..='\u{d7ff}' | '\u{f900}'..='\u{fdcf}' | '\u{fdf0}'..='\u{fffd}' |
        '\u{10000}'..='\u{effff}')
}

fn qname(raw: &[u8]) -> Result<(), Rejected> {
    let name = std::str::from_utf8(raw).map_err(reject)?;
    let parts: Vec<_> = name.split(':').collect();
    if parts.len() > 2 || parts.iter().any(|part| {
        let mut chars = part.chars();
        !chars.next().is_some_and(name_start) || chars.any(|c| !name_start(c) &&
            !matches!(c, '-' | '.' | '0'..='9' | '\u{b7}' | '\u{300}'..='\u{36f}' | '\u{203f}'..='\u{2040}'))
    }) { return Err(reject("invalid XML qualified name")); }
    Ok(())
}

fn normalized(raw: &[u8], attribute: bool) -> Result<String, Rejected> {
    if attribute && raw.contains(&b'<') { return Err(reject("literal '<' in XML attribute")); }
    let text = std::str::from_utf8(raw).map_err(reject)?.replace("\r\n", "\n").replace('\r', "\n");
    let text = if attribute { text.replace(['\n', '\t'], " ") } else { text };
    let text = quick_xml::escape::unescape(&text).map_err(reject)?.into_owned();
    xml_chars(&text)?;
    Ok(text)
}

struct Frame {
    bindings: Vec<(String, String)>,
    namespace: Option<String>,
    name: String,
    values: Map<String, Value>,
    text: String,
    child_seen: bool,
    size: usize,
}

impl Frame {
    fn leading_text(&mut self, text: &str, maximum: usize) -> Result<(), Rejected> {
        if self.child_seen { return Ok(()); }
        self.text.push_str(text);
        let text = self.text.trim();
        if !text.is_empty() {
            let extra = serde_json::to_string(text).unwrap().len().saturating_add(4)
                .saturating_add(usize::from(!self.values.is_empty()));
            if self.size.saturating_add(extra) > maximum {
                return Err(reject("XML normalized text exceeds encoded byte bound"));
            }
        }
        Ok(())
    }
    fn finish(mut self, maximum: usize) -> Result<Value, Rejected> {
        let text = self.text.trim();
        if !text.is_empty() {
            let value = Value::String(text.into());
            self.child("$".into(), value, maximum)?;
        }
        Ok(Value::Object(self.values))
    }
    fn child(&mut self, name: String, value: Value, maximum: usize) -> Result<(), Rejected> {
        let value_size = encoded_len(&value, RecordEncoding::Python)?;
        let extra = match self.values.get(&name) {
            None => serde_json::to_string(&name).unwrap().len().saturating_add(1)
                .saturating_add(value_size).saturating_add(usize::from(!self.values.is_empty())),
            Some(Value::Array(_)) => value_size.saturating_add(1),
            Some(_) => value_size.saturating_add(3),
        };
        let size = self.size.saturating_add(extra);
        if size > maximum { return Err(reject("XML normalized node exceeds encoded byte bound")); }
        match self.values.get_mut(&name) {
            None => { self.values.insert(name, value); },
            Some(Value::Array(values)) => values.push(value),
            Some(previous) => {
                let first = std::mem::replace(previous, Value::Null);
                *previous = Value::Array(vec![first, value]);
            },
        }
        self.size = size;
        Ok(())
    }
}

/// Header checks run before the first record. The caller supplies configured
/// assertions; this framer contains no source-specific names or metadata rules.
pub fn scan<R, H, F>(source: R, envelope: &Envelope, limits: Limits, mut header: H, mut consume: F) -> Result<Stats, Rejected>
where R: Read, H: FnMut(Value) -> Result<(), Rejected>, F: FnMut(Value, usize) -> Result<(), Rejected> {
    let names = [&envelope.root, &envelope.header, &envelope.container, &envelope.record];
    if envelope.namespace.is_empty() || names.iter().any(|n| n.is_empty() || n.contains([':', '{', '}']))
        || names.iter().enumerate().any(|(i, n)| names[..i].contains(n))
        || envelope.record_wrapper.as_ref().is_some_and(|name| name.is_empty())
        || limits.max_bytes == 0 || limits.max_record == 0 || limits.max_header == 0 || limits.max_depth < 3 {
        return Err(Rejected::new("contract", "invalid XML stream envelope or bounds"));
    }
    let total = Cell::new(0);
    let since_record = Cell::new(0);
    let source = Budget { source, total: &total, since_record: &since_record, limits };
    let mut reader = Reader::from_reader(BufReader::with_capacity(65536, source));
    reader.config_mut().expand_empty_elements = true;
    reader.config_mut().check_comments = true;
    let mut buffer = Vec::new();
    let mut stack: Vec<Frame> = Vec::new();
    let (mut root_seen, mut root_closed, mut header_seen, mut container_seen, mut event_seen) = (false, false, false, false, false);
    let mut records = 0;
    loop {
        let event = reader.read_event_into(&mut buffer).map_err(reject)?;
        match event {
            Event::DocType(_) => return Err(reject("DTD is unsupported")),
            Event::Decl(decl) => {
                if event_seen || root_seen || decl.version().map_err(reject)?.as_ref() != b"1.0" {
                    return Err(reject("invalid XML declaration"));
                }
                let content = std::str::from_utf8(decl.as_ref()).map_err(reject)?;
                let declaration = quick_xml::events::BytesStart::from_content(content, 3);
                let mut keys = Vec::new();
                for attribute in declaration.attributes() {
                    let attribute = attribute.map_err(reject)?;
                    let key = attribute.key.as_ref();
                    match key {
                        b"version" if keys.is_empty() && attribute.value.as_ref() == b"1.0" => {},
                        b"encoding" if keys == [b"version".to_vec()] && attribute.value.eq_ignore_ascii_case(b"utf-8") => {},
                        b"standalone" if !keys.is_empty() && keys.last().map(Vec::as_slice) != Some(b"standalone") && matches!(attribute.value.as_ref(), b"yes" | b"no") => {},
                        _ => return Err(reject("invalid XML declaration attribute or encoding")),
                    }
                    keys.push(key.to_vec());
                }
            },
            Event::Start(start) => {
                qname(start.name().as_ref())?;
                if root_closed || stack.len() >= limits.max_depth { return Err(reject("XML root or depth bound exceeded")); }
                let mut bindings = Vec::new();
                let mut attributes = Vec::new();
                for attribute in start.attributes() {
                    let attribute = attribute.map_err(reject)?;
                    let raw = attribute.key.as_ref();
                    qname(raw)?;
                    let value = normalized(attribute.value.as_ref(), true)?;
                    if raw == b"xmlns" || raw.starts_with(b"xmlns:") {
                        let prefix = raw.strip_prefix(b"xmlns:");
                        let xml = "http://www.w3.org/XML/1998/namespace";
                        let xmlns = "http://www.w3.org/2000/xmlns/";
                        if value == xmlns || prefix == Some(b"xmlns") ||
                            (prefix == Some(b"xml")) != (value == xml) ||
                            (prefix.is_some() && value.is_empty()) || value.chars().any(char::is_whitespace) {
                            return Err(reject("invalid reserved, empty or whitespace XML namespace binding"));
                        }
                        bindings.push((std::str::from_utf8(prefix.unwrap_or(b"")).map_err(reject)?.into(), value));
                    } else { attributes.push((raw.to_vec(), value)); }
                }
                let (namespace, name) = resolved(start.name().as_ref(), false, &bindings, &stack)?;
                let same_namespace = namespace.as_deref() == Some(envelope.namespace.as_str());
                match stack.len() {
                    0 => {
                        if root_seen || !same_namespace || name != envelope.root { return Err(reject("invalid XML root/namespace")); }
                        root_seen = true;
                    },
                    1 => {
                        if !same_namespace { return Err(reject("invalid XML envelope namespace")); }
                        if name == envelope.header && !header_seen && !container_seen { }
                        else if name == envelope.container && header_seen && !container_seen { container_seen = true; }
                        else { return Err(reject("duplicate, unexpected or misplaced XML envelope element")); }
                    },
                    2 if stack[1].name == envelope.container => {
                        if !same_namespace || name != envelope.record { return Err(reject("unexpected XML record")); }
                        if records >= limits.max_records { return Err(reject("XML record count exceeds bound")); }
                    },
                    _ => {},
                }
                let maximum = if stack.len() >= 2 && stack[1].name == envelope.container {
                    limits.max_record
                } else { limits.max_header };
                let mut values = Map::new();
                let mut size = 2usize;
                for (raw, value) in attributes {
                    let (ns, local) = resolved(&raw, true, &bindings, &stack)?;
                    let key = match ns { Some(ns) => format!("@{{{ns}}}{local}"), None => format!("@{local}") };
                    size = size.saturating_add(serde_json::to_string(&key).unwrap().len())
                        .saturating_add(1).saturating_add(serde_json::to_string(&value).unwrap().len())
                        .saturating_add(usize::from(!values.is_empty()));
                    if size > maximum { return Err(reject("XML normalized attributes exceed byte bound")); }
                    if values.insert(key, Value::String(value)).is_some() {
                        return Err(reject("duplicate expanded XML attribute"));
                    }
                }
                if let Some(parent) = stack.last_mut() { parent.child_seen = true; }
                stack.push(Frame { bindings, namespace, name, values, text: String::new(), child_seen: false, size });
            },
            Event::Text(text) => {
                if stack.is_empty() && text.as_ref().contains(&b'&') { return Err(reject("entity reference outside XML root")); }
                if text.as_ref().windows(3).any(|part| part == b"]]>") { return Err(reject("CDATA terminator in XML text")); }
                let text = normalized(text.as_ref(), false)?;
                if stack.len() <= 1 || (stack.len() == 2 && stack[1].name == envelope.container) {
                    if !text.chars().all(|c| matches!(c, ' ' | '\t' | '\r' | '\n')) { return Err(reject("unexpected XML envelope text")); }
                } else {
                    let maximum = node_bound(&stack, envelope, limits);
                    let frame = stack.last_mut().unwrap();
                    // Match an element's leading text; tail text is not a field.
                    frame.leading_text(&text, maximum)?;
                }
            },
            Event::CData(text) => {
                if stack.len() < 2 || (stack.len() == 2 && stack[1].name == envelope.container) { return Err(reject("unexpected XML envelope CDATA")); }
                let text = std::str::from_utf8(text.as_ref()).map_err(reject)?.replace("\r\n", "\n").replace('\r', "\n");
                xml_chars(&text)?;
                let maximum = node_bound(&stack, envelope, limits);
                let frame = stack.last_mut().unwrap();
                frame.leading_text(&text, maximum)?;
            },
            Event::End(_) => {
                let maximum = node_bound(&stack, envelope, limits);
                let frame = stack.pop().ok_or_else(|| reject("unbalanced XML end tag"))?;
                let key = if frame.namespace.as_deref() == Some(envelope.namespace.as_str()) { frame.name.clone() }
                    else { match &frame.namespace { Some(ns) => format!("{{{ns}}}{}", frame.name), None => frame.name.clone() } };
                if stack.is_empty() { root_closed = true; }
                else if stack.len() == 1 && frame.name == envelope.header {
                    let value = frame.finish(limits.max_header)?;
                    if encoded_len(&value, RecordEncoding::Python)? > limits.max_header { return Err(reject("XML header exceeds byte bound")); }
                    header(value)?;
                    header_seen = true;
                    since_record.set(0);
                } else if stack.len() == 2 && stack[1].name == envelope.container {
                    let mut value = frame.finish(limits.max_record)?;
                    if let Some(wrapper) = &envelope.record_wrapper { value = Value::Object(Map::from_iter([(wrapper.clone(), value)])); }
                    if encoded_len(&value, RecordEncoding::Python)? > limits.max_record { return Err(reject("XML record exceeds encoded byte bound")); }
                    consume(value, records)?;
                    records += 1;
                    since_record.set(0);
                } else if stack.len() >= 2 { stack.last_mut().unwrap().child(key, frame.finish(maximum)?, maximum)?; }
            },
            Event::Eof => break,
            Event::Comment(text) => { xml_chars(std::str::from_utf8(text.as_ref()).map_err(reject)?)?; },
            Event::PI(pi) => {
                qname(pi.target())?;
                if pi.target().contains(&b':') { return Err(reject("colon in XML processing instruction target")); }
                if pi.target().eq_ignore_ascii_case(b"xml") { return Err(reject("reserved XML processing instruction target")); }
                xml_chars(std::str::from_utf8(pi.as_ref()).map_err(reject)?)?;
                if stack.len() >= 2 && (stack[1].name == envelope.header || stack.len() >= 3) {
                    return Err(reject("processing instruction inside a captured XML node"));
                }
            },
            _ => {},
        }
        event_seen = true;
        buffer.clear();
    }
    if !root_closed || !stack.is_empty() || !header_seen || !container_seen { return Err(reject("incomplete XML envelope")); }
    Ok(Stats { records, bytes: total.get() })
}
