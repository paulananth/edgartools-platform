//! Prepare current records from retained readings, without database or source policy.
//! Field values stay raw JSON so large integers and decimal text are never rounded.

use chrono::{DateTime, FixedOffset};
use serde::{Deserialize, Serialize};
use serde_json::value::{to_raw_value, RawValue};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

type Document = Box<RawValue>;
type Object = BTreeMap<String, Document>;

#[derive(Deserialize)]
struct Reading {
    assertion_id: String,
    subject: String,
    source_code: String,
    record_key: String,
    publication_key: String,
    revision: Document,
    mapping_version: Option<Document>,
    effective_at: Option<String>,
    kind: String,
    fields: BTreeMap<String, Document>,
    identifiers: Document,
    #[serde(default)]
    details: BTreeMap<String, Document>,
    profiles: Vec<Document>,
    relationships: Document,
}

#[derive(Serialize)]
struct CurrentRecord {
    kind: String,
    fields: BTreeMap<String, Object>,
    identifiers: Document,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    details: BTreeMap<String, Document>,
    profiles: Vec<Document>,
    profile_fields: BTreeMap<String, BTreeMap<String, Object>>,
    relationships: Document,
    assertion_id: String,
    source_meta: Object,
}

fn read_object(raw: &RawValue) -> Result<Object, String> {
    serde_json::from_str(raw.get()).map_err(|_| "Reading requires an object".into())
}

fn read_text(raw: &RawValue) -> Result<String, String> {
    serde_json::from_str(raw.get()).map_err(|_| "Reading requires text".into())
}

fn write_document(value: &impl Serialize) -> Result<Document, String> {
    to_raw_value(value).map_err(|_| "Reading cannot be serialized".into())
}

fn read_time(raw: &str) -> Result<DateTime<FixedOffset>, String> {
    // Stored readings use ISO format; accept its space separator as well.
    let mut normalized = raw.to_owned();
    if normalized.as_bytes().get(10) == Some(&b' ') {
        normalized.replace_range(10..11, "T");
    }
    DateTime::parse_from_rfc3339(&normalized)
        .map_err(|_| "Effective time must include a timezone".into())
}

fn read_revision(raw: &str) -> Result<(usize, &str), String> {
    // Native revisions are nonnegative Python integers, without a width limit.
    if raw.is_empty() || !raw.bytes().all(|c| c.is_ascii_digit()) {
        return Err("Reading revision must be a nonnegative integer".into());
    }
    Ok((raw.len(), raw))
}

fn identify_profile_values(profile: &Object) -> Result<String, String> {
    let mut values: Vec<Option<String>> = Vec::new();
    for name in [
        "role",
        "authority",
        "registration",
        "jurisdiction",
        "valid_from",
    ] {
        values.push(match profile.get(name) {
            None => None,
            Some(value) if value.get() == "null" => None,
            Some(value) => Some(read_text(value)?),
        });
    }
    let bytes = serde_json::to_vec(&values).map_err(|_| "Invalid profile identity")?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

/// Identify one profile using its identifying text, independent of source or record type.
pub fn identify_profile(raw: &str) -> Result<String, String> {
    let value: Object = serde_json::from_str(raw).map_err(|_| "Profile requires an object")?;
    identify_profile_values(&value)
}

fn record_field(item: Document, metadata: &Object) -> Result<Object, String> {
    let mut body = read_object(&item)?;
    body.extend(
        metadata
            .iter()
            .map(|(key, value)| (key.clone(), value.clone())),
    );
    Ok(body)
}

/// Fold source revisions and reread versions once, keeping exact original field values.
pub fn prepare_current_records(
    raw: &str,
    as_of: &str,
    retired: &[String],
) -> Result<String, String> {
    let readings: Vec<Reading> =
        serde_json::from_str(raw).map_err(|_| "Invalid retained readings")?;
    let clock = read_time(as_of)?;
    let retired: BTreeSet<_> = retired.iter().map(String::as_str).collect();
    let mut groups: BTreeMap<String, Vec<Reading>> = BTreeMap::new();
    for reading in readings {
        if retired.contains(reading.source_code.as_str()) {
            continue;
        }
        if let Some(effective) = &reading.effective_at {
            if read_time(effective)? > clock {
                continue;
            }
        }
        read_revision(reading.revision.get())?;
        if let Some(mapping) = &reading.mapping_version {
            read_revision(mapping.get())?;
        }
        groups
            .entry(reading.subject.clone())
            .or_default()
            .push(reading);
    }
    let mut result = BTreeMap::new();
    for (subject, mut versions) in groups {
        versions.sort_by(|a, b| {
            let av = a.revision.get();
            let bv = b.revision.get();
            let am = a.mapping_version.as_ref().map_or("1", |value| value.get());
            let bm = b.mapping_version.as_ref().map_or("1", |value| value.get());
            (
                av.len(),
                av,
                am.len(),
                am,
                &a.publication_key,
                &a.assertion_id,
            )
                .cmp(&(
                    bv.len(),
                    bv,
                    bm.len(),
                    bm,
                    &b.publication_key,
                    &b.assertion_id,
                ))
        });
        let mut fields = BTreeMap::new();
        let mut profile_fields: BTreeMap<String, BTreeMap<String, Object>> = BTreeMap::new();
        let mut seen = BTreeMap::new();
        let mut last = None;
        for reading in versions {
            let version = (
                reading.revision.get().to_owned(),
                reading
                    .mapping_version
                    .as_ref()
                    .map_or("1", |value| value.get())
                    .to_owned(),
            );
            if seen
                .get(&version)
                .is_some_and(|id| id != &reading.assertion_id)
            {
                return Err("Source native revision has contradictory publications".into());
            }
            seen.insert(version, reading.assertion_id.clone());
            let mut metadata = BTreeMap::new();
            metadata.insert(
                "assertion_id".into(),
                write_document(&reading.assertion_id)?,
            );
            metadata.insert("source_code".into(), write_document(&reading.source_code)?);
            metadata.insert("record_key".into(), write_document(&reading.record_key)?);
            metadata.insert(
                "effective_at".into(),
                write_document(&reading.effective_at)?,
            );
            for (name, item) in &reading.fields {
                let body = read_object(item)?;
                let operation = read_text(body.get("op").ok_or("Field operation is missing")?)?;
                match operation.as_str() {
                    "unknown" => {}
                    "retract" => {
                        fields.remove(name);
                    }
                    _ => {
                        fields.insert(name.clone(), record_field(item.clone(), &metadata)?);
                    }
                }
            }
            let mut continuing = BTreeMap::new();
            for raw in &reading.profiles {
                let profile = read_object(raw)?;
                let key = identify_profile_values(&profile)?;
                let mut values = profile_fields.get(&key).cloned().unwrap_or_default();
                let changes = profile
                    .get("fields")
                    .map(|raw| read_object(raw))
                    .transpose()?
                    .unwrap_or_default();
                for (name, raw) in changes {
                    let parsed = serde_json::from_str::<Object>(raw.get()).ok();
                    let item = if parsed.as_ref().is_some_and(|body| body.contains_key("op")) {
                        parsed.unwrap()
                    } else if raw.get() == "null" {
                        BTreeMap::from([("op".into(), write_document(&"unknown")?)])
                    } else {
                        BTreeMap::from([
                            ("op".into(), write_document(&"value")?),
                            ("value".into(), raw),
                        ])
                    };
                    let operation =
                        read_text(item.get("op").ok_or("Profile field operation is missing")?)?;
                    match operation.as_str() {
                        "unknown" => {}
                        "retract" => {
                            values.remove(&name);
                        }
                        "value" | "clear" => {
                            if operation == "value"
                                && item.get("value").is_none_or(|v| v.get() == "null")
                            {
                                return Err("Use unknown for null profile evidence".into());
                            }
                            values.insert(name, record_field(write_document(&item)?, &metadata)?);
                        }
                        _ => return Err("Unknown profile field operation".into()),
                    }
                }
                continuing.insert(key, values);
            }
            profile_fields = continuing;
            let mut source_meta = metadata;
            source_meta.remove("assertion_id");
            last = Some((reading, source_meta));
        }
        let (reading, source_meta) = last.ok_or("Missing retained reading")?;
        result.insert(
            subject,
            CurrentRecord {
                kind: reading.kind,
                fields,
                identifiers: reading.identifiers,
                details: reading.details,
                profiles: reading.profiles,
                profile_fields,
                relationships: reading.relationships,
                assertion_id: reading.assertion_id,
                source_meta,
            },
        );
    }
    serde_json::to_string(&result).map_err(|_| "Current records cannot be serialized".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn profile_identity_uses_plain_text_and_missing_values() {
        let profile = r#"{"role":"adviser","authority":"example","registration":"test"}"#;
        assert_eq!(
            identify_profile(profile).unwrap(),
            format!(
                "{:x}",
                Sha256::digest(br#"["adviser","example","test",null,null]"#)
            )
        );
    }

    #[test]
    fn record_values_and_revisions_keep_arbitrary_integer_precision() {
        let raw = r#"[{"assertion_id":"a","subject":"record","source_code":"example","record_key":"r","publication_key":"p","revision":999999999999999999999999999999999999999,"effective_at":null,"kind":"record","fields":{"amount":{"op":"value","value":999999999999999999999999999999999999999}},"identifiers":{},"profiles":[],"relationships":[]}]"#;
        let output = prepare_current_records(raw, "2026-10-19T00:00:00+00:00", &[]).unwrap();
        assert!(output.contains(r#""value":999999999999999999999999999999999999999"#));
    }
}
