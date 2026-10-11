//! Generic complete-set reduction. Transport, receipts and publication stay
//! with Python; only successful caller exhaustion may expose the result.
use std::collections::{BinaryHeap, HashMap};

use indexmap::IndexMap;
use serde::Deserialize;
use serde_json::{Map, Value};

type Key = Vec<String>;
type Members = HashMap<String, Option<String>>;

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Group {
    pub source: String,
    pub table: Value,
    pub keys: Vec<String>,
    pub mode: String,
    pub count: String,
    pub sample: Option<String>,
    pub sample_limit: usize,
    pub member: Option<String>,
    pub last: Option<String>,
    pub last_null: Option<String>,
    pub exclude: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    max_rows: usize,
    max_input_bytes: usize,
    max_state_bytes: usize,
    max_keys: usize,
    max_members: usize,
    max_output_rows: usize,
    max_output_bytes: usize,
    groups: IndexMap<String, Group>,
}

pub struct Row {
    pub key: Key,
    pub member: Option<String>,
    pub last: Option<String>,
}

enum Entry {
    Count(u64),
    Members(Members),
}

pub struct Reduction {
    plan: Plan,
    state: IndexMap<String, HashMap<Key, Entry>>,
    rows: HashMap<String, usize>,
    keys: usize,
    members: usize,
    bytes: usize,
    failed: bool,
    finished: bool,
}

fn name(text: &str) -> bool {
    !text.is_empty()
        && text.len() <= 64
        && text
            .bytes()
            .enumerate()
            .all(|(i, b)| b == b'_' || b.is_ascii_alphabetic() || (i > 0 && b.is_ascii_digit()))
}

// Compact ensure_ascii=False JSON byte size, identical to the Python state
// accounting. Keys and values are text only, so no numeric spelling ambiguity.
fn text_bytes(text: &str) -> usize {
    2 + text
        .bytes()
        .map(|b| match b {
            b'"' | b'\\' | 8 | 9 | 10 | 12 | 13 => 2,
            0..=31 => 6,
            _ => 1,
        })
        .sum::<usize>()
}

fn key_bytes(key: &[String]) -> usize {
    2 + key.len().saturating_sub(1) + key.iter().map(|s| text_bytes(s)).sum::<usize>()
}

fn last_bytes(last: &Option<String>) -> usize {
    last.as_ref().map_or(4, |s| text_bytes(s))
}

impl Reduction {
    pub fn new(body: &str) -> Result<Self, String> {
        let raw: Value = serde_json::from_str(body).map_err(|_| "Invalid reduction plan")?;
        let groups = raw
            .get("groups")
            .and_then(Value::as_object)
            .ok_or("Invalid reduction groups")?;
        for spec in groups.values() {
            let spec = spec.as_object().ok_or("Invalid reduction group")?;
            if [
                "source",
                "table",
                "keys",
                "mode",
                "count",
                "sample",
                "sample_limit",
            ]
            .iter()
            .any(|key| !spec.contains_key(*key))
                || (spec.get("mode").and_then(Value::as_str) == Some("count") && spec.len() != 7)
                || ["member", "last", "last_null", "exclude"]
                    .iter()
                    .any(|key| spec.get(*key).is_some_and(|value| !value.is_string()))
            {
                return Err("Invalid reduction group fields".into());
            }
        }
        let plan: Plan = serde_json::from_value(raw).map_err(|_| "Invalid reduction plan")?;
        for (value, maximum) in [
            (plan.max_rows, 40_000_000),
            (plan.max_input_bytes, 16 * 1024usize.pow(3)),
            (plan.max_state_bytes, 256 * 1024usize.pow(2)),
            (plan.max_keys, 10_000_000),
            (plan.max_members, 10_000_000),
            (plan.max_output_rows, 100_000),
            (plan.max_output_bytes, 32 * 1024usize.pow(2)),
        ] {
            if value == 0 || value > maximum {
                return Err("Invalid reduction bound".into());
            }
        }
        if plan.groups.is_empty() || plan.groups.len() > 32 {
            return Err("Reduction requires 1..32 named groups".into());
        }
        for (group_name, g) in &plan.groups {
            let tables: Vec<&str> = match &g.table {
                Value::String(s) => vec![s],
                Value::Array(a) => a
                    .iter()
                    .map(|v| v.as_str().ok_or("Invalid reduction table"))
                    .collect::<Result<_, _>>()?,
                _ => return Err("Invalid reduction table".into()),
            };
            if !name(group_name)
                || !name(&g.source)
                || tables.is_empty()
                || tables.len() > 8
                || tables.iter().any(|s| !name(s))
                || tables
                    .iter()
                    .collect::<std::collections::HashSet<_>>()
                    .len()
                    != tables.len()
                || g.keys.is_empty()
                || g.keys.len() > 8
                || g.keys.iter().any(|s| !name(s))
                || g.keys
                    .iter()
                    .collect::<std::collections::HashSet<_>>()
                    .len()
                    != g.keys.len()
                || !name(&g.count)
                || g.keys.contains(&g.count)
                || g.sample_limit > 1000
            {
                return Err("Invalid reduction group".into());
            }
            match g.mode.as_str() {
                "count"
                    if g.sample.is_none()
                        && g.sample_limit == 0
                        && g.member.is_none()
                        && g.last.is_none()
                        && g.last_null.is_none()
                        && g.exclude.is_none() => {}
                "members"
                    if g.member.as_ref().is_some_and(|s| name(s))
                        && g.sample
                            .as_ref()
                            .is_some_and(|s| name(s) && !g.keys.contains(s) && s != &g.count)
                        && g.last.as_ref().is_none_or(|s| {
                            name(s) && Some(s) != g.member.as_ref() && tables.len() == 1
                        })
                        && (g.last_null.is_none() || g.last.is_some()) => {}
                _ => return Err("Invalid reduction mode or columns".into()),
            }
            if let Some(exclude) = &g.exclude {
                let other = plan
                    .groups
                    .get(exclude)
                    .ok_or("Invalid reduction exclusion")?;
                if exclude == group_name
                    || other.mode != "members"
                    || other.keys != g.keys
                    || other.exclude.is_some()
                {
                    return Err("Invalid reduction exclusion".into());
                }
            }
        }
        let state = plan
            .groups
            .keys()
            .map(|name| (name.clone(), HashMap::new()))
            .collect();
        Ok(Self {
            plan,
            state,
            rows: HashMap::new(),
            keys: 0,
            members: 0,
            bytes: 0,
            failed: false,
            finished: false,
        })
    }

    pub fn spec(&self, name: &str) -> Result<&Group, String> {
        self.ready()?;
        self.plan
            .groups
            .get(name)
            .ok_or_else(|| "Unknown reduction group".into())
    }

    fn ready(&self) -> Result<(), String> {
        if self.failed {
            return Err("Reduction failed; discard its provisional state".into());
        }
        if self.finished {
            return Err("Reduction already finished".into());
        }
        Ok(())
    }

    pub fn invalidate(&mut self) {
        self.failed = true;
    }

    pub fn push(&mut self, name: &str, rows: Vec<Row>) -> Result<(), String> {
        let result = self.push_inner(name, rows);
        if result.is_err() {
            self.invalidate();
        }
        result
    }

    fn push_inner(&mut self, name: &str, rows: Vec<Row>) -> Result<(), String> {
        self.ready()?;
        let spec = self
            .plan
            .groups
            .get(name)
            .ok_or("Unknown reduction group")?;
        let state = self.state.get_mut(name).ok_or("Unknown reduction group")?;
        let selected_rows = self.rows.entry(name.to_owned()).or_default();
        for row in rows {
            if *selected_rows >= self.plan.max_rows {
                return Err("Reduction exceeds selected input row budget for group".into());
            }
            *selected_rows += 1;
            if row.key.len() != spec.keys.len()
                || (spec.mode == "members") != row.member.is_some()
                || (spec.last.is_some() && row.last.is_none())
                || (spec.last.is_none() && row.last.is_some())
            {
                return Err("Invalid reduction row".into());
            }
            let prior = state.get(&row.key);
            let new_key = prior.is_none();
            let (new_member, add, remove) = match prior {
                Some(Entry::Count(n)) => (false, (n + 1).to_string().len(), n.to_string().len()),
                None if spec.mode == "count" => (false, 1, 0),
                _ => {
                    let member = row.member.as_ref().ok_or("Invalid reduction member")?;
                    let old = match prior {
                        Some(Entry::Members(m)) => m.get(member),
                        _ => None,
                    };
                    (
                        old.is_none(),
                        last_bytes(&row.last) + if old.is_none() { text_bytes(member) } else { 0 },
                        old.map_or(0, last_bytes),
                    )
                }
            };
            let bytes = self.bytes + add + if new_key { key_bytes(&row.key) } else { 0 } - remove;
            if self.keys + usize::from(new_key) > self.plan.max_keys
                || self.members + usize::from(new_member) > self.plan.max_members
                || bytes > self.plan.max_state_bytes
            {
                return Err("Reduction exceeds declared state budget".into());
            }
            self.keys += usize::from(new_key);
            self.members += usize::from(new_member);
            self.bytes = bytes;
            let entry = state.entry(row.key).or_insert_with(|| {
                if spec.mode == "count" {
                    Entry::Count(0)
                } else {
                    Entry::Members(HashMap::new())
                }
            });
            match entry {
                Entry::Count(n) => *n = n.checked_add(1).ok_or("Reduction count overflow")?,
                Entry::Members(m) => {
                    m.insert(row.member.unwrap(), row.last);
                }
            }
        }
        Ok(())
    }

    pub fn finish(&mut self) -> Result<Value, String> {
        self.ready()?;
        // Failed finish must never make partially accumulated state reusable.
        self.finished = true;
        if self.keys > self.plan.max_output_rows {
            self.invalidate();
            return Err("Reduction exceeds output row budget".into());
        }
        let mut result = Map::new();
        for (name, spec) in &self.plan.groups {
            let mut keys: Vec<_> = self.state[name].iter().collect();
            keys.sort_unstable_by(|(a, _), (b, _)| a.cmp(b));
            let mut output = Vec::with_capacity(keys.len());
            for (key, entry) in keys {
                let mut row: Map<String, Value> = spec
                    .keys
                    .iter()
                    .zip(key)
                    .map(|(column, value)| (column.clone(), Value::String(value.clone())))
                    .collect();
                match entry {
                    Entry::Count(n) => {
                        row.insert(spec.count.clone(), Value::from(*n));
                    }
                    Entry::Members(members) => {
                        let excluded = spec
                            .exclude
                            .as_ref()
                            .and_then(|other| self.state[other].get(key));
                        let mut count = 0u64;
                        let mut sample: BinaryHeap<&String> = BinaryHeap::new();
                        for member in members.keys() {
                            if matches!(excluded, Some(Entry::Members(m)) if m.contains_key(member))
                            {
                                continue;
                            }
                            count += 1;
                            if spec.sample_limit != 0 {
                                sample.push(member);
                                if sample.len() > spec.sample_limit {
                                    sample.pop();
                                }
                            }
                        }
                        let sample: Vec<_> = sample
                            .into_sorted_vec()
                            .into_iter()
                            .map(|member| {
                                let mut item = Map::new();
                                item.insert(
                                    spec.member.clone().unwrap(),
                                    Value::String(member.clone()),
                                );
                                if let Some(column) = &spec.last {
                                    item.insert(
                                        column.clone(),
                                        Value::String(members[member].clone().unwrap()),
                                    );
                                }
                                Value::Object(item)
                            })
                            .collect();
                        row.insert(spec.count.clone(), Value::from(count));
                        row.insert(spec.sample.clone().unwrap(), Value::Array(sample));
                    }
                }
                output.push(Value::Object(row));
            }
            result.insert(name.clone(), Value::Array(output));
        }
        Ok(Value::Object(result))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn plan(groups: Value) -> Value {
        serde_json::json!({"max_rows": 100, "max_input_bytes": 1024,
            "max_state_bytes": 1024, "max_keys": 100, "max_members": 100,
            "max_output_rows": 100, "max_output_bytes": 1024, "groups": groups})
    }

    fn member(exclude: Option<&str>) -> Value {
        let mut group = serde_json::json!({"source": "main", "table": "rows", "keys": ["key"],
            "mode": "members", "member": "holder", "last": "time", "count": "count",
            "sample": "sample", "sample_limit": 1});
        if let Some(other) = exclude {
            group["exclude"] = Value::String(other.into());
        }
        group
    }

    fn row(member: &str, last: &str) -> Row {
        Row {
            key: vec!["a".into()],
            member: Some(member.into()),
            last: Some(last.into()),
        }
    }

    #[test]
    fn complete_exclusion_and_last_occurrence_are_deterministic() {
        let body =
            plan(serde_json::json!({"all": member(Some("excluded")), "excluded": member(None)}));
        let mut engine = Reduction::new(&body.to_string()).unwrap();
        engine
            .push(
                "all",
                vec![row("Z", "9999"), row("A", "old"), row("B", "b")],
            )
            .unwrap();
        engine
            .push("all", vec![row("Z", ""), row("A", "new")])
            .unwrap();
        engine.push("excluded", vec![row("A", "x")]).unwrap();
        let output = engine.finish().unwrap();
        assert_eq!(
            output["all"],
            serde_json::json!([
            {"key": "a", "count": 2, "sample": [{"holder": "B", "time": "b"}]}])
        );
        assert!(engine.finish().is_err());
    }

    #[test]
    fn bound_failure_poisoning_and_aggregate_output_keys() {
        let mut body = plan(serde_json::json!({"a": member(None), "b": member(None)}));
        body["max_output_rows"] = Value::from(1);
        let mut engine = Reduction::new(&body.to_string()).unwrap();
        engine.push("a", vec![row("A", "")]).unwrap();
        engine.push("b", vec![row("B", "")]).unwrap();
        assert_eq!(
            engine.finish().unwrap_err(),
            "Reduction exceeds output row budget"
        );
        assert!(engine.push("a", vec![]).is_err());
        body["max_state_bytes"] = Value::from(1);
        let mut refused = Reduction::new(&body.to_string()).unwrap();
        assert!(refused.push("a", vec![row("A", "")]).is_err());
        assert!(refused.finish().is_err());
    }

    #[test]
    fn text_and_key_bytes_match_compact_unicode_json() {
        for text in ["", "a", "é𐀀", "\0\u{1}\x08\t\n\x0c\r\"\\", "\u{2028}"] {
            assert_eq!(text_bytes(text), serde_json::to_vec(text).unwrap().len());
            let key = vec![text.to_owned(), "z".to_owned()];
            assert_eq!(key_bytes(&key), serde_json::to_vec(&key).unwrap().len());
        }
    }

    #[test]
    fn selected_row_bound_is_per_group_and_failure_is_terminal() {
        let mut body = plan(serde_json::json!({"a": member(None), "b": member(None)}));
        body["max_rows"] = Value::from(1);
        let mut engine = Reduction::new(&body.to_string()).unwrap();
        engine.push("a", vec![row("A", "")]).unwrap();
        engine.push("b", vec![row("B", "")]).unwrap();
        assert_eq!(
            engine.push("a", vec![row("A", "")]).unwrap_err(),
            "Reduction exceeds selected input row budget for group"
        );
        assert!(engine.finish().is_err());
    }
}
