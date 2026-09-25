//! Source Contract reader for one bronze artifact.
//!
//! The grammar is the one in `docs/specs/source-contract/spec.md` §8. This
//! crate implements the XML read path and the primitives the 13F contract
//! uses: `each`, `ordinal`, `text`, `number`, `steps`, and `custom`.

mod xml;

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use serde_yaml::Value;

use crate::xml::{parse_xml, strip_control_chars, Child, El};

#[derive(Clone, Debug, PartialEq)]
pub enum Val {
    Null,
    Int(i64),
    Float(f64),
    Str(String),
}

pub type Step = fn(&Val) -> Val;
pub type Row = BTreeMap<String, Val>;

pub struct Engine {
    contract: Value,
    steps: BTreeMap<String, Step>,
}

impl Engine {
    pub fn load(contract_yaml: &Path) -> Result<Self, String> {
        let text = fs::read_to_string(contract_yaml).map_err(|e| e.to_string())?;
        let contract: Value = serde_yaml::from_str(&text).map_err(|e| e.to_string())?;
        Ok(Self {
            contract,
            steps: BTreeMap::new(),
        })
    }

    pub fn with_step(mut self, name: &str, step: Step) -> Self {
        self.steps.insert(name.to_string(), step);
        self
    }

    pub fn parse(&self, bytes: &[u8]) -> Result<BTreeMap<String, Vec<Row>>, String> {
        let read = self.contract.get("read").ok_or("contract has no read")?;
        let format = scalar(read.get("format"))?;
        if format != "xml" {
            return Err(format!("this reader implements xml, not {format}"));
        }
        let document = match read_document(read, bytes) {
            Some(document) => document,
            None => return Ok(empty_tables(read)),
        };
        let mut out = empty_tables(read);
        let tables = read
            .get("tables")
            .and_then(Value::as_mapping)
            .ok_or("read.tables is missing")?;
        for (name, table) in tables {
            let table_name = name
                .as_str()
                .ok_or("table name is not a string")?
                .to_string();
            let each = scalar(table.get("each")).unwrap_or_else(|_| ".".into());
            let items = items_of(&document, &each)?;
            for (ordinal, item) in items.into_iter().enumerate() {
                let mut row = Row::new();
                let columns = table
                    .get("columns")
                    .and_then(Value::as_mapping)
                    .ok_or("columns missing")?;
                for (column, expr) in columns {
                    let column = column.as_str().ok_or("column name is not a string")?;
                    let value = eval(self, &document, item, ordinal as i64 + 1, expr)?;
                    row.insert(column.to_string(), value);
                }
                out.get_mut(&table_name).ok_or("unknown table")?.push(row);
            }
        }
        Ok(out)
    }
}

/// `none` and `nan` are null, matching `parse_thirteenf`'s text blanking.
pub fn blank_missing_token(value: &Val) -> Val {
    let Val::Str(text) = value else {
        return value.clone();
    };
    let text = text.trim();
    if text.is_empty() || text.eq_ignore_ascii_case("none") || text.eq_ignore_ascii_case("nan") {
        Val::Null
    } else {
        Val::Str(text.to_string())
    }
}

fn empty_tables(read: &Value) -> BTreeMap<String, Vec<Row>> {
    let mut out = BTreeMap::new();
    if let Some(tables) = read.get("tables").and_then(Value::as_mapping) {
        for name in tables.keys() {
            if let Some(name) = name.as_str() {
                out.insert(name.to_string(), Vec::new());
            }
        }
    }
    out
}

fn read_document(read: &Value, bytes: &[u8]) -> Option<El> {
    match parse_xml(bytes) {
        Ok((root, el)) => accept_root(read, root, el),
        Err(_) => {
            if scalar(read.get("on_parse_error")).ok().as_deref()
                != Some("retry_without_control_chars")
            {
                return None;
            }
            let stripped = strip_control_chars(bytes);
            let (root, el) = parse_xml(&stripped).ok()?;
            accept_root(read, root, el)
        }
    }
}

fn accept_root(read: &Value, root: String, el: El) -> Option<El> {
    match scalar(read.get("root")) {
        Ok(expected) if expected != root => None,
        _ => Some(el),
    }
}

fn items_of<'a>(document: &'a El, each: &str) -> Result<Vec<&'a El>, String> {
    if each == "." {
        return Ok(vec![document]);
    }
    match lookup(document, each)? {
        Found::El(el) => Ok(vec![el]),
        Found::List(rows) => Ok(rows),
        Found::Missing => Ok(Vec::new()),
        Found::Text(_) => Err(format!("each {each} landed on text")),
    }
}

enum Found<'a> {
    Missing,
    El(&'a El),
    List(Vec<&'a El>),
    Text(String),
}

fn lookup<'a>(start: &'a El, path: &str) -> Result<Found<'a>, String> {
    if path == "." {
        return Ok(Found::El(start));
    }
    let mut current = Found::El(start);
    for (index, key) in path.split('.').enumerate() {
        current = match current {
            Found::List(_) => {
                return Err(format!(
                    "path {path} crosses a repeating group at segment {index}; use each"
                ));
            }
            Found::Missing => Found::Missing,
            Found::Text(_) if key == "$" => current,
            Found::Text(_) => Found::Missing,
            Found::El(el) if key == "$" => match &el.text {
                Some(text) => Found::Text(text.clone()),
                None => Found::Missing,
            },
            Found::El(el) if let Some(rest) = key.strip_prefix('@') => {
                match el.attrs.get(&format!("@{rest}")) {
                    Some(value) => Found::Text(value.clone()),
                    None => Found::Missing,
                }
            }
            Found::El(el) => match el.children.get(key) {
                None => Found::Missing,
                Some(Child::One(child)) => Found::El(child),
                Some(Child::Many(rows)) => Found::List(rows.iter().collect()),
            },
        };
    }
    Ok(current)
}

fn eval(
    engine: &Engine,
    document: &El,
    item: &El,
    ordinal: i64,
    expr: &Value,
) -> Result<Val, String> {
    let Some(map) = expr.as_mapping() else {
        return Err("a column expression must be one call".into());
    };
    if map.len() != 1 {
        return Err("a column expression must be exactly one call".into());
    }
    let (name, args) = map.iter().next().unwrap();
    let name = name.as_str().ok_or("primitive name is not a string")?;
    match name {
        "ordinal" => Ok(Val::Int(ordinal)),
        "text" => text_of(scope(document, item, args), args),
        "number" => number_of(scope(document, item, args), args),
        "steps" => {
            let mut value = Val::Null;
            for step in args.as_sequence().ok_or("steps must be a list")? {
                value = eval(engine, document, item, ordinal, step)?;
            }
            Ok(value)
        }
        "custom" => {
            let step = scalar(args.get("step"))?;
            let function = engine
                .steps
                .get(&step)
                .ok_or_else(|| format!("no value step {step}"))?;
            let mut input = Val::Null;
            if let Some(inputs) = args.get("inputs").and_then(Value::as_mapping) {
                if inputs.len() != 1 {
                    return Err(format!("step {step} is called with one input"));
                }
                let (_, expr) = inputs.iter().next().unwrap();
                input = eval(engine, document, item, ordinal, expr)?;
            }
            Ok(function(&input))
        }
        other => Err(format!("primitive {other} is not implemented")),
    }
}

fn scope<'a>(document: &'a El, item: &'a El, args: &Value) -> &'a El {
    if scalar(args.get("from")).ok().as_deref() == Some("document") {
        document
    } else {
        item
    }
}

fn text_of(start: &El, args: &Value) -> Result<Val, String> {
    let path = scalar(args.get("path"))?;
    let default = yaml_val(args.get("default"));
    match lookup(start, &path)? {
        Found::Missing => Ok(default),
        Found::Text(text) => Ok(Val::Str(text.trim().to_string())),
        Found::El(_) | Found::List(_) => Err(format!("path {path} does not end at text")),
    }
}

fn number_of(start: &El, args: &Value) -> Result<Val, String> {
    let path = scalar(args.get("path"))?;
    let default = yaml_val(args.get("default"));
    let text = match lookup(start, &path)? {
        Found::Missing => return Ok(default),
        Found::Text(text) => text,
        Found::El(_) | Found::List(_) => {
            return Err(format!("path {path} does not end at a number"))
        }
    };
    let text = text.trim();
    if text.is_empty() {
        return Ok(default);
    }
    text.parse::<f64>().map(Val::Float).or(Ok(default))
}

fn scalar(value: Option<&Value>) -> Result<String, String> {
    value
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| "expected a string".into())
}

fn yaml_val(value: Option<&Value>) -> Val {
    match value {
        None | Some(Value::Null) => Val::Null,
        Some(Value::Bool(true)) => Val::Str("true".into()),
        Some(Value::Bool(false)) => Val::Str("false".into()),
        Some(Value::Number(number)) => {
            if let Some(int) = number.as_i64() {
                Val::Int(int)
            } else if let Some(float) = number.as_f64() {
                Val::Float(float)
            } else {
                Val::Null
            }
        }
        Some(Value::String(text)) => Val::Str(text.clone()),
        Some(_) => Val::Null,
    }
}
