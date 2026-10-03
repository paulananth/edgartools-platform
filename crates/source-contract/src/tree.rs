//! The one tree every reader builds, so paths and checks read XML, JSON, JSON
//! Lines and CSV the same way: `a.b` walks children, `$` is the text and `@x`
//! an attribute.

use std::collections::BTreeMap;

#[derive(Clone, Debug, Default)]
pub struct El {
    pub text: Option<String>,
    pub attrs: BTreeMap<String, String>,
    pub children: BTreeMap<String, Child>,
    /// A JSON scalar or a CSV cell: a value, not an element holding one.
    pub scalar: bool,
    /// A JSON array at this node, distinct from an object with an `item` key.
    pub array: bool,
}

#[derive(Clone, Debug)]
pub enum Child {
    One(El),
    Many(Vec<El>),
}

/// A record as the Python readers shape it: text under `$`, attributes under
/// `@x`, a repeated child as a list. Kept with a record set aside.
#[derive(Clone, Debug, PartialEq)]
pub enum Raw {
    Null,
    Text(String),
    List(Vec<Raw>),
    Map(BTreeMap<String, Raw>),
}

impl El {
    pub fn scalar(text: Option<String>) -> Self {
        Self { text, scalar: true, ..Self::default() }
    }

    pub fn add_child(&mut self, name: String, child: El) {
        let next = match self.children.remove(&name) {
            None => Child::One(child),
            Some(Child::One(prev)) => Child::Many(vec![prev, child]),
            Some(Child::Many(mut rows)) => {
                rows.push(child);
                Child::Many(rows)
            }
        };
        self.children.insert(name, next);
    }

    pub fn push_text(&mut self, text: &str) {
        if text.is_empty() {
            return;
        }
        match &mut self.text {
            Some(existing) => existing.push_str(text),
            None => self.text = Some(text.to_string()),
        }
    }

    pub fn take_only_child(&mut self, name: &str) -> Option<El> {
        match self.children.remove(name)? {
            Child::One(el) => Some(el),
            Child::Many(_) => None,
        }
    }

    pub fn raw(&self) -> Raw {
        if self.scalar {
            return self.text.clone().map_or(Raw::Null, Raw::Text);
        }
        let mut map = BTreeMap::new();
        if let Some(text) = &self.text {
            map.insert("$".to_string(), Raw::Text(text.clone()));
        }
        for (key, value) in &self.attrs {
            map.insert(key.clone(), Raw::Text(value.clone()));
        }
        for (key, child) in &self.children {
            let value = match child {
                Child::One(el) => el.raw(),
                Child::Many(rows) => Raw::List(rows.iter().map(El::raw).collect()),
            };
            map.insert(key.clone(), value);
        }
        Raw::Map(map)
    }
}
