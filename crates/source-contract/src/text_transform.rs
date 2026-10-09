//! Generic, ordered text operations. No source, loader or MDM policy lives here.
use regex::{Regex, RegexBuilder};
use serde_yaml::Value;
use unicode_normalization::{char::canonical_combining_class, UnicodeNormalization};
use crate::Rejected;

const MAX_TEXT: usize = 1 << 20;
const MAX_ARGUMENT: usize = 4096;
const MAX_SEARCH_BYTES: usize = 8 << 20;

pub(crate) struct Recipe(Vec<Operation>);
enum Operation {
    Nfkd,
    StripCombining,
    Upper,
    Trim,
    Replace(String, String),
    RegexReplace(Regex, String),
    Pad(String, String),
    RemovePrefix(String),
    Lines(Recipe),
    Slice(usize, usize),
    Tokens(std::collections::HashMap<String, String>),
}

pub(crate) fn cost(value: &Value) -> (usize, usize) {
    let mut result = (0, 0);
    for op in value.as_sequence().into_iter().flatten() {
        result.0 += 1;
        result.1 += usize::from(op.get("regex_replace").is_some());
        if let Some(inner) = op.get("lines") {
            // Nested lines are rejected by compile. Inspect one bounded level
            // here rather than recursively visiting malformed recipes.
            if let Some(ops) = inner.as_sequence() {
                result.0 += ops.len();
                result.1 += ops.iter().filter(|op| op.get("regex_replace").is_some()).count();
            }
        }
    }
    result
}

fn text(value: &Value) -> Result<String, String> {
    value.as_str().filter(|s| s.len() <= MAX_ARGUMENT).map(str::to_owned)
        .ok_or_else(|| "text transform arguments are strings of at most 4096 bytes".into())
}
fn pair(value: &Value, first: &str, second: &str) -> Result<(String, String), String> {
    let args = value.as_mapping().filter(|m| m.len() == 2)
        .ok_or("text transform requires exactly two named arguments")?;
    Ok((text(args.get(Value::String(first.into())).ok_or("missing text transform argument")?)?,
        text(args.get(Value::String(second.into())).ok_or("missing text transform argument")?)?))
}
fn enabled(value: &Value) -> Result<(), String> {
    if value.as_bool() == Some(true) { Ok(()) } else { Err("text transform flag must be true".into()) }
}
fn bounded_push(out: &mut String, text: &str) -> Result<(), Rejected> {
    if text.len() > MAX_TEXT.saturating_sub(out.len()) {
        return Err(Rejected::new("text_transform_limit", "text transformation exceeds 1048576 bytes"));
    }
    out.push_str(text);
    Ok(())
}
fn chars(iter: impl Iterator<Item=char>) -> Result<String, Rejected> {
    let mut out = String::new();
    for c in iter { bounded_push(&mut out, c.encode_utf8(&mut [0; 4]))?; }
    Ok(out)
}
// Python's str.strip includes four ASCII separators outside Unicode White_Space.
pub(crate) fn whitespace(c: char) -> bool { c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c) }

impl Recipe {
    pub(crate) fn compile(value: &Value) -> Result<Self, String> {
        let list = value.as_sequence().filter(|s| !s.is_empty() && s.len() <= 64)
            .ok_or("text transforms is a list of 1..64 operations")?;
        let mut result = Vec::new();
        for value in list {
            let map = value.as_mapping().filter(|m| m.len() == 1)
                .ok_or("a text transform has exactly one operation")?;
            let (name, args) = map.iter().next().unwrap();
            result.push(match name.as_str() {
                Some("unicode") if args.as_str() == Some("nfkd") => Operation::Nfkd,
                Some("strip_combining") => { enabled(args)?; Operation::StripCombining }
                Some("case") if args.as_str() == Some("upper") => Operation::Upper,
                Some("trim") => { enabled(args)?; Operation::Trim }
                Some("replace") => {
                    let (from, to) = pair(args, "from", "to")?;
                    if from.is_empty() { return Err("text replace from must be nonempty".into()); }
                    Operation::Replace(from, to)
                }
                Some("regex_replace") => {
                    let (pattern, replacement) = pair(args, "pattern", "with")?;
                    let regex = RegexBuilder::new(&pattern).size_limit(MAX_TEXT).dfa_size_limit(MAX_TEXT)
                        .nest_limit(32).build().map_err(|e| format!("text transform regex: {e}"))?;
                    Operation::RegexReplace(regex, replacement)
                }
                Some("pad") => { let (left, right) = pair(args, "left", "right")?; Operation::Pad(left, right) }
                Some("remove_prefix") => Operation::RemovePrefix(text(args)?),
                Some("lines") => {
                    if args.as_sequence().is_some_and(|ops| ops.iter().any(|op| op.get("lines").is_some())) {
                        return Err("lines transforms cannot contain another lines operation".into());
                    }
                    Operation::Lines(Recipe::compile(args)?)
                }
                Some("tokens") => {
                    let map = args.as_mapping().filter(|m| m.len() <= 256).ok_or("tokens requires at most 256 text replacements")?;
                    let mut replacements = std::collections::HashMap::new();
                    for (key, value) in map {
                        let key = text(key)?;
                        if key.is_empty() || key.chars().any(whitespace) { return Err("tokens keys are nonempty whitespace-free text".into()); }
                        replacements.insert(key, text(value)?);
                    }
                    Operation::Tokens(replacements)
                }
                Some("slice") => {
                    let map = args.as_mapping().filter(|m| m.len() == 2).ok_or("slice requires start and end")?;
                    let start = map.get(Value::String("start".into())).and_then(Value::as_u64).ok_or("slice start is unsigned")?;
                    let end = map.get(Value::String("end".into())).and_then(Value::as_u64).ok_or("slice end is unsigned")?;
                    if start > end || end > MAX_TEXT as u64 { return Err("slice requires 0 <= start <= end <= 1048576".into()); }
                    Operation::Slice(start as usize, end as usize)
                }
                _ => return Err("unknown text transform operation or argument".into()),
            });
        }
        Ok(Self(result))
    }

    pub(crate) fn apply(&self, mut value: String) -> Result<String, Rejected> {
        if value.len() > MAX_TEXT { return Err(Rejected::new("text_transform_limit", "text transform input exceeds 1048576 bytes")); }
        for operation in &self.0 {
            value = match operation {
                Operation::Nfkd => chars(value.nfkd())?,
                Operation::StripCombining => chars(value.chars().filter(|c| canonical_combining_class(*c) == 0))?,
                Operation::Upper => chars(value.chars().flat_map(char::to_uppercase))?,
                Operation::Trim => value.trim_matches(whitespace).to_owned(),
                Operation::RemovePrefix(prefix) => value.strip_prefix(prefix).unwrap_or(&value).to_owned(),
                Operation::Pad(left, right) => {
                    let mut out = String::new();
                    for part in [left.as_str(), value.as_str(), right.as_str()] { bounded_push(&mut out, part)?; }
                    out
                }
                Operation::Replace(from, to) => {
                    let mut out = String::new();
                    let mut cursor = 0;
                    for (start, matched) in value.match_indices(from) {
                        bounded_push(&mut out, &value[cursor..start])?;
                        bounded_push(&mut out, to)?;
                        cursor = start + matched.len();
                    }
                    bounded_push(&mut out, &value[cursor..])?;
                    out
                }
                Operation::RegexReplace(regex, replacement) => {
                    let mut out = String::new();
                    let mut cursor = 0;
                    let mut searched = 0;
                    let mut matches = regex.find_iter(&value);
                    loop {
                        // Charge the entire remaining window BEFORE asking for
                        // the next match. General regex iterators can rescan
                        // the suffix on each call, with quadratic total cost.
                        searched += value.len() - cursor + 1;
                        if searched > MAX_SEARCH_BYTES {
                            return Err(Rejected::new("text_transform_work_limit", "regex replacement exceeds 8388608 cumulative search-window bytes"));
                        }
                        let Some(matched) = matches.next() else { break };
                        bounded_push(&mut out, &value[cursor..matched.start()])?;
                        // Replacement is literal text, never a capture expansion.
                        bounded_push(&mut out, replacement)?;
                        cursor = matched.end();
                    }
                    bounded_push(&mut out, &value[cursor..])?;
                    out
                }
                Operation::Tokens(replacements) => {
                    let mut out = String::new();
                    for token in value.split(whitespace).filter(|token| !token.is_empty()) {
                        if !out.is_empty() { bounded_push(&mut out, " ")?; }
                        bounded_push(&mut out, replacements.get(token).map(String::as_str).unwrap_or(token))?;
                    }
                    out
                }
                Operation::Slice(start, end) => chars(value.chars().skip(*start).take(end - start))?,
                Operation::Lines(recipe) => {
                    let mut out = String::new();
                    for line in value.split('\n') {
                        let line = recipe.apply(line.to_owned())?;
                        if !line.is_empty() {
                            if !out.is_empty() { bounded_push(&mut out, "\n")?; }
                            bounded_push(&mut out, &line)?;
                        }
                    }
                    out
                }
            };
        }
        Ok(value)
    }
}
