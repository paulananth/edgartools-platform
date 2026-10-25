//! Shared literal/word search preparation. Names and field preferences are data.
use crate::reference::{
    cover_density, lexemes, query_groups, reference_query_matches, search_token,
};
use crate::{field, read, text, write, Object};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

fn fragments(value: &str, all_widths: bool) -> Vec<String> {
    let characters: Vec<char> = value.to_lowercase().chars().collect();
    let width = characters.len().min(3);
    let widths = if all_widths { 1..=width } else { width..=width };
    let mut tokens = BTreeSet::new();
    for n in widths.filter(|n| *n > 0) {
        for part in characters.windows(n) {
            tokens.insert(search_token(&format!(
                "fragment/{n}/{}",
                part.iter().collect::<String>()
            )));
        }
    }
    tokens.into_iter().collect()
}

fn selected_name(body: &Object, fields: &[String]) -> Result<Option<String>, String> {
    let stored: Object = body
        .get("fields")
        .map(|raw| read(raw))
        .transpose()?
        .unwrap_or_default();
    for name in fields {
        if let Some(raw) = stored.get(name) {
            let cell: Object = read(raw)?;
            if let Some(value) = cell.get("value").filter(|v| v.get() != "null") {
                let value: String = read(value).map_err(|_| "Search name must be text")?;
                if !value.is_empty() {
                    return Ok(Some(value));
                }
            }
        }
    }
    Ok(None)
}

#[derive(Deserialize, Serialize)]
struct Hit {
    id: String,
    name: Option<String>,
    #[serde(default)]
    rank: f64,
    #[serde(default)]
    matched_by: String,
}

pub fn prepare_text_search(raw: &str) -> Result<String, String> {
    let input: Object = serde_json::from_str(raw).map_err(|_| "Invalid text search request")?;
    let output = match text(&input, "operation")?.as_str() {
        "index" | "name" => {
            let fields: Vec<String> = read(field(&input, "fields")?)?;
            if fields.is_empty() || fields.iter().any(|name| name.trim().is_empty()) {
                return Err("Search needs configured name fields".into());
            }
            let body: Object = read(field(&input, "body")?)?;
            let name = selected_name(&body, &fields)?;
            if text(&input, "operation")? == "name" {
                return Ok(write(&name)?.get().into());
            }
            let terms = name
                .as_deref()
                .map(lexemes)
                .unwrap_or_default()
                .iter()
                .map(|term| search_token(term))
                .collect::<BTreeSet<_>>();
            let grams = fragments(name.as_deref().unwrap_or_default(), true);
            Object::from([
                ("name".into(), write(&name)?),
                ("words".into(), write(&terms)?),
                ("fragments".into(), write(&grams)?),
            ])
        }
        "query" => {
            let words = text(&input, "words")?;
            let alternatives = query_groups(&words)
                .into_iter()
                .map(|group| {
                    group
                        .iter()
                        .filter(|term| !term.starts_with('-'))
                        .flat_map(|term| lexemes(term))
                        .map(|term| search_token(&term))
                        .collect::<BTreeSet<_>>()
                })
                .collect::<Vec<_>>();
            let scope = alternatives.iter().any(BTreeSet::is_empty);
            Object::from([
                ("alternatives".into(), write(&alternatives)?),
                ("scope".into(), write(&scope)?),
                ("fragments".into(), write(&fragments(&words, false))?),
            ])
        }
        "rank" => {
            let words = text(&input, "words")?;
            let weight: f64 = read(field(&input, "position_weight")?)?;
            if !weight.is_finite() || !(0.0 < weight && weight <= 1.0) {
                return Err("Invalid search position weight".into());
            }
            let limit: usize = read(field(&input, "limit")?)?;
            let rows: Vec<Hit> = read(field(&input, "rows")?)?;
            let mut unique: BTreeMap<String, Hit> = BTreeMap::new();
            for row in rows {
                if let Some(old) = unique.get(&row.id) {
                    if old.name != row.name {
                        return Err("Search candidates disagree on an original name".into());
                    }
                } else {
                    unique.insert(row.id.clone(), row);
                }
            }
            let mut words_found = Vec::new();
            let mut contains_found = Vec::new();
            let literal = words.to_lowercase();
            for mut row in unique.into_values() {
                let name = row.name.as_deref().unwrap_or_default();
                if reference_query_matches(&words, name) {
                    row.rank = cover_density(&words, name, weight);
                    row.matched_by = "words".into();
                    words_found.push(row);
                } else if name.to_lowercase().contains(&literal) {
                    row.rank = 0.0;
                    row.matched_by = "contains".into();
                    contains_found.push(row);
                }
            }
            let mut found = if words_found.is_empty() {
                contains_found
            } else {
                words_found
            };
            found.sort_by(|a, b| {
                b.rank
                    .total_cmp(&a.rank)
                    .then_with(|| match (&a.name, &b.name) {
                        (Some(a), Some(b)) => a.cmp(b),
                        (None, None) => std::cmp::Ordering::Equal,
                        (None, _) => std::cmp::Ordering::Greater,
                        (_, None) => std::cmp::Ordering::Less,
                    })
                    .then_with(|| a.id.cmp(&b.id))
            });
            found.truncate(limit);
            return Ok(write(&found)?.get().into());
        }
        _ => return Err("Unknown text search operation".into()),
    };
    Ok(write(&output)?.get().into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};

    fn prepare(value: Value) -> Value {
        serde_json::from_str(&prepare_text_search(&value.to_string()).unwrap()).unwrap()
    }

    #[test]
    fn every_literal_probe_is_in_its_original_index() {
        let indexed = prepare(json!({"operation":"index", "fields":["invented"],
            "body":{"fields":{"invented":{"value":"A The 雪 %_a.b@c/d x-y"}}}}));
        for query in ["a", "THE", "雪", "%_", "a.b", "@c", "x-y"] {
            let plan = prepare(json!({"operation":"query","words":query}));
            for token in plan["fragments"].as_array().unwrap() {
                assert!(indexed["fragments"].as_array().unwrap().contains(token));
            }
        }
        assert_eq!(indexed["words"].as_array().unwrap().len(), 7);
    }

    #[test]
    fn negative_only_alternatives_request_the_indexed_scope() {
        assert_eq!(
            prepare(json!({"operation":"query","words":"-snow"}))["scope"],
            true
        );
        assert_eq!(
            prepare(json!({"operation":"query","words":"the OR -snow"}))["scope"],
            true
        );
        assert_eq!(
            prepare(json!({"operation":"query","words":"a the"}))["scope"],
            false
        );
    }

    #[test]
    fn ranking_reuses_word_grammar_then_literal_fallback() {
        let rows = json!([{"id":"two","name":"B the snow"},{"id":"one","name":"A the snow"},
                         {"id":"none","name":null}]);
        let rank = |words| {
            prepare(json!({"operation":"rank","words":words,"rows":rows,
            "limit":5,"position_weight":0.1}))
        };
        assert_eq!(rank("the \"snow\"")[0]["id"], "one");
        assert!(rank("the -snow").as_array().unwrap().is_empty());
        assert_eq!(rank("he sno")[0]["matched_by"], "contains");
        assert_eq!(rank("-missing")[2]["name"], Value::Null);
    }

    #[test]
    fn repeated_candidates_do_not_duplicate_ranked_results() {
        let rows = json!([{"id":"one","name":"the snow"},{"id":"one","name":"the snow"}]);
        let ranked = prepare(json!({"operation":"rank","words":"snow","rows":rows,
            "limit":5,"position_weight":0.1}));
        assert_eq!(ranked.as_array().unwrap().len(), 1);
    }
}
