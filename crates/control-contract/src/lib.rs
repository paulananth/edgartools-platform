//! Workload-independent control calculations. No database or provider dependencies.
pub mod bookkeeping;
#[cfg(feature = "python")]
mod opaque;
pub mod reference;
pub mod silver;
use chrono::{DateTime, SecondsFormat, Utc};
use serde_json::value::{to_raw_value, RawValue};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

type Document = Box<RawValue>;
type Object = BTreeMap<String, Document>;
fn read<T: serde::de::DeserializeOwned>(raw: &RawValue) -> Result<T, String> {
    serde_json::from_str(raw.get()).map_err(|_| "Invalid control value".into())
}
fn write(value: &impl serde::Serialize) -> Result<Document, String> {
    to_raw_value(value).map_err(|_| "Cannot serialize control value".into())
}
fn field<'a>(body: &'a Object, key: &str) -> Result<&'a RawValue, String> {
    body.get(key)
        .map(|v| v.as_ref())
        .ok_or_else(|| format!("Missing control field: {key}"))
}
fn text(body: &Object, key: &str) -> Result<String, String> {
    read(field(body, key)?)
}
fn exact_keys(body: &Object, keys: &[&str]) -> bool {
    body.len() == keys.len() && keys.iter().all(|key| body.contains_key(*key))
}
fn calculate_hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn canonical(raw: &RawValue) -> Result<String, String> {
    match raw.get().as_bytes().first() {
        Some(b'{') => {
            let body: Object = read(raw)?;
            let parts = body
                .iter()
                .map(|(key, value)| Ok(format!("{}:{}", write(key)?.get(), canonical(value)?)))
                .collect::<Result<Vec<_>, String>>()?;
            Ok(format!("{{{}}}", parts.join(",")))
        }
        Some(b'[') => {
            let body: Vec<Document> = read(raw)?;
            let parts = body
                .iter()
                .map(|v| canonical(v))
                .collect::<Result<Vec<_>, _>>()?;
            Ok(format!("[{}]", parts.join(",")))
        }
        Some(b'"') => Ok(write(&read::<String>(raw)?)?.get().to_owned()),
        _ => Ok(raw.get().to_owned()),
    }
}
fn validate_reference(raw: &RawValue) -> Result<(), String> {
    let reference: Object = read(raw)?;
    if !exact_keys(&reference, &["uri", "sha256"])
        || text(&reference, "uri")?.is_empty()
        || !valid_hash(&text(&reference, "sha256")?)
    {
        return Err("A reference requires an exact URI and lowercase SHA-256".into());
    }
    Ok(())
}
fn prepare_event(raw: &RawValue) -> Result<Object, String> {
    let event: Object = read(raw)?;
    if !exact_keys(
        &event,
        &[
            "version",
            "producer",
            "event_key",
            "run_id",
            "source",
            "feed",
            "event_type",
            "occurred_at",
            "scope",
            "evidence",
        ],
    ) || field(&event, "version")?.get() != "1"
    {
        return Err("Unsupported Change Journal envelope".into());
    }
    for key in ["producer", "source", "feed", "event_type"] {
        let label = text(&event, key)?;
        if label.is_empty()
            || label.len() > 256
            || !label.as_bytes()[0].is_ascii_alphanumeric()
            || !label
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_.:/-".contains(&b))
        {
            return Err(format!("Invalid journal {key}"));
        }
    }
    let key = text(&event, "event_key")?;
    if !(1..=2048).contains(&key.chars().count()) {
        return Err("An original event key is required".into());
    }
    let run = text(&event, "run_id")?;
    if uuid::Uuid::parse_str(&run)
        .map_err(|_| "Journal root run_id must be a canonical UUID")?
        .to_string()
        != run
    {
        return Err("Journal root run_id must be a canonical UUID".into());
    }
    let occurred = text(&event, "occurred_at")?;
    let stamp = DateTime::parse_from_rfc3339(&occurred)
        .map_err(|_| "Journal timestamp must have UTC timezone")?;
    if stamp.offset().local_minus_utc() != 0 {
        return Err("Journal timestamp must have UTC timezone".into());
    }
    let scope: Object = read(field(&event, "scope")?)?;
    if scope.len() > 32
        || scope
            .iter()
            .any(|(k, v)| k.is_empty() || read::<String>(v).map_or(true, |s| s.is_empty()))
    {
        return Err("Journal scopes contain identifiers only".into());
    }
    let evidence: Vec<Document> = read(field(&event, "evidence")?)?;
    if !(1..=100).contains(&evidence.len()) {
        return Err("Journal events require bounded evidence references".into());
    }
    for reference in evidence {
        validate_reference(&reference)?;
    }
    let body = canonical(raw)?;
    if body.len() > 1_048_576 {
        return Err("Journal event exceeds its storage bound".into());
    }
    let mut prepared = Object::new();
    for key in [
        "producer",
        "event_key",
        "run_id",
        "source",
        "feed",
        "event_type",
        "occurred_at",
    ] {
        prepared.insert(key.into(), field(&event, key)?.to_owned());
    }
    prepared.insert("body".into(), write(&body)?);
    prepared.insert(
        "canonical_hash".into(),
        write(&calculate_hash(body.as_bytes()))?,
    );
    prepared.insert("key_hash".into(), write(&calculate_hash(key.as_bytes()))?);
    Ok(prepared)
}
/// Canonicalize transport JSON without changing numeric precision or spelling.
pub fn canonicalize(raw: &str) -> Result<String, String> {
    let value: Document = serde_json::from_str(raw).map_err(|_| "Invalid control JSON")?;
    canonical(&value)
}
/// Prepare a journal event once for every database engine.
pub fn prepare_journal_event(raw: &str) -> Result<String, String> {
    let value: Document = serde_json::from_str(raw).map_err(|_| "Invalid event JSON")?;
    Ok(write(&prepare_event(&value)?)?.get().into())
}
/// Construct the same receipt from storage columns on each engine.
pub fn prepare_journal_receipt(raw: &str) -> Result<String, String> {
    let stored: Object = serde_json::from_str(raw).map_err(|_| "Invalid stored event")?;
    let body = text(&stored, "canonical_body")?;
    let event: Document = serde_json::from_str(&body).map_err(|_| "Invalid stored event")?;
    let prepared = prepare_event(&event)?;
    if text(&prepared, "canonical_hash")? != text(&stored, "canonical_hash")?
        || text(&prepared, "body")? != body
    {
        return Err("Journal receipt content or hash mismatch".into());
    }
    let at = if stored.contains_key("recorded_at_epoch") {
        let epoch = text(&stored, "recorded_at_epoch")?;
        let (seconds, fraction) = epoch.split_once('.').unwrap_or((&epoch, ""));
        if seconds.starts_with('-')
            || fraction.len() > 6
            || !fraction.bytes().all(|b| b.is_ascii_digit())
        {
            return Err("Invalid receipt timestamp".into());
        }
        let seconds = seconds
            .parse::<i64>()
            .map_err(|_| "Invalid receipt timestamp")?;
        let nanos = format!("{fraction:0<9}")
            .parse::<u32>()
            .map_err(|_| "Invalid receipt timestamp")?;
        DateTime::<Utc>::from_timestamp(seconds, nanos)
            .ok_or("Invalid receipt timestamp")?
            .fixed_offset()
    } else {
        DateTime::parse_from_rfc3339(&text(&stored, "recorded_at")?)
            .map_err(|_| "Invalid receipt timestamp")?
    };
    let receipt = Object::from([
        ("id".into(), field(&stored, "id")?.to_owned()),
        (
            "canonical_hash".into(),
            field(&stored, "canonical_hash")?.to_owned(),
        ),
        (
            "recorded_at".into(),
            write(
                &at.with_timezone(&Utc)
                    .to_rfc3339_opts(SecondsFormat::Micros, true),
            )?,
        ),
        ("event".into(), event),
    ]);
    Ok(write(&receipt)?.get().into())
}
/// Verify content before independent durable readback by the caller.
pub fn check_journal_receipt(raw: &str, expected: Option<&str>) -> Result<String, String> {
    let receipt: Object =
        serde_json::from_str(raw).map_err(|_| "Malformed Change Journal receipt")?;
    if !exact_keys(&receipt, &["id", "canonical_hash", "recorded_at", "event"]) {
        return Err("Malformed Change Journal receipt".into());
    }
    let event = field(&receipt, "event")?;
    let prepared = prepare_event(event)?;
    if text(&prepared, "canonical_hash")? != text(&receipt, "canonical_hash")?
        || expected.is_some_and(|e| {
            canonicalize(e).map_or(true, |s| s != text(&prepared, "body").unwrap_or_default())
        })
    {
        return Err("Journal receipt content or hash mismatch".into());
    }
    Ok(write(&prepared)?.get().into())
}
pub fn prepare_journal_read(raw: &str) -> Result<String, String> {
    let mut query: Object = serde_json::from_str(raw).map_err(|_| "Invalid journal read")?;
    match text(&query, "operation")?.as_str() {
        "list" => {
            let limit: u64 = read(field(&query, "limit")?)
                .map_err(|_| "Journal inspection requires limit 1..1000 and nonnegative after")?;
            let after: Document = field(&query, "after")?.to_owned();
            if !(1..=1000).contains(&limit)
                || after.get().is_empty()
                || !after.get().bytes().all(|b| b.is_ascii_digit())
            {
                return Err(
                    "Journal inspection requires limit 1..1000 and nonnegative after".into(),
                );
            }
            if let Some(run) = query.get("run_id").filter(|v| v.get() != "null") {
                let normalized = uuid::Uuid::parse_str(&read::<String>(run)?)
                    .map_err(|_| "Invalid journal run identifier")?
                    .to_string();
                query.insert("run_id".into(), write(&normalized)?);
            }
        }
        "found" => {
            text(&query, "producer")?;
            let keys: Vec<Document> = read(field(&query, "keys")?)
                .map_err(|_| "Journal lookup requires at most 10000 text keys")?;
            if keys.len() > 10000 || keys.iter().any(|v| read::<String>(v).is_err()) {
                return Err("Journal lookup requires at most 10000 text keys".into());
            }
        }
        _ => return Err("Invalid journal read operation".into()),
    }
    Ok(write(&query)?.get().into())
}
pub fn confirm_journal_receipt(receipt: &str, stored: &str) -> Result<(), String> {
    if canonicalize(receipt)? != canonicalize(stored)? {
        return Err("Journal durable read-back mismatch".into());
    }
    Ok(())
}
pub fn digest_json(raw: &str) -> Result<String, String> {
    Ok(calculate_hash(canonicalize(raw)?.as_bytes()))
}
pub fn check_reference(raw: &str) -> Result<(), String> {
    let value: Document = serde_json::from_str(raw).map_err(|_| "Invalid reference")?;
    validate_reference(&value)
}
#[cfg(feature = "python")]
mod python {
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;
    #[pyfunction]
    fn canonicalize(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::canonicalize(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn canonicalize_opaque(py: Python<'_>, value: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        super::opaque::canonicalize(py, &value)
    }
    #[pyfunction]
    fn prepare_journal_event(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::prepare_journal_event(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn prepare_journal_receipt(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::prepare_journal_receipt(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction(signature=(raw,expected=None))]
    fn check_journal_receipt(
        py: Python<'_>,
        raw: String,
        expected: Option<String>,
    ) -> PyResult<String> {
        py.allow_threads(|| super::check_journal_receipt(&raw, expected.as_deref()))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn prepare_journal_read(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::prepare_journal_read(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn confirm_journal_receipt(py: Python<'_>, receipt: String, stored: String) -> PyResult<()> {
        py.allow_threads(|| super::confirm_journal_receipt(&receipt, &stored))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn digest_json(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::digest_json(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn check_reference(py: Python<'_>, raw: String) -> PyResult<()> {
        py.allow_threads(|| super::check_reference(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn hash_text(py: Python<'_>, value: String) -> PyResult<String> {
        Ok(py.allow_threads(|| super::calculate_hash(value.as_bytes())))
    }
    #[pymodule]
    fn edgar_control(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(canonicalize, m)?)?;
        m.add_function(wrap_pyfunction!(canonicalize_opaque, m)?)?;
        m.add_function(wrap_pyfunction!(hash_text, m)?)?;
        m.add_function(wrap_pyfunction!(prepare_journal_event, m)?)?;
        m.add_function(wrap_pyfunction!(prepare_journal_receipt, m)?)?;
        m.add_function(wrap_pyfunction!(check_journal_receipt, m)?)?;
        m.add_function(wrap_pyfunction!(prepare_journal_read, m)?)?;
        m.add_function(wrap_pyfunction!(confirm_journal_receipt, m)?)?;
        m.add_function(wrap_pyfunction!(digest_json, m)?)?;
        m.add_function(wrap_pyfunction!(check_reference, m)?)?;
        m.add_function(wrap_pyfunction!(prepare_run_checks, m)?)?;
        m.add_function(wrap_pyfunction!(prepare_run_completion, m)?)?;
        m.add_function(wrap_pyfunction!(prepare_run_resume, m)?)?;
        m.add_function(wrap_pyfunction!(canonicalize_numeric_json, m)?)?;
        m.add_function(wrap_pyfunction!(prepare_reference_context, m)?)?;
        m.add_function(wrap_pyfunction!(prepare_reference_version, m)?)?;
        m.add_function(wrap_pyfunction!(order_reference_rows, m)?)?;
        m.add_function(wrap_pyfunction!(compile_reference_query, m)?)?;
        m.add_function(wrap_pyfunction!(encode_reference_search, m)?)?;
        m.add_function(wrap_pyfunction!(reference_query_matches, m)?)?;
        m.add_function(wrap_pyfunction!(prepare_reference_search, m)?)?;
        m.add_function(wrap_pyfunction!(completion_storage_contract, m)?)?;
        m.add_function(wrap_pyfunction!(select_latest_capture, m)?)?;
        m.add_function(wrap_pyfunction!(select_verified_units, m)?)?;
        Ok(())
    }

    #[pyfunction]
    fn prepare_run_checks(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::bookkeeping::prepare_run_checks(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn prepare_run_completion(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::bookkeeping::prepare_run_completion(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn prepare_run_resume(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::bookkeeping::prepare_run_resume(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn canonicalize_numeric_json(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::silver::canonicalize_numeric_json(&raw)).map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn prepare_reference_context(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::reference::prepare_reference_context(&raw)).map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn prepare_reference_version(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::reference::prepare_reference_version(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn order_reference_rows(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::reference::order_reference_rows(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn compile_reference_query(py: Python<'_>, words: String) -> String {
        py.allow_threads(|| super::reference::compile_reference_query(&words))
    }
    #[pyfunction]
    fn encode_reference_search(py: Python<'_>, label: String) -> String {
        py.allow_threads(|| super::reference::encode_reference_search(&label))
    }
    #[pyfunction]
    fn reference_query_matches(py: Python<'_>, words: String, label: String) -> bool {
        py.allow_threads(|| super::reference::reference_query_matches(&words, &label))
    }
    #[pyfunction]
    fn prepare_reference_search(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::reference::prepare_reference_search(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn completion_storage_contract(py: Python<'_>) -> PyResult<String> {
        py.allow_threads(super::bookkeeping::completion_storage_contract)
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn select_latest_capture(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::bookkeeping::select_latest_capture(&raw))
            .map_err(PyValueError::new_err)
    }
    #[pyfunction]
    fn select_verified_units(py: Python<'_>, raw: String) -> PyResult<String> {
        py.allow_threads(|| super::bookkeeping::select_verified_units(&raw))
            .map_err(PyValueError::new_err)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn canonical_values_keep_numeric_precision_and_spelling() {
        assert_eq!(canonicalize(r#"{"z":9999999999999999999999999999999999999999999999999999999999,"a":[-0.0,1e+100,"café 😀"]}"#).unwrap(),
            r#"{"a":[-0.0,1e+100,"café 😀"],"z":9999999999999999999999999999999999999999999999999999999999}"#);
    }
    #[test]
    fn reference_fields_and_digest_are_exact() {
        assert!(check_reference(r#"{"uri":"s3://invented/object","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}"#).is_ok());
        assert!(check_reference(r#"{"uri":"s3://invented/object","sha256":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}"#).is_err());
        assert_eq!(digest_json("{}").unwrap(), calculate_hash(b"{}"));
    }
    #[test]
    fn query_limits_reject_booleans_and_unbounded_reads() {
        assert!(prepare_journal_read(r#"{"operation":"list","limit":true,"after":0}"#).is_err());
        assert!(prepare_journal_read(r#"{"operation":"list","limit":1,"after":-1}"#).is_err());
        assert!(prepare_journal_read(
            r#"{"operation":"list","limit":1000,"after":99999999999999999999999999999999999999999}"#
        )
        .is_ok());
    }
}
