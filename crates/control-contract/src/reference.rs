//! Reference hierarchy, canonical content and exact aggregation; no store I/O.
use crate::{calculate_hash, field, read, text, write, Document, Object};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
struct Input {
    codes: Vec<Object>,
    #[serde(default)]
    levels: BTreeMap<usize, String>,
    #[serde(default)]
    samples: usize,
    #[serde(default = "prepare_default")]
    prepare: bool,
}

fn prepare_default() -> bool {
    true
}

pub fn order_reference_rows(raw: &str) -> Result<String, String> {
    let rows: Vec<Object> = serde_json::from_str(raw).map_err(|_| "Invalid reference rows")?;
    let mut keyed = rows
        .into_iter()
        .map(|row| Ok((text(&row, "code")?, row)))
        .collect::<Result<Vec<_>, String>>()?;
    keyed.sort_by(|a, b| a.0.cmp(&b.0));
    Ok(
        write(&keyed.into_iter().map(|(_, row)| row).collect::<Vec<_>>())?
            .get()
            .to_string(),
    )
}

#[derive(Deserialize)]
struct ContextLists {
    labels: Vec<Object>,
    crosswalk: Vec<Object>,
}

pub fn prepare_reference_context(raw: &str) -> Result<String, String> {
    let input: ContextLists = serde_json::from_str(raw).map_err(|_| "Invalid reference context lists")?;
    let mut labels = input.labels.into_iter().map(|row| Ok((text(&row,"language")?, text(&row,"label")?)))
        .collect::<Result<Vec<_>,String>>()?;
    labels.sort();
    let mut crosswalk = input.crosswalk.into_iter().map(|row| Ok((
        (text(&row,"to_set")?, text(&row,"to_version")?, text(&row,"to_code")?), row)))
        .collect::<Result<Vec<_>,String>>()?;
    crosswalk.sort_by(|a,b| a.0.cmp(&b.0));
    let result = BTreeMap::from([
        ("synonyms", write(&labels.into_iter().map(|(_, label)|label).collect::<Vec<_>>())?),
        ("crosswalk", write(&crosswalk.into_iter().map(|(_, row)|row).collect::<Vec<_>>())?),
    ]);
    Ok(write(&result)?.get().to_string())
}

fn optional_text(row: &Object, name: &str) -> Result<Option<String>, String> {
    match row.get(name) {
        None => Ok(None),
        Some(value) => read(value),
    }
}

pub(crate) fn query_groups(words: &str) -> Vec<Vec<String>> {
    let mut terms = Vec::new();
    let mut token = String::new();
    let mut quoted = false;
    for ch in words.chars() {
        if ch == '"' {
            quoted = !quoted;
            token.push(ch);
        } else if ch.is_whitespace() && !quoted {
            if !token.is_empty() {
                terms.push(std::mem::take(&mut token));
            }
        } else {
            token.push(ch);
        }
    }
    if !token.is_empty() {
        terms.push(token);
    }
    let mut groups = vec![Vec::new()];
    let count = terms.len();
    let mut terms = terms.into_iter().enumerate();
    while let Some((index, mut term)) = terms.next() {
        if term == "-" {
            if let Some((_, following)) = terms.next() {
                term.push_str(&following);
            }
        }
        if term.eq_ignore_ascii_case("or") && index + 1 < count
            && !groups.last().unwrap().is_empty() {
            groups.push(Vec::new());
        } else if !lexemes(&term).is_empty() {
            groups.last_mut().unwrap().push(term);
        }
    }
    groups.into_iter().filter(|g| !g.is_empty()).collect()
}

pub(crate) fn search_token(term: &str) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(term.as_bytes()))
}

pub fn encode_reference_search(label: &str) -> String {
    lexemes(label).iter().map(|term| search_token(term)).collect::<Vec<_>>().join(" ")
}

pub fn compile_reference_query(words: &str) -> String {
    // Probe a superset: native matching checks exclusions and phrase positions.
    // A negative-only alternative needs the complete indexed version scope.
    let mut groups = Vec::new();
    for group in query_groups(words) {
        let terms = group.iter().filter(|term| !term.starts_with('-'))
            .flat_map(|term| lexemes(term)).collect::<BTreeSet<_>>();
        if terms.is_empty() { return String::new(); }
        groups.push(format!("({})", terms.iter().map(|term| format!("+{}", search_token(term)))
            .collect::<Vec<_>>().join(" ")));
    }
    groups.join(" ")
}

pub(crate) fn lexemes(value: &str) -> Vec<String> {
    let mut found = Vec::new();
    // Keep compound words as well as their components, and dotted tokens as
    // units, matching the existing simple-parser word/compound behavior.
    for token in value.split(|ch: char| !ch.is_alphanumeric() && !matches!(ch, '-' | '.' | '@' | '/')) {
        let token = token.trim_matches(['-', '.']).to_lowercase();
        if token.is_empty() { continue; }
        if token.contains(['.', '@', '/']) {
            found.push(token);
        } else if token.contains("--") {
            found.extend(token.split('-').filter(|s| !s.is_empty()).map(str::to_string));
        } else {
            found.push(token.clone());
            if token.contains('-') {
                found.extend(token.split('-').filter(|s| !s.is_empty()).map(str::to_string));
            }
        }
    }
    found
}

pub fn reference_query_matches(words: &str, label: &str) -> bool {
    let tokens = lexemes(label);
    query_groups(words).iter().any(|group| group.iter().all(|term| {
        let negative = term.starts_with('-');
        let term = term.trim_start_matches('-');
        let terms = lexemes(term);
        if terms.is_empty() { return false; }
        let phrase = term.starts_with('"') || (terms.len() > 1 && !term.contains([':', '!', '&']));
        let found = if phrase {
            tokens.windows(terms.len()).any(|part| part == terms)
        } else {
            terms.iter().all(|word| tokens.contains(word))
        };
        found != negative
    }))
}

pub(crate) fn cover_density(words: &str, label: &str, weight: f64) -> f64 {
    // Minimal positive covers, with intervening non-query tokens discounted.
    // Formula reference: PostgreSQL 16 tsrank.c calc_rank_cd / Cover:
    // https://github.com/postgres/postgres/blob/REL_16_STABLE/src/backend/utils/adt/tsrank.c
    let groups = query_groups(words)
        .into_iter()
        .map(|g| {
            g.into_iter()
                .filter(|term| !term.starts_with('-'))
                .map(|term| (term.starts_with('"'), lexemes(&term)))
                .filter(|(_, terms)| !terms.is_empty())
                .collect::<Vec<_>>()
        })
        .filter(|g| !g.is_empty())
        .collect::<Vec<_>>();
    let tokens = lexemes(label);
    let wanted = groups
        .iter()
        .flat_map(|g| g.iter().flat_map(|(_, terms)| terms))
        .collect::<BTreeSet<_>>();
    let positions = tokens
        .iter()
        .enumerate()
        .filter_map(|(i, token)| wanted.contains(token).then_some(i))
        .collect::<Vec<_>>();
    let matches = |start: usize, end: usize| {
        let window = &tokens[positions[start]..=positions[end]];
        groups.iter().any(|group| {
            group.iter().all(|(phrase, terms)| {
                if *phrase {
                    window.windows(terms.len()).any(|part| part == terms)
                } else {
                    terms.iter().all(|term| window.contains(term))
                }
            })
        })
    };
    let mut score = 0.0;
    let mut start = 0;
    while start < positions.len() {
        let Some(end) = (start..positions.len()).find(|&end| matches(start, end)) else {
            break;
        };
        let begin = (start..=end)
            .rev()
            .find(|&begin| matches(begin, end))
            .unwrap();
        let noise = (positions[end] - positions[begin]).saturating_sub(end - begin);
        score += (weight as f32 as f64) / (1 + noise) as f64;
        start = begin + 1;
    }
    score as f32 as f64
}

#[derive(Deserialize, Serialize, Clone)]
struct SearchHit {
    code: String,
    label: String,
    label_path: String,
    matched_by: String,
    rank: f64,
    #[serde(skip_serializing)]
    search_text: String,
}

#[derive(Deserialize)]
struct Search {
    rows: Vec<SearchHit>,
    limit: usize,
    words: String,
    synonym_weight: f64,
    position_weight: f64,
}

pub fn prepare_reference_search(raw: &str) -> Result<String, String> {
    let input: Search =
        serde_json::from_str(raw).map_err(|_| "Invalid reference search candidates")?;
    let priority = |hit: &SearchHit| match hit.matched_by.as_str() {
        "label" => 0,
        "synonym" => 1,
        "label contains" => 2,
        "synonym contains" => 3,
        _ => 4,
    };
    if !(0.0 < input.synonym_weight && input.synonym_weight <= 1.0)
        || !(0.0 < input.position_weight && input.position_weight <= 1.0)
    {
        return Err("Invalid reference search weights".into());
    }
    let mut best: BTreeMap<String, SearchHit> = BTreeMap::new();
    for mut hit in input.rows {
        if !hit.rank.is_finite() || hit.rank < 0.0 || priority(&hit) == 4 {
            return Err("Invalid reference search rank".into());
        }
        if !hit.matched_by.ends_with(" contains") {
            hit.rank = cover_density(&input.words, &hit.search_text, input.position_weight);
            if hit.matched_by == "synonym" {
                hit.rank *= input.synonym_weight;
            }
        }
        let take = best
            .get(&hit.code)
            .map(|old| {
                hit.rank > old.rank || (hit.rank == old.rank && priority(&hit) < priority(old))
            })
            .unwrap_or(true);
        if take {
            best.insert(hit.code.clone(), hit);
        }
    }
    let mut found = best.into_values().collect::<Vec<_>>();
    found.sort_by(|a, b| b.rank.total_cmp(&a.rank).then_with(|| a.code.cmp(&b.code)));
    found.truncate(input.limit);
    Ok(write(&found)?.get().to_string())
}

fn list(row: &Object, name: &str) -> Result<Vec<Object>, String> {
    match row.get(name) {
        None => Ok(Vec::new()),
        Some(value) if value.get() == "null" => Ok(Vec::new()),
        Some(value) => read(value),
    }
}

/// Exact decimal text as filed: an optional minus, digits, and optional decimals.
fn is_decimal(text: &str) -> bool {
    let digits = text.strip_prefix('-').unwrap_or(text);
    let (whole, fraction) = match digits.split_once('.') {
        Some((whole, fraction)) => (whole, Some(fraction)),
        None => (digits, None),
    };
    !whole.is_empty()
        && whole.bytes().all(|b| b.is_ascii_digit())
        && fraction.map_or(true, |f| !f.is_empty() && f.bytes().all(|b| b.is_ascii_digit()))
}

/// A code's named properties (ticket 132): each name lower-case words joined by
/// `_`; each value text, `true` or `false`, or a list of distinct texts (kept
/// sorted). None when the code has none, so a version published before
/// properties existed keeps its bytes.
pub fn code_properties(row: &Object) -> Result<Option<Document>, String> {
    use serde_json::Value;
    const REFUSED: &str = "A code's properties are named text, true or false, or a list of distinct texts";
    let found: Value = match row.get("properties") {
        None => return Ok(None),
        Some(raw) => serde_json::from_str(raw.get()).map_err(|_| REFUSED)?,
    };
    let given = match found {
        Value::Null => return Ok(None),
        Value::Object(given) if !given.is_empty() => given,
        _ => return Err(REFUSED.into()),
    };
    let named = |name: &str| {
        name.len() <= 64
            && name.starts_with(|c: char| c.is_ascii_lowercase())
            && name.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
    };
    let filled = |text: &str| !text.trim().is_empty() && text.trim() == text;
    let mut kept = BTreeMap::new();
    for (name, value) in given {
        if !named(&name) {
            return Err(REFUSED.into());
        }
        let value = match value {
            Value::String(text) if filled(&text) => Value::String(text),
            Value::Bool(flag) => Value::Bool(flag),
            Value::Array(items) if !items.is_empty() => {
                let mut texts = items
                    .into_iter()
                    .map(|item| match item {
                        Value::String(text) if filled(&text) => Ok(text),
                        _ => Err(REFUSED.to_string()),
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                let count = texts.len();
                texts.sort();
                texts.dedup();
                if texts.len() != count {
                    return Err(REFUSED.into());
                }
                Value::from(texts)
            }
            _ => return Err(REFUSED.into()),
        };
        kept.insert(name, value);
    }
    Ok(Some(write(&kept)?))
}

pub fn prepare_reference_version(raw: &str) -> Result<String, String> {
    let input: Input = serde_json::from_str(raw).map_err(|_| "Invalid reference preparation")?;
    let mut by_code = BTreeMap::new();
    for row in &input.codes {
        if by_code.insert(text(row, "code")?, row).is_some() {
            return Err("A reference version has duplicate codes".into());
        }
    }
    let mut paths: Vec<Object> = Vec::new();
    let mut canonical = String::new();
    let mut invalid = 0usize;
    let mut with_parent = 0usize;
    let mut mappings: BTreeMap<[String; 3], usize> = BTreeMap::new();
    let mut samples = Vec::new();
    for (code, row) in &by_code {
        if input.prepare {
            let mut chain = vec![*row];
            let mut seen = BTreeSet::from([code.to_string()]);
            while let Some(parent) = optional_text(chain.last().unwrap(), "parent_code")? {
                if !seen.insert(parent.clone()) {
                    return Err("The hierarchy has a cycle through a code".into());
                }
                let row = by_code
                    .get(&parent)
                    .ok_or("A code names a parent the version lacks")?;
                chain.push(*row);
            }
            chain.reverse();
            let level = input.levels.get(&chain.len());
            let path = chain
                .iter()
                .map(|row| text(row, "code").map(|s| s.replace('\\', "\\\\").replace('/', "\\/")))
                .collect::<Result<Vec<_>, _>>()?
                .join("/");
            let label_path = chain
                .iter()
                .map(|row| text(row, "label"))
                .collect::<Result<Vec<_>, _>>()?
                .join(" > ");
            paths.push(BTreeMap::from([
                ("code".into(), write(code)?),
                ("path".into(), write(&path)?),
                ("label_path".into(), write(&label_path)?),
                ("level".into(), write(&level)?),
                ("depth".into(), write(&chain.len())?),
            ]));
        }
        let mut body: Object = BTreeMap::new();
        for name in [
            "code",
            "label",
            "definition",
            "parent_code",
            "valid_from",
            "valid_to",
            "status",
            "invalid_reason",
        ] {
            body.insert(
                name.into(),
                match row.get(name) {
                    Some(v) => v.clone(),
                    None => write(&Option::<String>::None)?,
                },
            );
        }
        // A typed value joins the canonical form only on a code that has one,
        // so every version published before values existed keeps its bytes.
        match (optional_text(row, "value")?, optional_text(row, "unit")?) {
            (None, None) => {}
            (Some(value), Some(unit)) if is_decimal(&value) && !unit.trim_matches(' ').is_empty() => {
                body.insert("value".into(), write(&value)?);
                body.insert("unit".into(), write(&unit)?);
            }
            _ => return Err("A code's value is decimal text with its unit, or neither".into()),
        }
        if let Some(properties) = code_properties(row)? {
            body.insert("properties".into(), properties);
        }
        let level = paths
            .last()
            .and_then(|p| p.get("level"))
            .cloned()
            .unwrap_or(write(&Option::<String>::None)?);
        body.insert("level".into(), level);
        let mut labels = list(row, "labels")?
            .iter()
            .map(|label| {
                Ok([
                    text(label, "language")?,
                    text(label, "kind")?,
                    text(label, "label")?,
                ])
            })
            .collect::<Result<Vec<[String; 3]>, String>>()?;
        labels.sort();
        body.insert("labels".into(), write(&labels)?);
        let mut crosswalk = Vec::new();
        for mapping in list(row, "crosswalk")? {
            let values = [
                text(&mapping, "to_set")?,
                text(&mapping, "to_version")?,
                text(&mapping, "to_code")?,
                text(&mapping, "match_type")?,
            ];
            *mappings
                .entry([values[0].clone(), values[1].clone(), values[3].clone()])
                .or_default() += 1;
            crosswalk.push(values);
        }
        crosswalk.sort();
        body.insert("crosswalk".into(), write(&crosswalk)?);
        canonical.push_str(&crate::canonical(write(&body)?.as_ref())?);
        canonical.push('\n');
        invalid += usize::from(optional_text(row, "status")?.as_deref() == Some("invalid"));
        with_parent += usize::from(optional_text(row, "parent_code")?.is_some());
        if samples.len() < input.samples {
            samples.push(BTreeMap::from([
                ("code".to_string(), field(row, "code")?.to_owned()),
                ("label".to_string(), field(row, "label")?.to_owned()),
                (
                    "parent_code".to_string(),
                    row.get("parent_code")
                        .cloned()
                        .unwrap_or(write(&Option::<String>::None)?),
                ),
            ]));
        }
    }
    // The paths API retains input order; canonical content and samples are
    // ordered by complete Unicode code points independently of SQL collation.
    let positions = input
        .codes
        .iter()
        .enumerate()
        .map(|(i, row)| Ok((text(row, "code")?, i)))
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    paths.sort_by_key(|p| positions.get(&text(p, "code").unwrap()).copied().unwrap());
    let maps_to = mappings
        .into_iter()
        .map(|([to_set, to_version, match_type], rows)| {
            Ok(BTreeMap::from([
                ("to_set", write(&to_set)?),
                ("to_version", write(&to_version)?),
                ("match_type", write(&match_type)?),
                ("rows", write(&rows)?),
            ]))
        })
        .collect::<Result<Vec<_>, String>>()?;
    let output: BTreeMap<&str, Document> = BTreeMap::from([
        ("sha256", write(&calculate_hash(canonical.as_bytes()))?),
        ("canonical", write(&canonical)?),
        ("paths", write(&paths)?),
        ("maps_to", write(&maps_to)?),
        ("sample_codes", write(&samples)?),
        (
            "counts",
            write(&BTreeMap::from([
                ("codes", input.codes.len()),
                ("invalid", invalid),
                ("with_parent", with_parent),
            ]))?,
        ),
    ]);
    Ok(write(&output)?.get().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_value_joins_the_canonical_form_only_where_a_code_has_one() {
        let plain = prepare_reference_version(r#"{"codes":[{"code":"a","label":"A","value":null,"unit":null}]}"#).unwrap();
        let before = prepare_reference_version(r#"{"codes":[{"code":"a","label":"A"}]}"#).unwrap();
        assert_eq!(plain, before);
        let valued = prepare_reference_version(
            r#"{"codes":[{"code":"a","label":"A","value":"25.250000","unit":"percent"}]}"#,
        )
        .unwrap();
        assert!(valued.contains(r#"\"unit\":\"percent\""#) && valued.contains(r#"\"value\":\"25.250000\""#), "{valued}");
        for bad in [r#""value":"25""#, r#""value":"2.5e1","unit":"percent""#, r#""value":"25.","unit":"percent""#,
                    r#""value":"","unit":"percent""#, r#""value":"25","unit":" ""#] {
            let raw = format!(r#"{{"codes":[{{"code":"a","label":"A",{bad}}}]}}"#);
            assert!(prepare_reference_version(&raw).unwrap_err().contains("decimal text"), "{bad}");
        }
    }

    #[test]
    fn properties_join_the_canonical_form_only_where_a_code_has_some() {
        let before = prepare_reference_version(r#"{"codes":[{"code":"a","label":"A"}]}"#).unwrap();
        let null = prepare_reference_version(r#"{"codes":[{"code":"a","label":"A","properties":null}]}"#).unwrap();
        assert_eq!(null, before);
        let given = prepare_reference_version(
            r#"{"codes":[{"code":"a","label":"A","properties":{"to":["b","a"],"hierarchy":true,"cycles":"invalid"}}]}"#,
        )
        .unwrap();
        let expected = r#"\"properties\":{\"cycles\":\"invalid\",\"hierarchy\":true,\"to\":[\"a\",\"b\"]}"#;
        assert!(given.contains(expected), "{given}");
        for bad in [r#"{}"#, r#"{"Bad":"x"}"#, r#"{"x":""}"#, r#"{"x":" y"}"#, r#"{"x":1}"#, r#"{"x":[]}"#,
                    r#"{"x":["a","a"]}"#, r#"{"x":[true]}"#, r#"{"x":{"y":"z"}}"#, r#"["x"]"#] {
            let raw = format!(r#"{{"codes":[{{"code":"a","label":"A","properties":{bad}}}]}}"#);
            assert!(prepare_reference_version(&raw).unwrap_err().contains("properties"), "{bad}");
        }
    }

    #[test]
    fn hierarchy_escapes_and_refuses_missing_parents_and_cycles() {
        let result = prepare_reference_version(r#"{"codes":[{"code":"a/","label":"Root"},{"code":"b","label":"Leaf","parent_code":"a/"}],"levels":{"2":"Leaf level"}}"#).unwrap();
        assert!(result.contains(r#"a\\//b"#));
        assert!(prepare_reference_version(
            r#"{"codes":[{"code":"a","label":"A","parent_code":"missing"}]}"#
        )
        .unwrap_err()
        .contains("parent"));
        assert!(prepare_reference_version(
            r#"{"codes":[{"code":"a","label":"A","parent_code":"a"}]}"#
        )
        .unwrap_err()
        .contains("cycle"));
    }
}
