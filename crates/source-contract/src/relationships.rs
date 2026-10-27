//! Prepare relationship history from explicit records and configured types.
//! Every database uses this calculation; this module performs no storage access.

use crate::record_values::{self as values, Document, Object};
use indexmap::IndexMap;
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};

const FIRST_TIME: i64 = -62_135_596_800_000_000;
const LAST_TIME: i64 = 253_402_300_799_999_999;
const IDENTITY: &[&str] = &["type", "source_id", "target_id", "scope", "capacity"];
const NOT_PERIOD: &[&str] = &[
    "type",
    "source_id",
    "target_id",
    "scope",
    "capacity",
    "source_subject",
    "target_subject",
    "relationship_id",
    "derived",
    "periods",
    "evidence",
    "last_seen",
    "on",
    "basis",
    "held",
    "title",
];

#[derive(Deserialize)]
struct Command {
    claims: BTreeMap<String, Object>,
    bindings: BTreeMap<String, String>,
    canonical: BTreeMap<String, String>,
    records: BTreeMap<String, Object>,
    types: IndexMap<String, Object>,
    stored: BTreeMap<String, Object>,
    as_of: String,
    clock: String,
    kinds: BTreeSet<String>,
}

#[derive(Clone)]
struct Relationship {
    body: Object,
    periods: Vec<Object>,
    evidence: Vec<Object>,
    sightings: Option<Vec<Object>>,
}

#[derive(Clone)]
struct LinkPeriod {
    key: String,
    source: String,
    target: String,
    start: i64,
    stop: i64,
    body: Object,
}

fn at(body: &Object, field: &str, otherwise: i64) -> Result<i64, String> {
    if !values::has_value(body, field) {
        return Ok(otherwise);
    }
    Ok(values::read_time(&values::read_text(body, field)?)?.timestamp_micros())
}

fn interval(body: &Object) -> Result<(i64, i64), String> {
    Ok((
        at(body, "valid_from", FIRST_TIME)?,
        at(body, "valid_to", LAST_TIME)?,
    ))
}

fn default_text(body: &Object, field: &str, default: &str) -> Result<String, String> {
    if body.contains_key(field) {
        values::read_text(body, field)
    } else {
        Ok(default.into())
    }
}

fn add_review(reviews: &mut Vec<Object>, reason: &str, context: Object) -> Result<(), String> {
    let mut body = Object::from([("reason".into(), values::write_value(&reason)?)]);
    body.extend(context);
    let raw = values::write_value(&body)?;
    for prior in reviews.iter() {
        if values::values_match(&raw, &values::write_value(prior)?)? {
            return Ok(());
        }
    }
    reviews.push(body);
    Ok(())
}

fn keep_earlier_start(
    periods: &mut [Object],
    period: &Object,
    any_basis: bool,
) -> Result<bool, String> {
    let keep = |name: &str| name != "valid_from" && (!any_basis || name != "valid_from_basis");
    let rest: Object = period
        .iter()
        .filter(|(key, _)| keep(key))
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect();
    for stored in periods {
        if !any_basis
            && values::read_text(stored, "valid_from_basis")
                .ok()
                .as_deref()
                != Some("observed")
        {
            continue;
        }
        let other: Object = stored
            .iter()
            .filter(|(key, _)| keep(key))
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect();
        if !values::values_match(&values::write_value(&rest)?, &values::write_value(&other)?)? {
            continue;
        }
        if at(period, "valid_from", FIRST_TIME)? < at(stored, "valid_from", FIRST_TIME)? {
            for key in if any_basis {
                vec!["valid_from", "valid_from_basis"]
            } else {
                vec!["valid_from"]
            } {
                if let Some(value) = period.get(key) {
                    stored.insert(key.into(), value.clone());
                }
            }
        }
        return Ok(true);
    }
    Ok(false)
}

fn read_sighting_order(raw: &Document) -> Result<(u8, usize, String), String> {
    if raw.get().starts_with('"') {
        return Ok((2, 0, values::read_value(raw)?));
    }
    let text = match raw.get() {
        "true" => "1",
        "false" => "0",
        text => text,
    };
    let digits = text.strip_prefix('-').unwrap_or(text);
    if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("Observation identity must be text or an integer".into());
    }
    if text.starts_with('-') {
        let reversed = digits
            .bytes()
            .map(|byte| char::from(b'9' - (byte - b'0')))
            .collect();
        Ok((0, usize::MAX - digits.len(), reversed))
    } else {
        Ok((1, digits.len(), digits.into()))
    }
}

fn combine_periods(sightings: Vec<Object>) -> Result<(Vec<Object>, Vec<Object>), String> {
    let mut stated_times = BTreeSet::new();
    let mut ordered = Vec::new();
    for sighting in sightings {
        let time = at(&sighting, "on", FIRST_TIME)?;
        if values::read_text(&sighting, "basis")? == "stated" {
            stated_times.insert(time);
        }
        ordered.push((
            time,
            !values::has_value(&sighting, "held"),
            read_sighting_order(
                sighting
                    .get("assertion_id")
                    .ok_or("Missing observation identity")?,
            )?,
            sighting,
        ));
    }
    ordered.sort_by(|a, b| (&a.0, &a.1, &a.2).cmp(&(&b.0, &b.1, &b.2)));
    let mut periods: Vec<Object> = Vec::new();
    let mut contradictions = Vec::new();
    let mut current: Option<Object> = None;
    let mut stated_end: Option<Document> = None;
    for (time, dropped, _, sighting) in ordered {
        let basis = values::read_text(&sighting, "basis")?;
        if basis == "observed" && stated_times.contains(&time) {
            continue;
        }
        if dropped {
            if let Some(mut period) = current.take() {
                if time > at(&period, "valid_from", FIRST_TIME)? {
                    period.insert(
                        "valid_to".into(),
                        values::read_optional_value(&sighting, "on")?,
                    );
                    period.insert("valid_to_basis".into(), values::write_value(&basis)?);
                    periods.push(period);
                }
            } else if basis == "stated"
                && periods.last().is_some_and(|period| {
                    values::read_text(period, "valid_to_basis").ok().as_deref() == Some("observed")
                })
            {
                let last = periods.last_mut().ok_or("Missing relationship period")?;
                last.insert(
                    "valid_to".into(),
                    values::read_optional_value(&sighting, "on")?,
                );
                last.insert("valid_to_basis".into(), values::write_value(&"stated")?);
            }
            stated_end = if basis == "stated" {
                Some(values::read_optional_value(&sighting, "on")?)
            } else {
                None
            };
            continue;
        }
        if current.is_none() {
            if let Some(end) = &stated_end {
                if basis == "observed" {
                    if time
                        > values::read_time(&values::read_value::<String>(end)?)?.timestamp_micros()
                    {
                        contradictions.push(Object::from([
                            ("stated_end".into(), end.clone()),
                            ("on".into(), values::read_optional_value(&sighting, "on")?),
                            (
                                "assertion_id".into(),
                                values::read_optional_value(&sighting, "assertion_id")?,
                            ),
                            (
                                "subject".into(),
                                values::read_optional_value(&sighting, "subject")?,
                            ),
                        ]));
                    }
                    continue;
                }
            }
            current = Some(Object::from([
                (
                    "valid_from".into(),
                    values::read_optional_value(&sighting, "on")?,
                ),
                ("valid_from_basis".into(), values::write_value(&basis)?),
                ("valid_to".into(), values::write_value(&())?),
                ("valid_to_basis".into(), values::write_value(&())?),
                ("last_observed".into(), values::write_value(&())?),
                ("titles".into(), values::write_value(&Vec::<Object>::new())?),
            ]));
            stated_end = None;
        }
        let period = current
            .as_mut()
            .ok_or("Missing current relationship period")?;
        if basis == "observed" {
            period.insert(
                "last_observed".into(),
                values::read_optional_value(&sighting, "on")?,
            );
        }
        let mut titles: Vec<Object> = values::read_array(period, "titles")?
            .iter()
            .map(|raw| values::read_value(raw))
            .collect::<Result<_, _>>()?;
        if values::has_value(&sighting, "title") {
            let title = values::read_optional_value(&sighting, "title")?;
            let changed = match titles.last() {
                None => true,
                Some(last) => {
                    !values::values_match(&values::read_optional_value(last, "title")?, &title)?
                }
            };
            if changed {
                titles.push(Object::from([
                    ("title".into(), title),
                    ("on".into(), values::read_optional_value(&sighting, "on")?),
                ]));
            }
        }
        period.insert("titles".into(), values::write_value(&titles)?);
    }
    if let Some(period) = current {
        periods.push(period);
    }
    Ok((periods, contradictions))
}

pub fn prepare_relationship_periods(raw: &str) -> Result<String, String> {
    let sightings: Vec<Object> =
        serde_json::from_str(raw).map_err(|_| "Invalid relationship sightings")?;
    serde_json::to_string(&combine_periods(sightings)?)
        .map_err(|_| "Relationship periods cannot be serialized".into())
}

fn finish_at_succession(
    edges: &mut IndexMap<String, Relationship>,
    types: &IndexMap<String, Object>,
    reviews: &mut Vec<Object>,
) -> Result<(), String> {
    let mut ceased: BTreeMap<String, (Object, String, i64)> = BTreeMap::new();
    let mut keys: Vec<_> = edges.keys().cloned().collect();
    keys.sort();
    for key in keys {
        let edge = &edges[&key];
        let kind = values::read_text(&edge.body, "type")?;
        if !types
            .get(&kind)
            .is_some_and(|spec| values::has_value(spec, "ends_parent_links"))
        {
            continue;
        }
        let source = values::read_text(&edge.body, "source_id")?;
        for period in &edge.periods {
            let start = interval(period)?.0;
            if ceased
                .get(&source)
                .is_none_or(|(_, _, prior)| start < *prior)
            {
                ceased.insert(source.clone(), (period.clone(), key.clone(), start));
            }
        }
    }
    let mut empty = Vec::new();
    for (key, edge) in edges.iter_mut() {
        let kind = values::read_text(&edge.body, "type")?;
        if ceased.is_empty()
            || !types
                .get(&kind)
                .is_some_and(|spec| values::has_value(spec, "hierarchy"))
        {
            continue;
        }
        for end in ["source_id", "target_id"] {
            let endpoint = values::read_text(&edge.body, end)?;
            let Some((succession, by, on)) = ceased.get(&endpoint) else {
                continue;
            };
            if end == "target_id" && at(&edge.body, "last_seen", FIRST_TIME)? > *on {
                continue;
            }
            let mut kept = Vec::new();
            for mut period in std::mem::take(&mut edge.periods) {
                let (start, stop) = interval(&period)?;
                if start >= *on {
                    let ends = BTreeSet::from([
                        values::read_text(&edge.body, "source_id")?,
                        values::read_text(&edge.body, "target_id")?,
                    ]);
                    add_review(
                        reviews,
                        "parent_link_after_succession",
                        Object::from([
                            ("relationship_id".into(), values::write_value(key)?),
                            ("successor_link".into(), values::write_value(by)?),
                            ("entities".into(), values::write_value(&ends)?),
                        ]),
                    )?;
                } else {
                    if stop > *on {
                        period.insert(
                            "valid_to".into(),
                            values::read_optional_value(succession, "valid_from")?,
                        );
                        period.insert(
                            "valid_to_basis".into(),
                            succession
                                .get("valid_from_basis")
                                .cloned()
                                .map_or_else(|| values::write_value(&"stated"), Ok)?,
                        );
                        period.insert("ended_by".into(), values::write_value(by)?);
                    }
                    kept.push(period);
                }
            }
            edge.periods = kept;
        }
        if edge.periods.is_empty() {
            empty.push(key.clone());
        }
    }
    for key in empty {
        edges.shift_remove(&key);
    }
    Ok(())
}

/// Prepare direct links and derived history from a complete affected read set.
pub fn prepare_relationships(raw: &str) -> Result<String, String> {
    let command: Command = serde_json::from_str(raw).map_err(|_| "Invalid relationship command")?;
    // The types run only as their one check allows (ticket 132).
    let types = serde_json::to_value(&command.types).map_err(|error| error.to_string())?;
    crate::relationship_types::check(
        types.as_object().ok_or("Invalid relationship command")?,
        Some(&command.kinds),
    )?;
    let mut edges: IndexMap<String, Relationship> = IndexMap::new();
    let mut reviews = Vec::new();
    for (subject, record) in &command.claims {
        for raw in values::read_array(record, "relationships")? {
            let reported: Object = values::read_value(&raw)?;
            let start = if values::has_value(&reported, "source_subject") {
                values::read_text(&reported, "source_subject")?
            } else {
                subject.clone()
            };
            let target = values::read_text(&reported, "target_subject").ok();
            let kind = values::read_text(&reported, "type").ok();
            let context = Object::from([
                (
                    "assertion_id".into(),
                    values::read_optional_value(record, "assertion_id")?,
                ),
                ("relationship".into(), values::write_value(&reported)?),
                ("subject".into(), values::write_value(subject)?),
            ]);
            let Some((kind, spec)) =
                kind.and_then(|kind| command.types.get(&kind).map(|spec| (kind, spec)))
            else {
                add_review(&mut reviews, "unsupported_relationship", context)?;
                continue;
            };
            let capacities: Vec<String> = spec
                .get("capacities")
                .map(|raw| values::read_value(raw))
                .transpose()?
                .unwrap_or_default();
            if !capacities.is_empty()
                && !values::read_text(&reported, "capacity")
                    .is_ok_and(|capacity| capacities.contains(&capacity))
            {
                add_review(&mut reviews, "unsupported_capacity", context)?;
                continue;
            }
            let sighting = values::has_value(&reported, "on");
            if !capacities.is_empty() && !sighting {
                add_review(&mut reviews, "unknown_relationship_start", context)?;
                continue;
            }
            if sighting
                && !default_text(&reported, "basis", "observed")
                    .is_ok_and(|basis| ["observed", "stated"].contains(&basis.as_str()))
            {
                add_review(&mut reviews, "unknown_date_basis", context)?;
                continue;
            }
            let (Some(source), Some(target_id)) = (
                command.bindings.get(&start),
                target
                    .as_ref()
                    .and_then(|target| command.bindings.get(target)),
            ) else {
                let mut missing = Vec::new();
                if !command.bindings.contains_key(&start) {
                    missing.push("source");
                }
                if target
                    .as_ref()
                    .is_none_or(|key| !command.bindings.contains_key(key))
                {
                    missing.push("target");
                }
                let mut context = context;
                context.insert("missing".into(), values::write_value(&missing)?);
                add_review(&mut reviews, "unresolved_endpoint", context)?;
                continue;
            };
            let source_id = command
                .canonical
                .get(source)
                .ok_or("Missing canonical source record")?;
            let target_id = command
                .canonical
                .get(target_id)
                .ok_or("Missing canonical target record")?;
            if source_id == target_id {
                add_review(&mut reviews, "self_relationship", context)?;
                continue;
            }
            let source = command
                .records
                .get(source_id)
                .ok_or("Missing relationship source")?;
            let destination = command
                .records
                .get(target_id)
                .ok_or("Missing relationship target")?;
            let from: Vec<String> = values::read_value(
                spec.get("from")
                    .ok_or("Relationship type needs source kinds")?,
            )?;
            let to: Vec<String> = values::read_value(
                spec.get("to")
                    .ok_or("Relationship type needs target kinds")?,
            )?;
            if !from.contains(&values::read_text(source, "kind")?)
                || !to.contains(&values::read_text(destination, "kind")?)
            {
                add_review(&mut reviews, "incompatible_endpoint", context)?;
                continue;
            }
            let mut missing = Vec::new();
            if values::read_text(source, "status").ok().as_deref() != Some("accepted") {
                missing.push("source");
            }
            if values::read_text(destination, "status").ok().as_deref() != Some("accepted") {
                missing.push("target");
            }
            if !missing.is_empty() {
                let mut context = context;
                context.insert("missing".into(), values::write_value(&missing)?);
                add_review(&mut reviews, "unresolved_endpoint_identity", context)?;
                continue;
            }
            let seen = values::read_object(record, "source_meta")?
                .get("effective_at")
                .cloned();
            let mut period: Object = if sighting {
                Object::from([(
                    "valid_from".into(),
                    values::read_optional_value(&reported, "on")?,
                )])
            } else {
                reported
                    .iter()
                    .filter(|(key, _)| !NOT_PERIOD.contains(&key.as_str()))
                    .map(|(key, value)| (key.clone(), value.clone()))
                    .collect()
            };
            if !sighting {
                let invalid_basis = ["valid_from_basis", "valid_to_basis"].iter().any(|field| {
                    period.get(*field).is_some_and(|raw| {
                        raw.get() != "null"
                            && !values::read_value::<String>(raw)
                                .is_ok_and(|basis| ["observed", "stated"].contains(&basis.as_str()))
                    })
                });
                if invalid_basis {
                    add_review(&mut reviews, "unknown_date_basis", context)?;
                    continue;
                }
                if values::has_value(&period, "valid_from") {
                    if !period.contains_key("valid_from_basis") {
                        period.insert("valid_from_basis".into(), values::write_value(&"stated")?);
                    }
                } else if let Some(seen) = seen.as_ref().filter(|raw| values::has_content(raw)) {
                    period.insert("valid_from".into(), seen.clone());
                    period.insert("valid_from_basis".into(), values::write_value(&"observed")?);
                } else {
                    add_review(&mut reviews, "unknown_relationship_start", context)?;
                    continue;
                }
                if values::has_value(&period, "valid_to") && !period.contains_key("valid_to_basis")
                {
                    period.insert("valid_to_basis".into(), values::write_value(&"stated")?);
                }
                let (lo, hi) = interval(&period)?;
                if lo >= hi {
                    add_review(&mut reviews, "invalid_relationship_interval", context)?;
                    continue;
                }
            }
            let mut eligible = true;
            for (endpoint, field) in [(source, "from_profile"), (destination, "to_profile")] {
                if !values::has_value(spec, field) {
                    continue;
                }
                let role = values::read_text(spec, field)?;
                let bounds = interval(&period)?;
                let mut found = false;
                for raw in values::read_array(endpoint, "profiles")? {
                    let profile: Object = values::read_value(&raw)?;
                    if values::read_text(&profile, "role")? == role {
                        let (lo, hi) = interval(&profile)?;
                        if lo <= bounds.0 && hi >= bounds.1 {
                            found = true;
                            break;
                        }
                    }
                }
                if !found {
                    add_review(&mut reviews, "missing_endpoint_profile", context.clone())?;
                    eligible = false;
                    break;
                }
            }
            if !eligible {
                continue;
            }
            let mut identity = Object::from([
                ("type".into(), values::write_value(&kind)?),
                ("source_id".into(), values::write_value(source_id)?),
                ("target_id".into(), values::write_value(target_id)?),
                (
                    "scope".into(),
                    reported
                        .get("scope")
                        .cloned()
                        .map_or_else(|| values::write_value(&""), Ok)?,
                ),
            ]);
            if values::has_value(&reported, "capacity") {
                identity.insert("capacity".into(), reported["capacity"].clone());
            }
            let identity_values: Vec<_> = IDENTITY
                .iter()
                .filter_map(|field| identity.get(*field).cloned())
                .collect();
            let key = values::calculate_content_hash(&values::write_value(&identity_values)?)?;
            if !edges.contains_key(&key) {
                identity.insert("derived".into(), values::write_value(&false)?);
                identity.insert("relationship_id".into(), values::write_value(&key)?);
                identity.insert("last_seen".into(), values::write_value(&())?);
                edges.insert(
                    key.clone(),
                    Relationship {
                        body: identity,
                        periods: Vec::new(),
                        evidence: Vec::new(),
                        sightings: None,
                    },
                );
            }
            let edge = edges.get_mut(&key).ok_or("Missing prepared relationship")?;
            if sighting {
                edge.sightings
                    .get_or_insert_with(Vec::new)
                    .push(Object::from([
                        ("on".into(), values::read_optional_value(&reported, "on")?),
                        (
                            "basis".into(),
                            values::write_value(&default_text(&reported, "basis", "observed")?)?,
                        ),
                        (
                            "held".into(),
                            reported
                                .get("held")
                                .cloned()
                                .map_or_else(|| values::write_value(&true), Ok)?,
                        ),
                        (
                            "title".into(),
                            values::read_optional_value(&reported, "title")?,
                        ),
                        (
                            "assertion_id".into(),
                            values::read_optional_value(record, "assertion_id")?,
                        ),
                        ("subject".into(), values::write_value(subject)?),
                    ]));
            } else if values::read_text(&period, "valid_from_basis")
                .ok()
                .as_deref()
                == Some("observed")
                || values::has_value(spec, "keeps_start")
            {
                if !keep_earlier_start(
                    &mut edge.periods,
                    &period,
                    values::has_value(spec, "keeps_start"),
                )? {
                    edge.periods.push(period);
                }
            } else {
                let mut exists = false;
                for old in &edge.periods {
                    if values::values_match(
                        &values::write_value(old)?,
                        &values::write_value(&period)?,
                    )? {
                        exists = true;
                        break;
                    }
                }
                if !exists {
                    edge.periods.push(period);
                }
            }
            if let Some(seen) = seen.filter(|raw| values::has_content(raw)) {
                let moment =
                    values::read_time(&values::read_value::<String>(&seen)?)?.timestamp_micros();
                if !values::has_value(&edge.body, "last_seen")
                    || moment > at(&edge.body, "last_seen", FIRST_TIME)?
                {
                    edge.body.insert("last_seen".into(), seen);
                }
            }
            edge.evidence.push(Object::from([
                (
                    "assertion_id".into(),
                    values::read_optional_value(record, "assertion_id")?,
                ),
                ("source_subject".into(), values::write_value(&start)?),
                ("target_subject".into(), values::write_value(&target)?),
            ]));
        }
    }
    let mut empty = Vec::new();
    for (key, edge) in edges.iter_mut() {
        if let Some(sightings) = edge.sightings.take() {
            let (periods, contradictions) = combine_periods(sightings)?;
            edge.periods = periods;
            if let Some(first) = contradictions.first() {
                let mut context = first.clone();
                context.insert("relationship_id".into(), values::write_value(key)?);
                let ends = BTreeSet::from([
                    values::read_text(&edge.body, "source_id")?,
                    values::read_text(&edge.body, "target_id")?,
                ]);
                context.insert("entities".into(), values::write_value(&ends)?);
                add_review(&mut reviews, "contradicts_stated_end", context)?;
            }
            if edge.periods.is_empty() {
                empty.push(key.clone());
            }
        }
    }
    for key in empty {
        edges.shift_remove(&key);
    }
    finish_at_succession(&mut edges, &command.types, &mut reviews)?;
    finish_relationships(edges, &command, reviews)
}

fn derive_current_parents(
    group: &[LinkPeriod],
    invalid: &BTreeSet<String>,
    spec: &Object,
    scope: &Document,
    command: &Command,
) -> Result<Vec<Object>, String> {
    let now = values::read_time(&command.clock)?.timestamp_micros();
    let mut parents = BTreeMap::new();
    for link in group {
        if !invalid.contains(&link.key) && link.start <= now && now < link.stop {
            parents.insert(link.source.clone(), link);
        }
    }
    let mut result = Vec::new();
    for source in parents.keys() {
        let mut path = Vec::new();
        let mut node = source.clone();
        let mut seen = BTreeSet::new();
        while let Some(link) = parents.get(&node).filter(|_| !seen.contains(&node)) {
            seen.insert(node.clone());
            path.push(link.key.clone());
            node = link.target.clone();
        }
        if seen.contains(&node)
            || group
                .iter()
                .any(|link| link.source == node && invalid.contains(&link.key))
        {
            continue;
        }
        let mut body = Object::from([
            (
                "type".into(),
                spec.get("ultimate_type")
                    .cloned()
                    .ok_or("An ultimate parent names its ultimate_type")?,
            ),
            ("source_id".into(), values::write_value(source)?),
            ("target_id".into(), values::write_value(&node)?),
            ("scope".into(), scope.clone()),
            ("derived".into(), values::write_value(&true)?),
            (
                "algorithm".into(),
                values::write_value(&"accounting-chain-v1")?,
            ),
            ("as_of".into(), values::write_value(&command.as_of)?),
            ("path".into(), values::write_value(&path)?),
        ]);
        let id = values::calculate_content_hash(&values::write_value(&body)?)?;
        body.insert("relationship_id".into(), values::write_value(&id)?);
        result.push(body);
    }
    Ok(result)
}

fn derive_parent_history(
    group: &[LinkPeriod],
    invalid: &BTreeSet<String>,
    spec: &Object,
    scope: &Document,
) -> Result<Vec<Object>, String> {
    let links: Vec<_> = group
        .iter()
        .filter(|link| !invalid.contains(&link.key))
        .collect();
    let disputed: Vec<_> = group
        .iter()
        .filter(|link| invalid.contains(&link.key))
        .collect();
    let mut dates = IndexMap::new();
    for link in links.iter().chain(disputed.iter()) {
        for (field, time) in [("valid_from", link.start), ("valid_to", link.stop)] {
            if time < LAST_TIME && !dates.contains_key(&time) {
                dates.insert(time, values::read_optional_value(&link.body, field)?);
            }
        }
    }
    let mut cuts: Vec<_> = dates.keys().copied().collect();
    cuts.sort();
    let mut found: BTreeMap<(String, String), Vec<(i64, i64, Vec<String>)>> = BTreeMap::new();
    for (index, start) in cuts.iter().copied().enumerate() {
        let stop = cuts.get(index + 1).copied().unwrap_or(LAST_TIME);
        let mut parents = BTreeMap::new();
        for link in &links {
            if link.start <= start && start < link.stop {
                parents.insert(link.source.clone(), *link);
            }
        }
        for source in parents.keys() {
            let mut path = Vec::new();
            let mut node = source.clone();
            let mut seen = BTreeSet::new();
            while let Some(link) = parents.get(&node).filter(|_| !seen.contains(&node)) {
                seen.insert(node.clone());
                path.push(link.key.clone());
                node = link.target.clone();
            }
            if seen.contains(&node)
                || disputed
                    .iter()
                    .any(|link| link.source == node && link.start <= start && start < link.stop)
            {
                continue;
            }
            let periods = found.entry((source.clone(), node)).or_default();
            if let Some(last) = periods
                .last_mut()
                .filter(|last| last.1 == start && last.2 == path)
            {
                last.1 = stop;
            } else {
                periods.push((start, stop, path));
            }
        }
    }
    let mut result = Vec::new();
    for ((source, target), spans) in found {
        let mut body = Object::from([
            (
                "type".into(),
                spec.get("ultimate_type")
                    .cloned()
                    .ok_or("An ultimate parent names its ultimate_type")?,
            ),
            ("source_id".into(), values::write_value(&source)?),
            ("target_id".into(), values::write_value(&target)?),
            ("scope".into(), scope.clone()),
            ("derived".into(), values::write_value(&true)?),
            (
                "algorithm".into(),
                values::write_value(&"accounting-chain-v2")?,
            ),
        ]);
        let id = values::calculate_content_hash(&values::write_value(&body)?)?;
        body.insert("relationship_id".into(), values::write_value(&id)?);
        let mut periods = Vec::new();
        for (start, stop, path) in spans {
            periods.push(Object::from([
                (
                    "valid_from".into(),
                    dates
                        .get(&start)
                        .ok_or("Missing parent-history start")?
                        .clone(),
                ),
                (
                    "valid_to".into(),
                    dates
                        .get(&stop)
                        .cloned()
                        .map_or_else(|| values::write_value(&()), Ok)?,
                ),
                ("path".into(), values::write_value(&path)?),
            ]));
        }
        body.insert("periods".into(), values::write_value(&periods)?);
        result.push(body);
    }
    Ok(result)
}

fn finish_relationships(
    mut edges: IndexMap<String, Relationship>,
    command: &Command,
    mut reviews: Vec<Object>,
) -> Result<String, String> {
    let mut grouped: IndexMap<(String, String), Vec<LinkPeriod>> = IndexMap::new();
    for (key, edge) in &mut edges {
        let mut periods = Vec::new();
        for period in std::mem::take(&mut edge.periods) {
            periods.push((
                interval(&period)?,
                values::calculate_content_hash(&values::write_value(&period)?)?,
                period,
            ));
        }
        periods.sort_by(|a, b| (&a.0, &a.1).cmp(&(&b.0, &b.1)));
        let kind = values::read_text(&edge.body, "type")?;
        let scope = values::write_sorted_json(&edge.body["scope"])?;
        for ((start, stop), _, body) in periods {
            grouped
                .entry((kind.clone(), scope.clone()))
                .or_default()
                .push(LinkPeriod {
                    key: key.clone(),
                    source: values::read_text(&edge.body, "source_id")?,
                    target: values::read_text(&edge.body, "target_id")?,
                    start,
                    stop,
                    body: body.clone(),
                });
            edge.periods.push(body);
        }
    }
    let mut invalid = BTreeSet::new();
    for ((kind, _), group) in &grouped {
        let spec = command.types.get(kind).cloned().unwrap_or_default();
        if values::has_value(&spec, "one_parent") {
            for (index, link) in group.iter().enumerate() {
                for other in &group[index + 1..] {
                    if link.source == other.source
                        && link.target != other.target
                        && link.start.max(other.start) < link.stop.min(other.stop)
                    {
                        invalid.extend([link.key.clone(), other.key.clone()]);
                        let mut keys = vec![link.key.clone(), other.key.clone()];
                        keys.sort();
                        let ends = BTreeSet::from([
                            link.source.clone(),
                            link.target.clone(),
                            other.target.clone(),
                        ]);
                        add_review(
                            &mut reviews,
                            "conflicting_accounting_parents",
                            Object::from([
                                ("edges".into(), values::write_value(&keys)?),
                                ("entities".into(), values::write_value(&ends)?),
                            ]),
                        )?;
                    }
                }
            }
        }
        if !values::has_value(&spec, "hierarchy") {
            continue;
        }
        let mut adjacency: IndexMap<String, Vec<usize>> = IndexMap::new();
        for (index, link) in group.iter().enumerate() {
            adjacency
                .entry(link.source.clone())
                .or_default()
                .push(index);
        }
        for start in adjacency.keys() {
            let initial = adjacency[start].iter().rev().map(|index| {
                (
                    *index,
                    Vec::<String>::new(),
                    BTreeSet::from([start.clone()]),
                    FIRST_TIME,
                    LAST_TIME,
                )
            });
            let mut work: Vec<_> = initial.collect();
            while let Some((index, mut path, mut seen, start_time, stop_time)) = work.pop() {
                let link = &group[index];
                let lo = start_time.max(link.start);
                let hi = stop_time.min(link.stop);
                if lo >= hi {
                    continue;
                }
                path.push(link.key.clone());
                if link.target == *start {
                    let cycle: BTreeSet<_> = path.into_iter().collect();
                    let mut ends = BTreeSet::new();
                    for key in &cycle {
                        ends.insert(values::read_text(&edges[key].body, "source_id")?);
                        ends.insert(values::read_text(&edges[key].body, "target_id")?);
                    }
                    let scope = edges
                        .get(&link.key)
                        .ok_or("Missing hierarchy relationship")?
                        .body["scope"]
                        .clone();
                    add_review(
                        &mut reviews,
                        "hierarchy_cycle",
                        Object::from([
                            ("type".into(), values::write_value(kind)?),
                            ("scope".into(), scope),
                            ("edges".into(), values::write_value(&cycle)?),
                            ("entities".into(), values::write_value(&ends)?),
                        ]),
                    )?;
                    if values::read_text(&spec, "cycles").ok().as_deref() == Some("invalid") {
                        invalid.extend(cycle);
                    }
                } else if !seen.contains(&link.target) {
                    seen.insert(link.target.clone());
                    if let Some(next) = adjacency.get(&link.target) {
                        for next in next.iter().rev() {
                            work.push((*next, path.clone(), seen.clone(), lo, hi));
                        }
                    }
                }
            }
        }
    }
    let mut result = Vec::new();
    for (key, edge) in &edges {
        if invalid.contains(key) {
            continue;
        }
        let mut evidence = Vec::new();
        for item in &edge.evidence {
            evidence.push((
                values::calculate_content_hash(&values::write_value(item)?)?,
                item,
            ));
        }
        evidence.sort_by(|a, b| a.0.cmp(&b.0));
        let evidence: Vec<_> = evidence.into_iter().map(|(_, body)| body).collect();
        let mut body = edge.body.clone();
        body.insert("periods".into(), values::write_value(&edge.periods)?);
        body.insert("evidence".into(), values::write_value(&evidence)?);
        result.push(body);
    }
    for ((kind, _), group) in &grouped {
        let spec = command.types.get(kind).cloned().unwrap_or_default();
        let scope = &edges
            .get(&group[0].key)
            .ok_or("Missing hierarchy scope")?
            .body["scope"];
        match values::read_text(&spec, "ultimate_parent").ok().as_deref() {
            Some("accounting-chain-v1") => result.extend(derive_current_parents(
                group, &invalid, &spec, scope, command,
            )?),
            Some("accounting-chain-v2") => result.extend(derive_parent_history(
                group, &invalid, &spec, scope,
            )?),
            _ => {}
        }
    }
    for edge in &mut result {
        if !edge.contains_key("periods") {
            continue;
        }
        let key = values::read_text(edge, "relationship_id")?;
        let kind = values::read_text(edge, "type")?;
        let keeps_start = command
            .types
            .get(&kind)
            .is_some_and(|spec| values::has_value(spec, "keeps_start"));
        if let Some(stored) = command.stored.get(&key) {
            let mut periods: Vec<Object> = values::read_value(&edge["periods"])?;
            for raw in values::read_array(stored, "periods")? {
                let period: Object = values::read_value(&raw)?;
                if keeps_start
                    || values::read_text(&period, "valid_from_basis")
                        .ok()
                        .as_deref()
                        == Some("observed")
                {
                    keep_earlier_start(&mut periods, &period, keeps_start)?;
                }
            }
            edge.insert("periods".into(), values::write_value(&periods)?);
        }
    }
    let mut ordered = Vec::new();
    for edge in result {
        ordered.push((values::read_text(&edge, "relationship_id")?, edge));
    }
    ordered.sort_by(|a, b| a.0.cmp(&b.0));
    let result: Vec<_> = ordered.into_iter().map(|(_, body)| body).collect();
    serde_json::to_string(&(result, reviews))
        .map_err(|_| "Relationships cannot be serialized".into())
}
