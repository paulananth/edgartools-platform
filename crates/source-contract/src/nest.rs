//! `nest`: one iteration inside each row of another, so one table holds a row per
//! inner item (a fact under its concept and unit). `keep` copies named fields of
//! the outer row onto each inner row, and refuses one the outer row lacks;
//! nothing else of the outer row is carried.
//! The inner rows of every outer row count together against max_records.
use std::collections::HashSet;

use serde_yaml::Value;

use crate::tree::{Child, El};
use crate::iteration::{self, field_name};
use crate::{Engine, Lookups, Rejected, Row, Steps};

pub(crate) fn validate(args: &Value, format: &str, steps: &Steps, depth: usize) -> Result<(), String> {
    if format != "json" { return Err("each.nest requires JSON".into()); }
    let map = args.as_mapping().ok_or("nest arguments must be a mapping")?;
    if map.len() != 3 || map.keys().any(|k| !matches!(k.as_str(), Some("each" | "keep" | "then"))) {
        return Err("nest requires each, keep and then only".into());
    }
    let keep = args["keep"].as_mapping().filter(|m| !m.is_empty() && m.len() <= 64)
        .ok_or("nest.keep maps between 1 and 64 outer fields to new field names")?;
    let mut names = HashSet::new();
    for (from, to) in keep {
        let (Some(from), Some(to)) = (from.as_str(), to.as_str()) else {
            return Err("nest.keep maps field names to field names".into());
        };
        if !field_name(from) || !field_name(to) || !names.insert(to) {
            return Err("nest.keep names distinct fields, each of 1 to 64 ASCII letters, digits or _".into());
        }
    }
    iteration::validate(&args["each"], format, steps, depth + 1)?;
    iteration::validate(&args["then"], format, steps, depth + 1)
}

pub(crate) fn rows(engine: &Engine, context: &Row, lookups: &Lookups, document: &El, args: &Value,
                   maximum: usize, take: usize) -> Result<(Vec<El>, usize), Rejected> {
    let (outer, _) = iteration::rows(engine, context, lookups, document, &args["each"], maximum, usize::MAX)?;
    let keep = args["keep"].as_mapping().unwrap();
    let (mut result, mut count) = (Vec::new(), 0usize);
    for parent in &outer {
        let (inner, found) = iteration::rows(engine, context, lookups, parent, &args["then"],
                                             maximum - count, take.saturating_sub(result.len()))?;
        count += found;
        for mut row in inner {
            if row.scalar || row.array {
                return Err(Rejected::new("nest_row_shape", "A nested row must be a JSON object to carry outer fields"));
            }
            for (from, to) in keep {
                let to = to.as_str().unwrap();
                if row.children.contains_key(to) || row.attrs.contains_key(to) {
                    return Err(Rejected::new("nest_field_conflict", "A kept outer field names a field the nested row has"));
                }
                let value = match parent.children.get(from.as_str().unwrap()) {
                    Some(Child::One(el)) => el.clone(),
                    Some(Child::Many(items)) => {
                        let mut el = El { array: true, ..El::default() };
                        el.children.insert("item".into(), Child::Many(items.clone()));
                        el
                    }
                    None => return Err(Rejected::new("nest_field_missing", "A kept field is not in the outer row")),
                };
                row.add_child(to.into(), value);
                if let Some(keys) = row.json_keys.as_mut() { keys.push(to.into()); }
            }
            result.push(row);
        }
    }
    Ok((result, count))
}
