//! Bounded text projection/joining, with explicit shape and whitespace policies.
use serde_yaml::Value;
use crate::{check_path, lookup_shape, lookup_literal, setting, Found, Rejected, Val};
use crate::tree::{Child, El, ScalarKind};

const MAX_BYTES: usize = 1_048_576;

pub(crate) fn validate(args: &Value) -> Result<(), String> {
    let map = args.as_mapping().ok_or("join arguments must be a mapping")?;
    if map.keys().any(|k| !matches!(k.as_str(),Some("path"|"item_path"|"separator"|"trim"|"skip_empty"|"null_if_empty"|"max_items"|"from"|"item_type"|"path_mode"))) {
        return Err("join has an unknown argument".into());
    }
    if args.get("path_mode").is_some_and(|v| !matches!(v.as_str(),Some("tree"|"literal"))) { return Err("join path_mode is tree or literal".into()); }
    for key in ["path", "item_path"] {
        if setting(args,"path_mode") == Some("literal") && setting(args,key).is_some_and(|p| p.contains(['[',']'])) { return Err("literal paths have no filters".into()); }
        check_path(setting(args,key).ok_or("join requires path and item_path")?)?; }
    if !setting(args,"separator").is_some_and(|s| s.len() <= 128) { return Err("join separator is text of at most 128 bytes".into()); }
    if !args.get("max_items").and_then(Value::as_u64).is_some_and(|n| (1..=100_000).contains(&n)) { return Err("join max_items is 1..100000".into()); }
    if args.get("item_type").is_some_and(|v| !matches!(v.as_str(),Some("object"|"text"))) { return Err("join item_type is object or text".into()); }
    for key in ["trim", "skip_empty", "null_if_empty"] {
        if args.get(key).is_some_and(|v| v.as_bool().is_none()) { return Err("join flags are booleans".into()); }
    }
    if args.get("from").is_some_and(|v| !matches!(v.as_str(),Some("document"|"item"))) { return Err("join from is document or item".into()); }
    Ok(())
}

fn push(output: &mut String, text: &str) -> Result<(), Rejected> {
    if text.len() > MAX_BYTES.saturating_sub(output.len()) { return Err(Rejected::new("join_limit", "Joined text exceeds 1048576 bytes")); }
    output.push_str(text);
    Ok(())
}

pub(crate) fn read(start: &El, args: &Value) -> Result<Val, Rejected> {
    let lookup = if setting(args,"path_mode") == Some("literal") { lookup_literal } else { lookup_shape };
    let items = match lookup(start,setting(args,"path").unwrap())? {
        Found::Missing => return Ok(Val::Null),
        Found::El(el) if el.scalar && el.text.is_none() => return Ok(Val::Null),
        Found::List(items) => items,
        Found::El(el) if el.array => match el.children.get("item") {
            Some(Child::Many(items)) => items.iter().collect(),
            _ => return Err(Rejected::new("join_shape", "Join requires an array")),
        },
        _ => return Err(Rejected::new("join_shape", "Join requires an array")),
    };
    if items.len() as u64 > args["max_items"].as_u64().unwrap() { return Err(Rejected::new("join_limit", "Join exceeds max_items")); }
    let mut output = String::new();
    let mut emitted = false;
    for item in items {
        if (setting(args,"item_type") == Some("object") && (item.scalar || item.array))
            || (setting(args,"item_type") == Some("text") && (!item.scalar || item.kind != ScalarKind::Text || item.text.is_none())) {
            return Err(Rejected::new("join_shape", "Joined item differs from declared item_type"));
        }
        let text = match lookup(item,setting(args,"item_path").unwrap())? {
            Found::Text(text,ScalarKind::Text,_) => text,
            Found::El(el) if el.scalar && el.kind == ScalarKind::Text => el.text.clone().ok_or_else(|| Rejected::new("join_shape", "Joined item must be text"))?,
            _ => return Err(Rejected::new("join_shape", "Joined item must be text")),
        };
        let text = if args["trim"].as_bool() == Some(true) { text.trim_matches(crate::text_transform::whitespace) } else { &text };
        if text.is_empty() && args["skip_empty"].as_bool() == Some(true) { continue; }
        if emitted { push(&mut output,setting(args,"separator").unwrap())?; }
        push(&mut output,text)?;
        emitted = true;
    }
    if output.is_empty() && args["null_if_empty"].as_bool() == Some(true) { Ok(Val::Null) }
    else { Ok(Val::Str(output)) }
}
