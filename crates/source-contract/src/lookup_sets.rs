//! Declared, bounded indexed sets for configured membership expressions, and
//! pair sets that give a key's value (`member_value`).
use std::collections::BTreeSet;

use serde_yaml::Value;
use crate::{expression_children, read_expressions, setting, Lookups, Rejected, Val};

/// Ceilings a contract may declare (ticket 91, as ticket 83: no cap below the
/// machine). A set declares its own measured bounds under these.
pub const MAX_VALUES: u64 = 100_000_000;
pub const MAX_SET_BYTES: u64 = 16 * 1024 * 1024 * 1024;
pub const MAX_VALUE_BYTES: u64 = 16_384;
/// Every supplied set together.
pub const MAX_AGGREGATE_BYTES: usize = 16 * 1024 * 1024 * 1024;
const MAX_SETS: usize = 16;

/// One supplied set: exact texts for `member`, or key and value pairs for
/// `member_value`, as its declaration says.
#[derive(Clone, Debug, PartialEq)]
pub enum LookupSet {
    Members(BTreeSet<String>),
    Pairs(BTreeSet<(String, String)>),
}

impl Default for LookupSet {
    fn default() -> Self { Self::Members(BTreeSet::new()) }
}

impl From<BTreeSet<String>> for LookupSet {
    fn from(values: BTreeSet<String>) -> Self { Self::Members(values) }
}

impl From<BTreeSet<(String, String)>> for LookupSet {
    fn from(pairs: BTreeSet<(String, String)>) -> Self { Self::Pairs(pairs) }
}

impl LookupSet {
    pub fn len(&self) -> usize {
        match self { Self::Members(values) => values.len(), Self::Pairs(pairs) => pairs.len() }
    }

    pub fn is_empty(&self) -> bool { self.len() == 0 }

    pub(crate) fn contains(&self, value: &str) -> Result<bool, Rejected> {
        match self {
            Self::Members(values) => Ok(values.contains(value)),
            Self::Pairs(_) => Err(Rejected::new("invalid_lookup", "a pair set gives values with member_value; it is not a membership set")),
        }
    }
}

fn valid_name(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128)
}

fn pairs(spec: &Value) -> bool {
    spec.get("pairs").and_then(Value::as_bool) == Some(true)
}

pub(crate) fn validate_call(args: &Value) -> Result<(), String> {
    let map = args.as_mapping().filter(|m| m.len() == 2)
        .ok_or("member requires lookup and key only")?;
    if map.keys().any(|k| !matches!(k.as_str(), Some("lookup" | "key")))
        || !args.get("lookup").is_some_and(valid_name) || args.get("key").is_none() {
        return Err("member requires a bounded lookup name and a key expression".into());
    }
    Ok(())
}

pub(crate) fn validate_value_call(args: &Value) -> Result<(), String> {
    let map = args.as_mapping().filter(|m| m.len() == 3)
        .ok_or("member_value requires lookup, key and on_many")?;
    if map.keys().any(|k| !matches!(k.as_str(), Some("lookup" | "key" | "on_many")))
        || !args.get("lookup").is_some_and(valid_name) || args.get("key").is_none()
        || !matches!(setting(args, "on_many"), Some("null" | "error")) {
        return Err("member_value requires a bounded lookup name, a key expression and on_many: \"null\" (quoted, so YAML keeps it text) or error".into());
    }
    Ok(())
}

pub(crate) fn validate(read: &Value) -> Result<(), String> {
    if let Some(specs) = read.get("lookup_sets") {
        let specs = specs.as_mapping().filter(|m| m.len() <= MAX_SETS)
            .ok_or("lookup_sets declares at most sixteen sets")?;
        for (name, spec) in specs {
            if !valid_name(name) { return Err("lookup set names are bounded nonempty text".into()); }
            let map = spec.as_mapping().filter(|m| m.len() == 3 + usize::from(m.contains_key("pairs")))
                .ok_or("lookup set requires max_values, max_bytes and max_value_bytes, and optionally pairs: true")?;
            if map.keys().any(|k| !matches!(k.as_str(), Some("max_values" | "max_bytes" | "max_value_bytes" | "pairs"))) {
                return Err("lookup set has an unknown bound".into());
            }
            if spec.get("pairs").is_some_and(|p| p.as_bool() != Some(true)) {
                return Err("lookup set pairs is true when declared".into());
            }
            for (bound, maximum) in [("max_values", MAX_VALUES), ("max_bytes", MAX_SET_BYTES), ("max_value_bytes", MAX_VALUE_BYTES)] {
                if !spec.get(bound).and_then(Value::as_u64).is_some_and(|n| n > 0 && n <= maximum) {
                    return Err(format!("lookup set {bound} must be positive and at most {maximum}"));
                }
            }
        }
    }
    fn visit(expr: &Value, read: &Value) -> Result<(), String> {
        for (call, wants_pairs) in [("member", false), ("member_value", true)] {
            let Some(args) = expr.get(call) else { continue };
            if wants_pairs { validate_value_call(args)?; } else { validate_call(args)?; }
            let spec = read.get("lookup_sets").and_then(|sets| sets.get(setting(args, "lookup").unwrap()))
                .ok_or(format!("{call} names an undeclared lookup set"))?;
            if pairs(spec) != wants_pairs {
                return Err(format!("{call} needs a {} set", if wants_pairs { "pair" } else { "membership" }));
            }
        }
        for child in expression_children(expr) { visit(child, read)?; }
        Ok(())
    }
    for expr in read_expressions(read) { visit(expr, read)?; }
    Ok(())
}

pub(crate) fn check(read: &Value, sets: &Lookups) -> Result<(), Rejected> {
    let Some(specs) = read.get("lookup_sets").and_then(Value::as_mapping) else { return Ok(()) };
    let invalid = || Rejected::new("invalid_lookup", "runtime sets must exactly match declared lookup_sets");
    if sets.len() != specs.len() { return Err(invalid()); }
    let mut total = 0usize;
    for (name, spec) in specs {
        let set = sets.get(name.as_str().unwrap()).ok_or_else(invalid)?;
        let texts: Vec<&str> = match (set, pairs(spec)) {
            (LookupSet::Members(values), false) => values.iter().map(String::as_str).collect(),
            (LookupSet::Pairs(values), true) => values.iter().flat_map(|(k, v)| [k.as_str(), v.as_str()]).collect(),
            _ => return Err(invalid()),
        };
        if set.len() as u64 > spec["max_values"].as_u64().unwrap() {
            return Err(Rejected::new("limit_exceeded", "lookup set exceeds max_values"));
        }
        let mut bytes = 0usize;
        for value in texts {
            if value.len() as u64 > spec["max_value_bytes"].as_u64().unwrap() {
                return Err(Rejected::new("limit_exceeded", "a lookup key or value exceeds max_value_bytes"));
            }
            bytes = bytes.checked_add(value.len()).ok_or_else(|| Rejected::new("limit_exceeded", "lookup byte count overflow"))?;
            if bytes as u64 > spec["max_bytes"].as_u64().unwrap() {
                return Err(Rejected::new("limit_exceeded", "lookup set exceeds max_bytes"));
            }
        }
        total = total.checked_add(bytes).ok_or_else(|| Rejected::new("limit_exceeded", "lookup byte count overflow"))?;
        if total > MAX_AGGREGATE_BYTES { return Err(Rejected::new("limit_exceeded", "lookup sets exceed aggregate byte bound")); }
    }
    Ok(())
}

pub(crate) fn member(sets: &Lookups, name: &str, key: &Val) -> Result<Val, Rejected> {
    let set = sets.get(name).ok_or_else(|| Rejected::new("invalid_lookup", "lookup set is missing"))?;
    match key {
        Val::Null => Ok(Val::Bool(false)),
        Val::Str(key) => Ok(Val::Bool(set.contains(key)?)),
        _ => Err(Rejected::new("lookup_key", "membership key must be text or null; declare conversion explicitly")),
    }
}

/// The key's one value; null for a null or absent key. A key with several
/// distinct values gives null, or refuses with `on_many: error`.
pub(crate) fn member_value(sets: &Lookups, name: &str, key: &Val, on_many: &str) -> Result<Val, Rejected> {
    let set = sets.get(name).ok_or_else(|| Rejected::new("invalid_lookup", "lookup set is missing"))?;
    let LookupSet::Pairs(pairs) = set else {
        return Err(Rejected::new("invalid_lookup", "member_value needs a pair set"));
    };
    let key = match key {
        Val::Null => return Ok(Val::Null),
        Val::Str(key) => key,
        _ => return Err(Rejected::new("lookup_key", "a pair set key must be text or null; declare conversion explicitly")),
    };
    let mut found = pairs.range((key.clone(), String::new())..).take_while(|(k, _)| k == key).map(|(_, v)| v);
    match (found.next(), found.next()) {
        (None, _) => Ok(Val::Null),
        (Some(value), None) => Ok(Val::Str(value.clone())),
        (Some(_), Some(_)) if on_many == "error" => Err(Rejected::new("lookup_many", "the key has several values in its pair set")),
        _ => Ok(Val::Null),
    }
}

/// Python ingestion uses raw counts before deduplication or allocation:
/// (max_values, max_bytes, max_value_bytes, pairs).
#[cfg(feature = "python")]
pub(crate) fn input_bounds(read: &Value, name: &str) -> Result<Option<(usize, usize, usize, bool)>, Rejected> {
    let Some(specs) = read.get("lookup_sets") else { return Ok(None) };
    let spec = specs.get(name).ok_or_else(|| Rejected::new("invalid_lookup", "runtime lookup set is undeclared"))?;
    Ok(Some((spec["max_values"].as_u64().unwrap() as usize,
             spec["max_bytes"].as_u64().unwrap() as usize,
             spec["max_value_bytes"].as_u64().unwrap() as usize,
             pairs(spec))))
}
