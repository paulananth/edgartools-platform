//! The configured source engine (mastering to-do 15).
//!
//! A rules-file contract says how to read one artifact: its format and
//! container, the document checks that fail it, the tables it yields, each
//! table's columns, and the record checks that set a record aside. The grammar
//! grew from `docs/specs/source-contract/spec.md` §8. Python calls this
//! through `edgar_warehouse/rules/source_engine.py`; nothing else does.
//!
//! - A failed artifact is a `Rejected`, with a stable `code`.
//! - A record a check refuses with `on_fail: defer` is `Deferred`, with the
//!   `reason` the rules file names and its raw record.
//! - A `custom` step is a named function the caller registers. The contract
//!   is refused when it loads if a step it names has none.
//!
//! Every read is bounded by the contract's limits (artifact bytes, ZIP member
//! bytes, records); one over a limit fails closed. An artifact is read whole
//! into memory up to those limits: records are not streamed.

mod formats;
pub mod json_sequence;
mod integer;
mod reference;
mod value;
mod context;
mod parallel;
mod matrix;
mod iteration;
mod predicate;
mod json_text;
#[cfg(feature = "python")]
mod python;
mod tree;
mod xml;

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::path::Path;

use chrono::{DateTime, NaiveDate, SecondsFormat, Utc};
use serde_yaml::Value;

use crate::tree::{Child, El, ScalarKind};
pub use crate::tree::Raw;
use crate::xml::{parse_xml, strip_control_chars};

#[derive(Clone, Debug, PartialEq)]
pub enum Val {
    Null,
    Int(i64),
    UInt(u64),
    List(Vec<Val>),
    Map(BTreeMap<String, Val>),
    Bool(bool),
    Float(f64),
    Str(String),
}

/// A failed artifact, or a contract refused when it loads (`code: contract`).
#[derive(Clone, Debug, PartialEq)]
pub struct Rejected {
    pub code: String,
    pub detail: String,
}

impl Rejected {
    pub fn new(code: &str, detail: impl ToString) -> Self {
        Self { code: code.to_string(), detail: detail.to_string() }
    }
}

impl fmt::Display for Rejected {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for Rejected {}

pub type Step = Box<dyn Fn(&Val) -> Result<Val, String> + Send + Sync>;
pub type Steps = BTreeMap<String, Step>;
pub type Row = BTreeMap<String, Val>;
/// Named sets the caller supplies for `in_lookup` checks (an approved scope).
pub type Lookups = BTreeMap<String, BTreeSet<String>>;

/// A record set aside by a check, with the rules file's reason.
#[derive(Clone, Debug, PartialEq)]
pub struct Deferred {
    pub table: String,
    pub ordinal: i64,
    pub reason: String,
    pub raw: Raw,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Reading {
    pub tables: BTreeMap<String, Vec<Row>>,
    pub deferred: Vec<Deferred>,
}

const FORMATS: [&str; 4] = ["xml", "json", "jsonl", "csv"];
const PRIMITIVES: [&str; 15] = ["ordinal", "text", "number", "integer", "date", "const", "steps", "custom", "context", "lookup", "value", "object", "coalesce", "choose", "test"];
const CHECKS: [&str; 7] = ["required", "in_set", "in_lookup", "absent", "count", "before", "lei"];

struct Limits {
    max_bytes: u64,
    max_member_bytes: u64,
    max_records: usize,
}

pub struct Engine {
    read: Value,
    steps: Steps,
    limits: Limits,
}

fn contract_error(detail: impl ToString) -> Rejected {
    Rejected::new("contract", detail)
}

impl Engine {
    pub fn load(contract_yaml: &Path, steps: Steps) -> Result<Self, Rejected> {
        let text = fs::read_to_string(contract_yaml).map_err(contract_error)?;
        Self::from_yaml(&text, steps)
    }

    /// A contract as YAML (or JSON), refused now if anything in it is unknown.
    pub fn from_yaml(text: &str, steps: Steps) -> Result<Self, Rejected> {
        let contract: Value = serde_yaml::from_str(text).map_err(contract_error)?;
        let read = contract.get("read").ok_or_else(|| contract_error("contract has no read"))?.clone();
        validate(&read, &steps).map_err(contract_error)?;
        let limit = |name: &str, default: u64| {
            read.get("limits").and_then(|l| l.get(name)).and_then(Value::as_u64).unwrap_or(default)
        };
        let max_bytes = limit("max_bytes", 512 << 20);
        let limits = Limits {
            max_bytes,
            max_member_bytes: limit("max_member_bytes", max_bytes),
            max_records: limit("max_records", 10_000_000) as usize,
        };
        Ok(Self { read, steps, limits })
    }

    pub fn read(&self, bytes: &[u8], lookups: &Lookups) -> Result<Reading, Rejected> {
        self.read_with_context(bytes, lookups, &Row::new())
    }

    /// Validate caller facts even when a framed source contains no records.
    pub fn validate_context(&self, values: &Row) -> Result<(), Rejected> {
        context::check(&self.read, values)
    }

    /// Caller facts never replace document fields or parsing configuration.
    pub fn read_with_context(&self, bytes: &[u8], lookups: &Lookups, context: &Row) -> Result<Reading, Rejected> {
        context::check(&self.read, context)?;
        if bytes.len() as u64 > self.limits.max_bytes {
            return Err(Rejected::new("limit_exceeded", format!("the artifact is over {} bytes", self.limits.max_bytes)));
        }
        let member;
        let bytes = if setting(&self.read, "container") == Some("zip") {
            member = formats::zip_member(bytes, self.limits.max_member_bytes)?;
            &member[..]
        } else {
            bytes
        };
        let document = self.document(bytes)?;
        self.read_document(&document, lookups, context)
    }

    /// Project a validated framed JSON record through the ordinary configured
    /// interpreter. Input size follows the worker's typed Python JSON policy.
    pub fn read_json_value(&self, value: serde_json::Value, lookups: &Lookups, context: &Row) -> Result<Reading, Rejected> {
        context::check(&self.read, context)?;
        self.validate_json_projection()?;
        if json_sequence::encoded_len(&value, json_sequence::RecordEncoding::Python)? as u64 > self.limits.max_bytes {
            return Err(Rejected::new("limit_exceeded", format!("the artifact is over {} bytes", self.limits.max_bytes)));
        }
        let document = formats::json_value(value, uses_integer(&self.read), uses_python_text(&self.read) || uses_iteration_order(&self.read));
        self.read_document(&document, lookups, context)
    }

    pub(crate) fn validate_json_projection(&self) -> Result<(), Rejected> {
        if setting(&self.read, "format") != Some("json") || self.read.get("container").is_some() {
            return Err(Rejected::new("contract", "framed JSON projection requires json without a container"));
        }
        Ok(())
    }

    fn read_document(&self, document: &El, lookups: &Lookups, context: &Row) -> Result<Reading, Rejected> {
        for assertion in self.read.get("assertions").and_then(Value::as_sequence).into_iter().flatten() {
            match eval(self, context, &document, &document, 1, &assertion["test"])? {
                Val::Bool(true) => {},
                Val::Bool(false) | Val::Null => return Err(Rejected::new("assertion_failed", setting(assertion, "reason").unwrap())),
                _ => return Err(Rejected::new("assertion_condition", "a document assertion must return boolean or null")),
            }
        }
        for path in self.read.get("require").and_then(Value::as_sequence).into_iter().flatten() {
            let path = path.as_str().unwrap_or_default();
            match lookup(&document, path)? {
                Found::Missing => return Err(Rejected::new("missing_required", format!("{path} is missing"))),
                Found::List(_) => return Err(Rejected::new("repeated_path", format!("{path} is repeated"))),
                Found::El(_) | Found::Text(_, _, _) => {}
            }
        }
        let mut reading = Reading::default();
        let tables = self.read.get("tables").and_then(Value::as_mapping).into_iter().flatten();
        for (name, table) in tables {
            let name = name.as_str().unwrap_or_default().to_string();
            let expanded;
            let (items, count) = if table.get("each").is_some_and(|each| each.is_mapping()) {
                let count;
                (expanded, count) = iteration::rows(self, context, &document, &table["each"], self.limits.max_records, context::take(table, context))?;
                (expanded.iter().collect::<Vec<_>>(), count)
            } else {
                let items = items_of(&document, setting(table, "each").unwrap_or("."))?;
                let count = items.len();
                (items, count)
            };
            if count > self.limits.max_records {
                return Err(Rejected::new("limit_exceeded", format!("{name} has more than {} records", self.limits.max_records)));
            }
            self.check_count(&document, &name, count)?;
            let rows = reading.tables.entry(name.clone()).or_default();
            let mut selected = 0;
            for (index, item) in items.into_iter().take(context::take(table, context)).enumerate() {
                if let Some(select) = table.get("select") {
                    match eval(self, context, &document, item, index as i64 + 1, select)? {
                        Val::Bool(true) => {}, Val::Bool(false) | Val::Null => continue,
                        _ => return Err(Rejected::new("select_condition", "Selection must be boolean or null")),
                    }
                }
                selected += 1;
                let column_ordinal = if setting(table, "ordinal") == Some("selected") { selected } else { index as i64 + 1 };
                let mut record = Record { column_ordinal, engine: self, context, document: &document, item, ordinal: index as i64 + 1, table, values: Row::new() };
                if let Some(reason) = record.failed_check(lookups)? {
                    reading.deferred.push(Deferred { table: name.clone(), ordinal: record.ordinal, reason, raw: item.raw() });
                    continue;
                }
                for column in table.get("columns").and_then(Value::as_mapping).into_iter().flatten().map(|(c, _)| c) {
                    record.column(column.as_str().unwrap_or_default())?;
                }
                rows.push(record.values);
            }
        }
        Ok(reading)
    }

    fn document(&self, bytes: &[u8]) -> Result<El, Rejected> {
        let max_records = self.limits.max_records;
        match setting(&self.read, "format").unwrap_or_default() {
            "json" => formats::json(bytes, uses_integer(&self.read), uses_python_text(&self.read) || uses_iteration_order(&self.read)),
            "jsonl" => formats::jsonl(bytes, max_records, uses_integer(&self.read), uses_python_text(&self.read)),
            "csv" => formats::csv(bytes, max_records),
            _ => {
                let parsed = match parse_xml(bytes) {
                    Err(error)
                        if error.code == "malformed"
                            && setting(&self.read, "on_parse_error") == Some("retry_without_control_chars") =>
                    {
                        parse_xml(&strip_control_chars(bytes))
                    }
                    other => other,
                }?;
                if let Some(root) = setting(&self.read, "root") {
                    if parsed.root != root {
                        return Err(Rejected::new("wrong_root", format!("root {} is not {root}", parsed.root)));
                    }
                }
                if let Some(namespace) = setting(&self.read, "namespace") {
                    if parsed.namespace.as_deref() != Some(namespace) {
                        return Err(Rejected::new("wrong_namespace", format!("namespace {:?} is not {namespace}", parsed.namespace)));
                    }
                }
                Ok(parsed.el)
            }
        }
    }

    /// A stated record count must equal the records the table reads.
    fn check_count(&self, document: &El, table: &str, count: usize) -> Result<(), Rejected> {
        let Some(rule) = self.read.get("record_count") else { return Ok(()) };
        if setting(rule, "table") != Some(table) {
            return Ok(());
        }
        let path = setting(rule, "path").unwrap_or_default();
        let stated = match lookup(document, path)? {
            Found::Text(text, _, _) => text.trim().parse::<usize>().ok(),
            _ => None,
        };
        if stated != Some(count) {
            return Err(Rejected::new("record_count", format!("{path} states {stated:?}, the file holds {count}")));
        }
        Ok(())
    }
}

/// Child calls only: literal const/default/reference data is never executable.
pub(crate) fn expression_children(expr: &Value) -> Vec<&Value> {
    let mut children = Vec::new();
    if let Some(key) = expr.get("lookup").and_then(|args| args.get("key")) { children.push(key); }
    if let Some(steps) = expr.get("steps").and_then(Value::as_sequence) { children.extend(steps); }
    if let Some(inputs) = expr.get("custom").and_then(|args| args.get("inputs")).and_then(Value::as_mapping) {
        children.extend(inputs.values());
    }
    if let Some(fields) = expr.get("object").and_then(|args| args.get("fields")).and_then(Value::as_mapping) {
        children.extend(fields.values());
    }
    if let Some(values) = expr.get("coalesce").and_then(|args| args.get("values")).and_then(Value::as_sequence) {
        children.extend(values);
    }
    if let Some(args) = expr.get("choose") {
        for key in ["condition", "then", "else"] {
            if let Some(child) = args.get(key) { children.push(child); }
        }
    }
    children
}

/// Inspect expressions, never literal reference rows or const/default values.
fn uses_feature(read: &Value, predicate: fn(&Value) -> bool) -> bool {
    fn in_expression(expr: &Value, predicate: fn(&Value) -> bool) -> bool {
        predicate(expr) || expression_children(expr).into_iter().any(|child| in_expression(child, predicate))
    }
    read_expressions(read).into_iter().any(|expr| in_expression(expr, predicate))
}

pub(crate) fn assertion_expressions(read: &Value) -> Vec<&Value> {
    read.get("assertions").and_then(Value::as_sequence).into_iter().flatten().filter_map(|a| a.get("test")).collect()
}

fn read_expressions(read: &Value) -> Vec<&Value> {
    let mut result = assertion_expressions(read);
    for table in read.get("tables").and_then(Value::as_mapping).into_iter().flat_map(|tables| tables.values()) {
        result.extend(table_expressions(table));
    }
    result
}

pub(crate) fn table_expressions(table: &Value) -> Vec<&Value> {
    let mut result: Vec<_> = table.get("columns").and_then(Value::as_mapping).into_iter().flat_map(|m| m.values()).collect();
    if let Some(select) = table.get("select") { result.push(select); }
    if let Some(each) = table.get("each") { result.extend(iteration::expressions(each)); }
    result
}

fn uses_iteration_order(read: &Value) -> bool {
    read.get("tables").and_then(Value::as_mapping).into_iter().flat_map(|m| m.values())
        .any(|table| table.get("each").is_some_and(iteration::needs_order))
}

/// The precise numeric path is used only by an opted-in integer expression.
fn uses_integer(read: &Value) -> bool {
    uses_feature(read, |expr| expr.get("integer").is_some() || expr.get("value").is_some())
}

fn setting<'a>(value: &'a Value, name: &str) -> Option<&'a str> {
    value.get(name).and_then(Value::as_str)
}

fn uses_python_text(read: &Value) -> bool {
    uses_feature(read, |expr| ["text", "date"].iter().any(|name| expr.get(*name).is_some_and(|args| setting(args, "coerce") == Some("python"))))
}

fn validate_coerce(args: &Value) -> Result<(), String> {
    if args.get("coerce").is_some_and(|value| !matches!(value.as_str(), Some("scalar" | "python"))) {
        return Err("coerce is scalar or python".into());
    }
    Ok(())
}

/// Everything a contract names must exist now, not partway through a read.
fn validate(read: &Value, steps: &Steps) -> Result<(), String> {
    context::validate(read)?;
    reference::validate(read)?;
    let format = setting(read, "format").ok_or("read.format is missing")?;
    if !FORMATS.contains(&format) {
        return Err(format!("format {format} is not read"));
    }
    if uses_feature(read, |expr| expr.get("value").is_some()) && !matches!(format, "json" | "jsonl") {
        return Err("value requires JSON or JSON Lines".into());
    }
    if uses_python_text(read) && !matches!(format, "json" | "jsonl") {
        return Err("Python text coercion requires JSON or JSON Lines".into());
    }
    for name in ["root", "namespace"] {
        if read.get(name).is_some_and(|value| value.as_str().is_none()) {
            return Err(format!("read.{name} must be text"));
        }
    }
    if let Some(retry) = read.get("on_parse_error") {
        if retry.as_str() != Some("retry_without_control_chars") || format != "xml" {
            return Err("on_parse_error is retry_without_control_chars for XML only".into());
        }
    }
    if let Some(limits) = read.get("limits") {
        let limits = limits.as_mapping().ok_or("read.limits must be a mapping")?;
        for (name, value) in limits {
            if !matches!(name.as_str(), Some("max_bytes" | "max_member_bytes" | "max_records"))
                || !value.as_u64().is_some_and(|n| n > 0 && n <= usize::MAX as u64) {
                return Err("limits name positive integer max_bytes, max_member_bytes or max_records".into());
            }
        }
    }
    if read.get("require").is_some_and(|value| value.as_sequence().is_none()) {
        return Err("read.require must be a list".into());
    }
    if let Some(assertions) = read.get("assertions") {
        let assertions = assertions.as_sequence().filter(|s| s.len() <= 32).ok_or("read.assertions is a list of at most 32 assertions")?;
        for assertion in assertions {
            let args = assertion.as_mapping().filter(|m| m.len() == 2).ok_or("a document assertion names test and reason only")?;
            if args.keys().any(|k| !matches!(k.as_str(), Some("test" | "reason"))) {
                return Err("a document assertion names test and reason only".into());
            }
            if !setting(assertion, "reason").is_some_and(|s| !s.is_empty() && s.len() <= 4096) {
                return Err("an assertion reason is nonempty text of at most 4096 bytes".into());
            }
            validate_expr(assertion.get("test").ok_or("an assertion names no test")?, steps)?;
        }
    }
    if let Some(container) = read.get("container") {
        if container.as_str() != Some("zip") {
            return Err(format!("container {container:?} is not read"));
        }
    }
    for path in read.get("require").and_then(Value::as_sequence).into_iter().flatten() {
        check_path(path.as_str().ok_or("a required path is not a string")?)?;
    }
    if let Some(rule) = read.get("record_count") {
        check_path(setting(rule, "path").ok_or("record_count names no path")?)?;
        setting(rule, "table").ok_or("record_count names no table")?;
    }
    let tables = read.get("tables").and_then(Value::as_mapping).ok_or("read.tables is missing")?;
    if let Some(rule) = read.get("record_count") {
        let name = setting(rule, "table").ok_or("record_count names no table")?;
        if !tables.contains_key(Value::String(name.into())) {
            return Err(format!("record_count names unknown table {name}"));
        }
    }
    for (name, table) in tables {
        if let Some(each) = table.get("each") {
            if each.is_mapping() {
                iteration::validate(each, format, steps, 0)?;
            } else if each.as_str().is_none() {
                return Err("table.each must be text or one iteration call".into());
            }
        }
        if let Some(select) = table.get("select") { validate_expr(select, steps)?; }
        if table.get("ordinal").is_some_and(|v| !matches!(v.as_str(), Some("source" | "selected"))) { return Err("table.ordinal is source or selected".into()); }
        if table.get("checks").is_some_and(|value| value.as_sequence().is_none()) {
            return Err("table.checks must be a list".into());
        }
        if let Some(each) = setting(table, "each") {
            check_path(each)?;
        }
        let name = name.as_str().ok_or("a table name is not a string")?;
        let columns = table.get("columns").and_then(Value::as_mapping).ok_or(format!("{name}: columns are missing"))?;
        for (column, expr) in columns {
            column.as_str().ok_or("a column name is not a string")?;
            validate_expr(expr, steps)?;
        }
        let known = |column: &str| columns.contains_key(Value::String(column.into()));
        for check in table.get("checks").and_then(Value::as_sequence).into_iter().flatten() {
            let kind = setting(check, "check").ok_or("a check has no check")?;
            if !CHECKS.contains(&kind) {
                return Err(format!("check {kind} is not known"));
            }
            if !matches!(setting(check, "on_fail"), Some("defer" | "reject")) {
                return Err(format!("check {kind}: on_fail is defer or reject"));
            }
            if kind != "lei" && setting(check, "reason").is_none() {
                return Err(format!("check {kind} names no reason"));
            }
            if let Some(when) = check.get("when") {
                if setting(when, "column").or(setting(when, "path")).is_none() || when.get("equals").is_none() {
                    return Err(format!("check {kind}: when names a column or path and equals"));
                }
            }
            for path in [Some(check), check.get("when")].into_iter().flatten().filter_map(|c| setting(c, "path")) {
                check_path(path)?;
            }
            let when_column = check.get("when").and_then(|w| setting(w, "column"));
            for column in [setting(check, "column"), setting(check, "until"), when_column].into_iter().flatten() {
                if !known(column) {
                    return Err(format!("check {kind}: {column} is not a column of {name}"));
                }
            }
            let subject = setting(check, "column").or(setting(check, "path"));
            let complete = match kind {
                "in_set" => subject.is_some() && check.get("values").and_then(Value::as_sequence).is_some(),
                "in_lookup" => subject.is_some() && setting(check, "lookup").is_some(),
                "count" => setting(check, "path").is_some() && check.get("equals").and_then(Value::as_u64).is_some(),
                "before" => setting(check, "column").is_some() && setting(check, "until").is_some(),
                _ => subject.is_some(),
            };
            if !complete {
                return Err(format!("check {kind} is missing an argument"));
            }
        }
    }
    Ok(())
}

fn validate_expr(expr: &Value, steps: &Steps) -> Result<(), String> {
    let map = expr.as_mapping().filter(|m| m.len() == 1).ok_or("a column expression must be exactly one call")?;
    let (name, args) = map.iter().next().unwrap();
    let name = name.as_str().ok_or("a primitive name is not a string")?;
    if !PRIMITIVES.contains(&name) {
        return Err(format!("primitive {name} is not known"));
    }
    match name {
        "test" => predicate::validate(args)?,
        "steps" => {
            for step in args.as_sequence().ok_or("steps must be a list")? {
                validate_expr(step, steps)?;
            }
        }
        "custom" => {
            let step = setting(args, "step").ok_or("custom names no step")?;
            if !steps.contains_key(step) {
                return Err(format!("no value step {step}"));
            }
            let inputs = args.get("inputs").and_then(Value::as_mapping);
            if inputs.is_some_and(|i| i.len() != 1) {
                return Err(format!("step {step} is called with one input"));
            }
            for (_, input) in inputs.into_iter().flatten() {
                validate_expr(input, steps)?;
            }
        }
        "text" => {
            validate_coerce(args)?;
            if args.get("case").is_some_and(|v| !matches!(v.as_str(), Some("upper" | "lower" | "preserve"))) {
                return Err("text case is upper, lower or preserve".into());
            }
            check_path(setting(args, "path").ok_or("text names no path")?)?;
            if let Some(values) = args.get("null_if") {
                let values = values.as_sequence().ok_or("text null_if must be a list")?;
                if values.iter().any(|value| value.as_str().is_none()) {
                    return Err("text null_if entries must be strings".into());
                }
            }
            if args.get("trim").is_some_and(|value| value.as_bool().is_none()) {
                return Err("text trim must be a boolean".into());
            }
            if args.get("ignore_case").is_some_and(|value| value.as_bool().is_none()) {
                return Err("text ignore_case must be a boolean".into());
            }
            if args.get("ignore_case").is_some() && args.get("null_if").is_none() {
                return Err("text ignore_case requires null_if".into());
            }
        }
        "coalesce" => {
            let map = args.as_mapping().filter(|m| m.len() == 2).ok_or("coalesce requires values and skip only")?;
            let values = map.get(Value::String("values".into())).and_then(Value::as_sequence)
                .filter(|v| !v.is_empty() && v.len() <= 16).ok_or("coalesce values has 1..16 expressions")?;
            if !matches!(setting(args, "skip"), Some("null" | "falsey")) { return Err("coalesce skip is quoted null or falsey".into()); }
            for value in values { validate_expr(value, steps)?; }
        }
        "choose" => {
            let map = args.as_mapping().filter(|m| m.len() == 3).ok_or("choose requires condition, then and else only")?;
            for key in ["condition", "then", "else"] {
                validate_expr(map.get(Value::String(key.into())).ok_or("choose requires condition, then and else")?, steps)?;
            }
        }
        "object" => {
            let args = args.as_mapping().filter(|m| m.len() == 1).ok_or("object names fields only")?;
            let fields = args.get(Value::String("fields".into())).and_then(Value::as_mapping)
                .filter(|m| m.len() <= 128).ok_or("object fields is a mapping of at most 128 entries")?;
            for (name, expr) in fields {
                if !name.as_str().is_some_and(|name| !name.is_empty() && name.len() <= 128) {
                    return Err("object field names are nonempty text of at most 128 bytes".into());
                }
                validate_expr(expr, steps)?;
            }
        }
        "value" => value::validate(args)?,
        "lookup" => {
            reference::validate_call(args)?;
            validate_expr(&args["key"], steps)?;
        }
        "integer" => {
            check_path(setting(args, "path").ok_or("integer names no path")?)?;
            integer::validate(args)?;
        }
        "number" => check_path(setting(args, "path").ok_or("number names no path")?)?,
        "date" => {
            validate_coerce(args)?;
            check_path(setting(args, "path").ok_or("date names no path")?)?;
            let kind = setting(args, "kind").unwrap_or("instant");
            if !matches!(kind, "instant" | "calendar") || args.get("kind").is_some_and(|v| v.as_str().is_none()) {
                return Err("date kind must be instant or calendar".into());
            }
            if let Some(suffix) = args.get("basic_suffix") {
                if kind != "calendar" || !matches!(suffix.as_str(), Some("reject" | "ignore")) {
                    return Err("date basic_suffix requires calendar and reject or ignore".into());
                }
            }
            if let Some(prefix) = args.get("prefix_length") {
                if kind != "calendar" || !prefix.as_u64().is_some_and(|n| (1..=32).contains(&n)) {
                    return Err("date prefix_length requires calendar and an integer 1..32".into());
                }
            }
            if let Some(policy) = args.get("on_invalid") {
                if kind != "calendar" || !(policy.is_null() || matches!(policy.as_str(), Some("error" | "null"))) {
                    return Err("date on_invalid requires calendar and error or null".into());
                }
            }
        }
        _ => {}
    }
    Ok(())
}

/// One record being read: its columns, worked out once each, when a check or
/// the row first needs them, so checks run in the order the rules file gives.
struct Record<'a> {
    engine: &'a Engine,
    context: &'a Row,
    document: &'a El,
    item: &'a El,
    ordinal: i64,
    column_ordinal: i64,
    table: &'a Value,
    values: Row,
}

impl Record<'_> {
    fn column(&mut self, name: &str) -> Result<Val, Rejected> {
        if let Some(value) = self.values.get(name) {
            return Ok(value.clone());
        }
        let expr = self.table.get("columns").and_then(|c| c.get(name)).ok_or_else(|| contract_error(name))?;
        let value = eval(self.engine, self.context, self.document, self.item, self.column_ordinal, expr)?;
        self.values.insert(name.to_string(), value.clone());
        Ok(value)
    }

    fn subject(&mut self, check: &Value) -> Result<Val, Rejected> {
        if let Some(column) = setting(check, "column") {
            return self.column(column);
        }
        Ok(match lookup(self.item, setting(check, "path").unwrap_or_default())? {
            Found::Text(text, _, _) => Val::Str(text.trim().to_string()),
            Found::Missing => Val::Null,
            Found::El(_) | Found::List(_) => Val::Str(String::new()),
        })
    }

    /// The reason the first failing check gives, if it defers; an error if
    /// it rejects the artifact.
    fn failed_check(&mut self, lookups: &Lookups) -> Result<Option<String>, Rejected> {
        let table = self.table;
        for check in table.get("checks").and_then(Value::as_sequence).into_iter().flatten() {
            if let Some(when) = check.get("when") {
                if as_text(&self.subject(when)?) != as_text(&yaml_val(when.get("equals"))) {
                    continue;
                }
            }
            let kind = setting(check, "check").unwrap_or_default();
            let failure = match kind {
                "lei" => lei_failure(&self.subject(check)?),
                "count" => {
                    let path = setting(check, "path").unwrap_or_default();
                    let found = match lookup(self.item, path)? {
                        Found::Missing => 0,
                        Found::List(rows) => rows.len() as u64,
                        Found::El(_) | Found::Text(_, _, _) => 1,
                    };
                    (Some(found) != check.get("equals").and_then(Value::as_u64)).then_some("")
                }
                "absent" => {
                    let present = match setting(check, "column") {
                        Some(_) => self.subject(check)? != Val::Null,
                        None => !matches!(lookup(self.item, setting(check, "path").unwrap_or_default())?, Found::Missing),
                    };
                    present.then_some("")
                }
                "before" => {
                    let start = self.column(setting(check, "column").unwrap_or_default())?;
                    let until = self.column(setting(check, "until").unwrap_or_default())?;
                    match (start, until) {
                        (Val::Str(a), Val::Str(b)) => (instant(&a)? >= instant(&b)?).then_some(""),
                        _ => None,
                    }
                }
                "required" | "in_set" | "in_lookup" => {
                    let text = as_text(&self.subject(check)?);
                    let held = match kind {
                        "required" => text.is_some(),
                        "in_set" => text.is_some_and(|t| {
                            check
                                .get("values")
                                .and_then(Value::as_sequence)
                                .into_iter()
                                .flatten()
                                .any(|v| as_text(&yaml_val(Some(v))).as_deref() == Some(t.as_str()))
                        }),
                        _ => {
                            let name = setting(check, "lookup").unwrap_or_default();
                            let set = lookups
                                .get(name)
                                .ok_or_else(|| Rejected::new("missing_lookup", format!("the caller gave no {name}")))?;
                            text.is_some_and(|t| set.contains(&t))
                        }
                    };
                    (!held).then_some("")
                }
                other => return Err(contract_error(format!("check {other} is not known"))),
            };
            let Some(own) = failure else { continue };
            let reason = setting(check, "reason").unwrap_or(own).to_string();
            if setting(check, "on_fail") == Some("reject") {
                return Err(Rejected::new("check_failed", format!("record {} of the table: {reason}", self.ordinal)));
            }
            return Ok(Some(reason));
        }
        Ok(None)
    }
}

/// ISO 17442: 18 letters or digits, two check digits, mod 97 equal to 1.
fn lei_failure(value: &Val) -> Option<&'static str> {
    let Val::Str(text) = value else { return Some("invalid_lei") };
    let bytes = text.as_bytes();
    let shaped = bytes.len() == 20
        && bytes[..18].iter().all(|b| b.is_ascii_uppercase() || b.is_ascii_digit())
        && bytes[18..].iter().all(u8::is_ascii_digit);
    if !shaped {
        return Some("invalid_lei");
    }
    let remainder = bytes.iter().fold(0u64, |acc, b| {
        let digits = if b.is_ascii_digit() { u64::from(b - b'0') } else { u64::from(b - b'A' + 10) };
        if digits >= 10 { (acc * 100 + digits) % 97 } else { (acc * 10 + digits) % 97 }
    });
    (remainder != 1).then_some("invalid_lei_checksum")
}

fn instant(text: &str) -> Result<DateTime<Utc>, Rejected> {
    DateTime::parse_from_rfc3339(text.trim())
        .map(|t| t.with_timezone(&Utc))
        .map_err(|e| Rejected::new("invalid_value", format!("{text} is not a date with a time zone: {e}")))
}

/// ISO calendar dates accepted by Python date.fromisoformat, including
/// basic and week dates. No whitespace trimming or timezone interpretation.
fn calendar_date(text: &str, args: &Value) -> Result<Val, Rejected> {
    let prefix = args.get("prefix_length").and_then(Value::as_u64);
    let text: String = match prefix {
        Some(count) => text.chars().take(count as usize).collect(),
        None => text.to_string(),
    };
    // Python 3.12 accepts a ten-character input with an eight-character
    // basic calendar/week date followed by two ignored characters. This
    // compatibility exception must be declared; strict ISO is the default.
    let text = if setting(args, "basic_suffix") == Some("ignore") && text.is_ascii() && text.len() == 10 {
        let basic: String = text.chars().take(8).collect();
        let bytes = basic.as_bytes();
        if bytes.len() == 8 && (bytes.iter().all(u8::is_ascii_digit)
            || (bytes[4] == b'W' && bytes.iter().enumerate().all(|(i, b)| i == 4 || b.is_ascii_digit()))) {
            basic
        } else { text }
    } else { text };
    let shaped = match text.as_bytes() {
        bytes if bytes.len() == 10 && bytes[4] == b'-' && bytes[7] == b'-'
            && bytes.iter().enumerate().all(|(i, b)| i == 4 || i == 7 || b.is_ascii_digit()) => Some("%Y-%m-%d"),
        bytes if bytes.len() == 8 && bytes.iter().all(u8::is_ascii_digit) => Some("%Y%m%d"),
        bytes if bytes.len() == 10 && bytes[4..6] == *b"-W" && bytes[8] == b'-'
            && bytes.iter().enumerate().all(|(i, b)| (4..=5).contains(&i) || i == 8 || b.is_ascii_digit()) => Some("%G-W%V-%u"),
        bytes if bytes.len() == 8 && bytes[4] == b'W'
            && bytes.iter().enumerate().all(|(i, b)| i == 4 || b.is_ascii_digit()) => Some("%GW%V%u"),
        _ => None,
    };
    let parsed = if let Some(format) = shaped {
        NaiveDate::parse_from_str(&text, format).ok()
    } else if text.len() == 8 && text.as_bytes()[4..6] == *b"-W"
        && text.bytes().enumerate().all(|(i, b)| (4..=5).contains(&i) || b.is_ascii_digit()) {
        NaiveDate::parse_from_str(&format!("{text}-1"), "%G-W%V-%u").ok()
    } else if text.len() == 7 && text.as_bytes()[4] == b'W'
        && text.bytes().enumerate().all(|(i, b)| i == 4 || b.is_ascii_digit()) {
        NaiveDate::parse_from_str(&format!("{text}1"), "%GW%V%u").ok()
    } else {
        None
    };
    match parsed.filter(|date| chrono::Datelike::year(date) >= 1 && chrono::Datelike::year(date) <= 9999) {
        Some(date) => Ok(Val::Str(date.format("%Y-%m-%d").to_string())),
        None if args.get("on_invalid").is_some_and(|v| v.is_null() || v.as_str() == Some("null")) => Ok(Val::Null),
        None => Err(Rejected::new("invalid_value", "not an ISO calendar date")),
    }
}

/// A value as text, for comparing it with the text a rules file lists: a
/// whole number reads `1`, not `1.0`; null and an empty string are no value.
fn as_text(value: &Val) -> Option<String> {
    match value {
        Val::Null => None,
        Val::Str(text) if text.is_empty() => None,
        Val::Str(text) => Some(text.clone()),
        Val::Int(i) => Some(i.to_string()),
        Val::UInt(i) => Some(i.to_string()),
        Val::List(_) | Val::Map(_) => None,
        Val::Bool(b) => Some(b.to_string()),
        Val::Float(f) if f.fract() == 0.0 && f.abs() < 1e15 => Some(format!("{}", *f as i64)),
        Val::Float(f) => Some(f.to_string()),
    }
}

fn items_of<'a>(document: &'a El, each: &str) -> Result<Vec<&'a El>, Rejected> {
    if each == "." {
        return Ok(vec![document]);
    }
    match lookup(document, each)? {
        Found::El(el) => Ok(vec![el]),
        Found::List(rows) => Ok(rows),
        Found::Missing => Ok(Vec::new()),
        Found::Text(_, _, _) => Err(Rejected::new("invalid_path", format!("each {each} landed on text"))),
    }
}

enum Found<'a> {
    Missing,
    El(&'a El),
    List(Vec<&'a El>),
    Text(String, ScalarKind, Option<&'a str>),
}

fn lookup<'a>(start: &'a El, path: &str) -> Result<Found<'a>, Rejected> {
    lookup_value(start, path, false)
}

/// Existing text readers treat an empty array as absent. Integer conversion
/// retains it as a structured value so its explicit invalid policy applies.
fn lookup_value<'a>(start: &'a El, path: &str, keep_empty_arrays: bool) -> Result<Found<'a>, Rejected> {
    lookup_inner(start, path, keep_empty_arrays, false)
}

fn lookup_shape<'a>(start: &'a El, path: &str) -> Result<Found<'a>, Rejected> {
    lookup_inner(start, path, true, true)
}

fn lookup_inner<'a>(start: &'a El, path: &str, keep_empty_arrays: bool, keep_null: bool) -> Result<Found<'a>, Rejected> {
    if path == "." {
        return Ok(Found::El(start));
    }
    let mut current = Found::El(start);
    for (index, segment) in segments(path).iter().enumerate() {
        let (key, filter) = match segment.split_once('[') {
            Some((key, rest)) => (key, rest.strip_suffix(']').and_then(|f| f.split_once('='))),
            None => (segment.as_str(), None),
        };
        current = match current {
            Found::List(_) => {
                return Err(Rejected::new(
                    "repeated_path",
                    format!("path {path} crosses a repeating group at segment {index}; use each"),
                ));
            }
            Found::Missing => Found::Missing,
            Found::Text(_, _, _) if key == "$" => current,
            Found::Text(_, _, _) => Found::Missing,
            Found::El(el) if key == "$" => el.text.clone().map_or(Found::Missing, |text| Found::Text(text, el.kind, el.exact_number.as_deref())),
            Found::El(el) if key.starts_with('@') => el.attrs.get(key).cloned().map_or(Found::Missing, |text| Found::Text(text, ScalarKind::Text, None)),
            Found::El(el) => {
                let rows: Vec<&El> = match el.children.get(key) {
                    None => Vec::new(),
                    Some(Child::One(child)) => vec![child],
                    Some(Child::Many(rows)) => rows.iter().collect(),
                };
                let rows = match filter {
                    // `Name[sub.path=VALUE]` keeps the ones whose value matches.
                    Some((sub, wanted)) => {
                        let mut kept = Vec::new();
                        for row in rows {
                            if matches!(lookup(row, sub)?, Found::Text(text, _, _) if text.trim() == wanted) {
                                kept.push(row);
                            }
                        }
                        kept
                    }
                    None => rows,
                };
                match (rows.len(), el.children.get(key), filter) {
                    (0, Some(Child::Many(_)), None) if keep_empty_arrays => Found::List(rows),
                    (0, _, _) => Found::Missing,
                    (_, Some(Child::Many(_)), None) => Found::List(rows),
                    (1, _, _) => Found::El(rows[0]),
                    _ => Found::List(rows),
                }
            }
        };
    }
    // A JSON scalar or a CSV cell is its value.
    Ok(match current {
        Found::El(el) if el.scalar && !(keep_null && el.text.is_none()) => el.text.clone().map_or(Found::Missing, |text| Found::Text(text, el.kind, el.exact_number.as_deref())),
        other => other,
    })
}

/// A path is dot-separated names; a name may carry one `[sub.path=VALUE]`
/// filter. Anything else is refused when the contract loads.
fn check_path(path: &str) -> Result<(), String> {
    if path == "." { return Ok(()) }
    for segment in segments(path) {
        let Some((name, rest)) = segment.split_once('[') else {
            if segment.is_empty() || segment.contains(']') {
                return Err(format!("path {path} has an empty or broken segment"));
            }
            continue;
        };
        let filter = rest.strip_suffix(']').and_then(|f| f.split_once('='));
        match filter {
            Some((sub, value)) if !name.is_empty() && !sub.is_empty() && !value.contains(['[', ']']) => check_path(sub)?,
            _ => return Err(format!("path {path}: a filter is written name[sub.path=VALUE]")),
        }
    }
    Ok(())
}

/// A path's segments, split on dots outside a `[filter]`.
fn segments(path: &str) -> Vec<String> {
    let mut out = vec![String::new()];
    let mut depth = 0;
    for c in path.chars() {
        match c {
            '[' => depth += 1,
            ']' => depth -= 1,
            '.' if depth == 0 => {
                out.push(String::new());
                continue;
            }
            _ => {}
        }
        out.last_mut().unwrap().push(c);
    }
    out
}

fn falsey(value: &Val) -> bool {
    match value {
        Val::Null => true,
        Val::Bool(v) => !v,
        Val::Int(v) => *v == 0,
        Val::UInt(v) => *v == 0,
        Val::Float(v) => *v == 0.0,
        Val::Str(v) => v.is_empty(),
        Val::List(v) => v.is_empty(),
        Val::Map(v) => v.is_empty(),
    }
}

fn eval(engine: &Engine, context: &Row, document: &El, item: &El, ordinal: i64, expr: &Value) -> Result<Val, Rejected> {
    let (name, args) = expr.as_mapping().and_then(|m| m.iter().next()).ok_or_else(|| contract_error("expression"))?;
    match name.as_str().unwrap_or_default() {
        "ordinal" => Ok(Val::Int(ordinal)),
        "test" => predicate::read(if setting(args, "from") == Some("document") { document } else { item }, args),
        "context" => Ok(context.get(setting(args, "name").unwrap()).unwrap().clone()),
        "const" => Ok(yaml_val(args.get("value"))),
        "text" => {
            let trim = args.get("trim").and_then(Value::as_bool).unwrap_or(true);
            let value = match text_at(scope(document, item, args), args)? {
                Some(text) => Val::Str(if trim { text.trim().to_string() } else { text }),
                None => yaml_val(args.get("default")),
            };
            let value = match value {
                Val::Str(text) => Val::Str(match setting(args, "case").unwrap_or("preserve") {
                    "upper" => text.to_uppercase(), "lower" => text.to_lowercase(), _ => text,
                }),
                other => other,
            };
            let Val::Str(text) = &value else { return Ok(value) };
            let Some(null_if) = args.get("null_if").and_then(Value::as_sequence) else { return Ok(value) };
            let text = if trim { text.trim() } else { text.as_str() };
            let ignore_case = args.get("ignore_case").and_then(Value::as_bool).unwrap_or(false);
            let matches = null_if.iter().filter_map(Value::as_str).any(|token| {
                let token = if trim { token.trim() } else { token };
                if ignore_case { text.eq_ignore_ascii_case(token) } else { text == token }
            });
            Ok(if matches { Val::Null } else { Val::Str(text.to_string()) })
        }
        "coalesce" => {
            for expr in args["values"].as_sequence().unwrap() {
                let value = eval(engine, context, document, item, ordinal, expr)?;
                let skipped = if setting(args, "skip") == Some("null") { matches!(value, Val::Null) } else { falsey(&value) };
                if !skipped { return Ok(value); }
            }
            Ok(Val::Null)
        }
        "choose" => {
            let branch = match eval(engine, context, document, item, ordinal, &args["condition"])? {
                Val::Bool(true) => "then",
                Val::Bool(false) | Val::Null => "else",
                _ => return Err(Rejected::new("choose_condition", "choose condition must be boolean or null")),
            };
            eval(engine, context, document, item, ordinal, &args[branch])
        }
        "object" => {
            let mut fields = BTreeMap::new();
            for (name, expr) in args["fields"].as_mapping().unwrap() {
                fields.insert(name.as_str().unwrap().to_string(), eval(engine, context, document, item, ordinal, expr)?);
            }
            Ok(Val::Map(fields))
        }
        "value" => value::read(scope(document, item, args), args),
        "lookup" => {
            let key = eval(engine, context, document, item, ordinal, &args["key"])?;
            reference::read(&engine.read, args, &key)
        }
        "integer" => match lookup_value(scope(document, item, args), setting(args, "path").unwrap_or_default(), true)? {
            Found::Missing => Ok(integer::default(args)),
            Found::Text(text, kind, exact) => integer::read(exact.unwrap_or(&text), kind, args),
            _ => integer::invalid(args),
        },
        "number" => {
            let default = yaml_val(args.get("default"));
            Ok(match text_at(scope(document, item, args), args)? {
                Some(text) if !text.trim().is_empty() => text.trim().parse::<f64>().map(Val::Float).unwrap_or(default),
                _ => default,
            })
        }
        "date" if setting(args, "kind") == Some("calendar") => match text_at(scope(document, item, args), args)? {
            Some(text) if !text.is_empty() => calendar_date(&text, args),
            _ => Ok(yaml_val(args.get("default"))),
        },
        "date" => match text_at(scope(document, item, args), args)? {
            Some(text) if !text.trim().is_empty() => {
                {
                // As Python's `isoformat`: seconds, or six fractional digits.
                let at = instant(&text)?;
                let digits = if at.timestamp_subsec_nanos() == 0 { SecondsFormat::Secs } else { SecondsFormat::Micros };
                Ok(Val::Str(at.to_rfc3339_opts(digits, false)))
            }
            }
            _ => Ok(yaml_val(args.get("default"))),
        },
        "steps" => {
            let mut value = Val::Null;
            for step in args.as_sequence().into_iter().flatten() {
                value = eval(engine, context, document, item, ordinal, step)?;
            }
            Ok(value)
        }
        "custom" => {
            let step = setting(args, "step").unwrap_or_default();
            let function = engine.steps.get(step).ok_or_else(|| contract_error(format!("no value step {step}")))?;
            let mut input = Val::Null;
            for (_, expr) in args.get("inputs").and_then(Value::as_mapping).into_iter().flatten() {
                input = eval(engine, context, document, item, ordinal, expr)?;
            }
            function(&input).map_err(|e| Rejected::new("step_failed", format!("step {step}: {e}")))
        }
        other => Err(contract_error(format!("primitive {other} is not known"))),
    }
}

fn scope<'a>(document: &'a El, item: &'a El, args: &Value) -> &'a El {
    if setting(args, "from") == Some("document") { document } else { item }
}

fn text_at(start: &El, args: &Value) -> Result<Option<String>, Rejected> {
    let path = setting(args, "path").unwrap_or_default();
    if setting(args, "coerce") == Some("python") {
        return match lookup_value(start, path, true)? {
            Found::Missing => Ok(None),
            Found::Text(text, kind, exact) => json_text::scalar(&text, kind, exact).map(Some),
            Found::El(el) => json_text::value(el),
            Found::List(rows) => json_text::list(rows).map(Some),
        };
    }
    match lookup(start, path)? {
        Found::Missing => Ok(None),
        Found::Text(text, _, _) => Ok(Some(text)),
        Found::El(_) | Found::List(_) => Err(Rejected::new("invalid_path", format!("path {path} does not end at a value"))),
    }
}

fn yaml_val(value: Option<&Value>) -> Val {
    match value {
        None | Some(Value::Null) => Val::Null,
        Some(Value::Bool(b)) => Val::Str(b.to_string()),
        Some(Value::Number(number)) => number
            .as_i64()
            .map(Val::Int)
            .or_else(|| number.as_f64().map(Val::Float))
            .unwrap_or(Val::Null),
        Some(Value::String(text)) => Val::Str(text.clone()),
        Some(_) => Val::Null,
    }
}
