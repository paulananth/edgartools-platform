//! Identifier matching over an explicit indexed read set. No database-specific rules.

use crate::record_tests::{evaluate_record_test, normalize_value};
use crate::record_values::{self as values, Object};
use chrono::{Duration, Utc};
use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
struct Inputs {
    policy: Object,
    assertions: Vec<Object>,
    decisions: Vec<Object>,
    identities: Vec<Object>,
    bound: Vec<String>,
    /// Each stored bound record's master: a re-delivered record's identifiers
    /// are its master's, so a later record in the batch finds them.
    #[serde(default)]
    bound_entities: BTreeMap<String, String>,
    /// The values each bound record's bind withholds (part A2b): never its master's.
    #[serde(default)]
    withheld: BTreeMap<String, Vec<Withheld>>,
    released: BTreeSet<String>,
    normalizers: IndexMap<String, bool>,
}
/// What a matching rule does when a record's values reach no master, or
/// several: read once from the rule, each value checked (`activation.py`
/// holds the same lists).
#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum OnNoMatch {
    Mint,
    Wait,
}
#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
enum OnSeveral {
    #[default]
    Review,
    Merge,
}
/// When a record's values reach two masters and do not merge them: `review`,
/// or `first`, binding to the master this rule's value reaches and
/// withholding the values the other masters hold (part A2b).
#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
enum OnConflict {
    #[default]
    Review,
    First,
}
#[derive(Serialize, Deserialize, Clone, Copy)]
struct Outcomes {
    on_no_match: OnNoMatch,
    #[serde(default)]
    on_several: OnSeveral,
    #[serde(default)]
    on_conflict: OnConflict,
}
use crate::record_values::Withheld;
impl Outcomes {
    fn read(rule: &Object) -> Result<Self, String> {
        let outcome = |name: &str| -> Result<_, String> {
            values::write_value(&if values::has_value(rule, name) {
                read_rule_text(rule, name)?
            } else {
                "review".into()
            })
        };
        let (on_several, on_conflict) = (outcome("on_several")?, outcome("on_conflict")?);
        Ok(Self {
            on_no_match: values::read_value(&values::write_value(&read_rule_text(rule, "on_no_match")?)?)
                .map_err(|_| "A matching rule's on_no_match is mint or wait")?,
            on_several: values::read_value(&on_several)
                .map_err(|_| "A matching rule's on_several is review or merge")?,
            on_conflict: values::read_value(&on_conflict)
                .map_err(|_| "A matching rule's on_conflict is review or first")?,
        })
    }
}

#[derive(Serialize, Deserialize, Clone)]
struct Match {
    rule: Object,
    outcomes: Outcomes,
    namespace: String,
    value: String,
    raw: String,
    /// The record's source issues the namespace (its contract's `sources`),
    /// so the record establishes the value for its master.
    #[serde(default)]
    issued: bool,
}
#[derive(Serialize, Deserialize)]
struct Holder {
    namespace: String,
    value: String,
    records: IndexMap<String, String>,
}
#[derive(Serialize, Deserialize)]
struct Plan {
    records: BTreeMap<String, Object>,
    applicable: BTreeMap<String, Vec<Match>>,
    wanted: BTreeMap<String, BTreeSet<String>>,
    kinds: BTreeSet<String>,
    caller_holders: Vec<Holder>,
}

fn read_rule_text(body: &Object, key: &str) -> Result<String, String> {
    values::read_text(body, key)
}
fn rule_is_approved_for_matching(
    policy: &Object,
    kind: &str,
    rule: &Object,
) -> Result<bool, String> {
    for raw in values::read_array(policy, "automatic_rules")? {
        let Ok(entry) = values::read_value::<Object>(&raw) else {
            continue;
        };
        if read_rule_text(&entry, "kind").ok().as_deref() == Some(kind)
            && read_rule_text(&entry, "verdict").ok().as_deref() == Some("bind")
            && [
                ("family", "family"),
                ("rule_id", "rule_id"),
                ("rule_version", "version"),
            ]
            .iter()
            .all(|(left, right)| {
                entry
                    .get(*left)
                    .zip(rule.get(*right))
                    .is_some_and(|(left, right)| values::values_match(left, right).unwrap_or(false))
            })
        {
            return Ok(true);
        }
    }
    Ok(false)
}

fn read_matching_namespace(rule: &Object) -> Result<String, String> {
    let mut names = BTreeSet::new();
    for raw in values::read_array(rule, "when")? {
        let test: Object = values::read_value(&raw)?;
        if [
            "identifier_match@1",
            "identifier_cardinality@1",
            "kind_equal@1",
        ]
        .contains(&read_rule_text(&test, "primitive")?.as_str())
        {
            names.insert(read_rule_text(
                &values::read_object(&test, "args")?,
                "namespace",
            )?);
        }
    }
    if names.len() != 1 {
        return Err("A matching rule requires one identifier namespace".into());
    }
    names
        .into_iter()
        .next()
        .ok_or("Missing identifier namespace".into())
}

pub(crate) fn prepare_identifier_value(
    contracts: &BTreeMap<String, (String, Object)>,
    namespace: &str,
    raw: &str,
    normalizers: &IndexMap<String, bool>,
) -> Result<String, String> {
    match contracts.get(namespace) {
        Some((name, aliases)) => {
            normalize_value(name, &values::write_value(&raw)?, aliases, normalizers)
        }
        None => Ok(raw.into()),
    }
}

pub(crate) fn prepare_identifier_rules(
    policy: &Object,
) -> Result<BTreeMap<String, (String, Object)>, String> {
    let mut contracts = BTreeMap::new();
    for raw in values::read_object(policy, "kinds")?.values() {
        let block: Object = values::read_value(raw)?;
        let aliases = Object::from([(
            "normalizers".into(),
            values::write_value(&values::read_object(&block, "normalizers")?)?,
        )]);
        for (namespace, raw) in values::read_object(&block, "identifiers")? {
            let contract: Object = values::read_value(&raw)?;
            contracts
                .entry(namespace)
                .or_insert((read_rule_text(&contract, "normalizer")?, aliases.clone()));
        }
    }
    Ok(contracts)
}

pub fn plan_record_matches(raw: &str) -> Result<String, String> {
    let input: Inputs = serde_json::from_str(raw).map_err(|_| "Invalid record matching inputs")?;
    let mut rules = Vec::new();
    let mut issuers: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let contracts = prepare_identifier_rules(&input.policy)?;
    let mut blocks = BTreeMap::new();
    for (kind, raw) in values::read_object(&input.policy, "kinds")? {
        blocks.insert(kind, values::read_value::<Object>(&raw)?);
    }
    for (kind, block) in blocks {
        for (namespace, raw) in values::read_object(&block, "identifiers")? {
            let contract: Object = values::read_value(&raw)?;
            let sources: Vec<String> = values::read_array(&contract, "sources")?
                .iter()
                .map(|raw| values::read_value(raw))
                .collect::<Result<_, _>>()?;
            issuers.entry(namespace).or_default().extend(sources);
        }
        for raw in values::read_array(&block, "rules")? {
            let rule: Object = values::read_value(&raw)?;
            if read_rule_text(&rule, "family")? == "binding"
                && rule_is_approved_for_matching(&input.policy, &kind, &rule)?
            {
                rules.push(rule);
            }
        }
    }
    let mut ordered = Vec::new();
    for record in &input.assertions {
        let revision = values::read_optional_value(record, "revision")?;
        let mapping = record
            .get("mapping_version")
            .cloned()
            .unwrap_or(values::write_value(&1)?);
        if !revision.get().bytes().all(|ch| ch.is_ascii_digit())
            || !mapping.get().bytes().all(|ch| ch.is_ascii_digit())
        {
            return Err("Reading revisions must be nonnegative integers".into());
        }
        ordered.push((
            (
                revision.get().len(),
                revision.get().to_owned(),
                mapping.get().len(),
                mapping.get().to_owned(),
            ),
            record,
        ));
    }
    ordered.sort_by(|(left, _), (right, _)| left.cmp(right));
    let mut records = BTreeMap::new();
    for (_, record) in ordered {
        records.insert(read_rule_text(record, "subject")?, record.clone());
    }
    let mut taken: BTreeSet<_> = input
        .bound
        .into_iter()
        .filter(|subject| !input.released.contains(subject))
        .collect();
    let mut caller = BTreeMap::new();
    for decision in &input.decisions {
        if read_rule_text(decision, "operation")? == "bind" {
            let subject = read_rule_text(decision, "subject")?;
            taken.insert(subject.clone());
            caller.insert(subject, read_rule_text(decision, "entity_id")?);
        }
    }
    for (subject, entity) in &input.bound_entities {
        if !input.released.contains(subject) && !caller.contains_key(subject) {
            caller.insert(subject.clone(), entity.clone());
        }
    }
    let mut applicable: BTreeMap<String, Vec<Match>> = BTreeMap::new();
    let mut wanted: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut kinds = BTreeSet::new();
    for (subject, record) in &records {
        if taken.contains(subject) {
            continue;
        }
        for rule in &rules {
            if read_rule_text(rule, "applies_to_verdict")? != read_rule_text(record, "kind")?
                || (values::has_value(rule, "source")
                    && read_rule_text(rule, "source")? != read_rule_text(record, "source_code")?)
            {
                continue;
            }
            let mut passes = true;
            for raw in values::read_array(rule, "when")? {
                let test: Object = values::read_value(&raw)?;
                let name = read_rule_text(&test, "primitive")?;
                if [
                    "identifier_match@1",
                    "identifier_cardinality@1",
                    "kind_equal@1",
                ]
                .contains(&name.as_str())
                {
                    continue;
                }
                let verdict = evaluate_record_test(
                    &name,
                    &values::read_object(&test, "args")?,
                    record,
                    &Object::new(),
                    &input.normalizers,
                )?;
                if verdict == values::has_value(&test, "negate") {
                    passes = false;
                    break;
                }
            }
            if !passes {
                continue;
            }
            let namespace = read_matching_namespace(rule)?;
            let source = read_rule_text(record, "source_code")?;
            let issued = issuers
                .get(&namespace)
                .is_some_and(|sources| sources.contains(&source));
            // A source that does not issue the identifier may file it as a
            // cross-reference: it finds the master holding it, lookup only,
            // and is never given to it (Design 5, operator 2026-10-26:
            // "Lookup only").
            let identifiers = values::read_object(record, "identifiers")?;
            let cross_references = values::read_object(record, "cross_references")?;
            let Some(raw) = identifiers.get(&namespace).or(if issued {
                None
            } else {
                cross_references.get(&namespace)
            }) else {
                continue;
            };
            let raws = values::read_identifier_values(raw)?;
            if raws.is_empty() {
                continue;
            }
            let outcomes = Outcomes::read(rule)?;
            if outcomes.on_no_match == OnNoMatch::Mint {
                kinds.insert(read_rule_text(record, "kind")?);
            }
            let kept: Object = rule
                .iter()
                .filter(|(key, _)| ["rule_id", "version"].contains(&key.as_str()))
                .map(|(key, value)| (key.clone(), value.clone()))
                .collect();
            for raw in raws {
                let value =
                    prepare_identifier_value(&contracts, &namespace, &raw, &input.normalizers)?;
                wanted
                    .entry(namespace.clone())
                    .or_default()
                    .insert(raw.clone());
                applicable.entry(subject.clone()).or_default().push(Match {
                    rule: kept.clone(),
                    outcomes,
                    namespace: namespace.clone(),
                    value,
                    raw,
                    issued,
                });
            }
        }
    }
    let kinds_by_id: BTreeMap<_, _> = input
        .identities
        .iter()
        .map(|record| {
            Ok((
                read_rule_text(record, "entity_id")?,
                read_rule_text(record, "kind")?,
            ))
        })
        .collect::<Result<_, String>>()?;
    let mut caller_holders = Vec::new();
    for record in &input.assertions {
        let Some(entity) = caller.get(&read_rule_text(record, "subject")?) else {
            continue;
        };
        let source = read_rule_text(record, "source_code")?;
        for (namespace, raw) in values::read_object(record, "identifiers")? {
            if !issuers
                .get(&namespace)
                .is_some_and(|sources| sources.contains(&source))
            {
                continue;
            }
            let subject = read_rule_text(record, "subject")?;
            for raw in values::read_identifier_values(&raw)? {
                let kept_back = Withheld { namespace: namespace.clone(), raw: raw.clone() };
                if input.withheld.get(&subject).is_some_and(|held| held.contains(&kept_back)) {
                    continue;
                }
                // Looked up too: only a value no master holds is new for it.
                wanted
                    .entry(namespace.clone())
                    .or_default()
                    .insert(raw.clone());
                caller_holders.push(Holder {
                    value: prepare_identifier_value(&contracts, &namespace, &raw, &input.normalizers)?,
                    namespace: namespace.clone(),
                    records: IndexMap::from([(
                        entity.clone(),
                        kinds_by_id
                            .get(entity)
                            .cloned()
                            .unwrap_or(read_rule_text(record, "kind")?),
                    )]),
                });
            }
        }
    }
    serde_json::to_string(&Plan {
        records,
        applicable,
        wanted,
        kinds,
        caller_holders,
    })
    .map_err(|_| "Cannot serialize record match plan".into())
}

#[derive(Deserialize)]
struct PreparedInputs {
    plan: Plan,
    found: Vec<Holder>,
    suspended: BTreeSet<String>,
    newest: BTreeMap<String, Option<String>>,
    new_ids: Vec<String>,
    refused: BTreeSet<(String, String, String)>,
    as_of: String,
    /// The stored merges, Match Exclusions and their reversals about the
    /// masters the batch's records reach (part A2a): what a new merge rests
    /// on, and which pairs never merge again.
    #[serde(default)]
    consolidations: Vec<Object>,
}

/// Each master's consolidation component (its live merges, stored and this
/// batch's), and the pairs a steward keeps apart.
struct Consolidations {
    parent: BTreeMap<String, String>,
    merges: BTreeMap<String, Vec<String>>,
    exclusions: Vec<(String, String)>,
}

impl Consolidations {
    fn read(decisions: &[Object]) -> Result<Self, String> {
        let mut targeted: BTreeMap<String, Vec<(String, String)>> = BTreeMap::new();
        for body in decisions {
            let op = read_rule_text(body, "operation")?;
            if op == "reverse" || op == "revoke" {
                targeted
                    .entry(read_rule_text(body, "target")?)
                    .or_default()
                    .push((op, read_rule_text(body, "decision_id")?));
            }
        }
        let revoked = |id: &str| targeted.get(id).is_some_and(|by| !by.is_empty());
        let mut found = Self { parent: BTreeMap::new(), merges: BTreeMap::new(), exclusions: Vec::new() };
        for body in decisions {
            let op = read_rule_text(body, "operation")?;
            let id = read_rule_text(body, "decision_id")?;
            if op == "merge" {
                let pair = (read_rule_text(body, "left")?, read_rule_text(body, "right")?);
                if !revoked(&id) {
                    found.join(&pair.0, &pair.1, id);
                } else if targeted[&id]
                    .iter()
                    .any(|(by, reversal)| by == "reverse" && !revoked(reversal))
                {
                    // A reversed merge keeps its pair apart (replay's rule).
                    found.exclusions.push(pair);
                }
            } else if op == "exclude" && !revoked(&id) {
                found.exclusions.push((read_rule_text(body, "left")?, read_rule_text(body, "right")?));
            }
        }
        Ok(found)
    }
    fn root(&self, key: &str) -> String {
        let mut key = key.to_owned();
        while let Some(next) = self.parent.get(&key).filter(|next| **next != key) {
            key = next.clone();
        }
        key
    }
    fn join(&mut self, left: &str, right: &str, merge: String) {
        let (left, right) = (self.root(left), self.root(right));
        let mut ids = self.merges.remove(&left).unwrap_or_default();
        if left != right {
            ids.extend(self.merges.remove(&right).unwrap_or_default());
            self.parent.insert(right, left.clone());
        }
        ids.push(merge);
        self.merges.insert(left, ids);
    }
    /// Every live merge a merge of these two components must name.
    fn depends(&self, left: &str, right: &str) -> Vec<String> {
        let mut ids: BTreeSet<String> = BTreeSet::new();
        for key in [left, right] {
            ids.extend(self.merges.get(&self.root(key)).into_iter().flatten().cloned());
        }
        ids.into_iter().collect()
    }
    fn excluded(&self, entities: &[String]) -> bool {
        let roots: Vec<String> = entities.iter().map(|e| self.root(e)).collect();
        self.exclusions.iter().any(|(left, right)| {
            let (left, right) = (self.root(left), self.root(right));
            left != right && roots.contains(&left) && roots.contains(&right)
        })
    }
}

fn prepare_decision_time(raw: &str) -> Result<String, String> {
    let time = values::read_time(raw)?.with_timezone(&Utc);
    let fraction = if time.timestamp_subsec_micros() == 0 {
        String::new()
    } else {
        format!(".{:06}", time.timestamp_subsec_micros())
    };
    Ok(format!(
        "{}{fraction}+00:00",
        time.format("%Y-%m-%dT%H:%M:%S")
    ))
}

/// A record's place in the batch: it finds a held master, else a rule may
/// create one from it, else it only waits.
#[derive(PartialEq, Eq, PartialOrd, Ord)]
enum Phase {
    Finds,
    Creates,
    Waits,
}
fn phase(found: &BTreeMap<(String, String), IndexMap<String, String>>, items: &[Match]) -> Phase {
    if items.iter().any(|item| found.contains_key(&(item.namespace.clone(), item.value.clone()))) {
        Phase::Finds
    } else if items.iter().any(|item| item.outcomes.on_no_match == OnNoMatch::Mint) {
        Phase::Creates
    } else {
        Phase::Waits
    }
}

pub fn link_matching_records(raw: &str) -> Result<String, String> {
    let input: PreparedInputs =
        serde_json::from_str(raw).map_err(|_| "Invalid prepared record matches")?;
    let mut found: BTreeMap<(String, String), IndexMap<String, String>> = BTreeMap::new();
    for holder in input.found {
        found
            .entry((holder.namespace, holder.value))
            .or_default()
            .extend(holder.records);
    }
    let stored = found.clone();
    let mut result: BTreeMap<&str, Vec<Object>> =
        ["identities", "decisions", "reviews", "mints", "joins"]
            .into_iter()
            .map(|name| (name, Vec::new()))
            .collect();
    for holder in input.plan.caller_holders {
        let key = (holder.namespace, holder.value);
        // A value the caller's or a re-delivered record gives its master,
        // which no master held: re-checked under the lock like a rule's.
        if !stored.contains_key(&key) {
            for entity in holder.records.keys() {
                result.get_mut("mints").unwrap().push(Object::from([
                    ("entity_id".into(), values::write_value(entity)?),
                    ("namespace".into(), values::write_value(&key.0)?),
                    ("raw".into(), values::write_value(&key.1)?),
                ]));
            }
        }
        found.entry(key).or_default().extend(holder.records);
    }
    let mut ids = input.new_ids.into_iter();
    let mut floors = BTreeMap::new();
    let mut consolidations = Consolidations::read(&input.consolidations)?;
    // A master this batch merged away answers as the master it merged into.
    let mut moved: BTreeMap<String, String> = BTreeMap::new();
    let resolve = |moved: &BTreeMap<String, String>, entity: &String| {
        let mut entity = entity.clone();
        while let Some(next) = moved.get(&entity) {
            entity = next.clone();
        }
        entity
    };
    let mut subjects: Vec<_> = input.plan.applicable.iter().collect();
    // Look up first, then master (ticket 138): every record that finds a
    // held master binds before any record creates one, so a value it adds is
    // found by the rest of the batch and no new master shadows a stored one.
    // Then the records a rule may create from, then those that only wait.
    subjects.sort_by_cached_key(|(subject, items)| (phase(&found, items), *subject));
    for (subject, items) in subjects {
        let record = &input.plan.records[subject];
        let kind = read_rule_text(record, "kind")?;
        let mut matches: IndexMap<String, Vec<&Match>> = IndexMap::new();
        // The masters reached through a rule that merges what it reaches.
        let mut merging: BTreeSet<String> = BTreeSet::new();
        let mut problem = None;
        for item in items {
            let merges = item.outcomes.on_several == OnSeveral::Merge;
            if let Some(held) = found.get(&(item.namespace.clone(), item.value.clone())) {
                let held: IndexMap<String, &String> = held
                    .iter()
                    .map(|(entity, held_kind)| (resolve(&moved, entity), held_kind))
                    .collect();
                if held.len() > 1 && !merges {
                    problem = Some(("ambiguous_identifier", item.namespace.clone()));
                    break;
                }
                for (entity, held_kind) in &held {
                    let held_kind = *held_kind;
                    if held_kind != &kind {
                        problem = Some(("incompatible_identifier_kind", item.namespace.clone()));
                        break;
                    }
                    if input.suspended.contains(entity) {
                        problem = Some(("suspended_identifier", item.namespace.clone()));
                        break;
                    }
                    matches.entry(entity.clone()).or_default().push(item);
                    if merges {
                        merging.insert(entity.clone());
                    }
                }
                if problem.is_some() {
                    break;
                }
            }
        }
        // Two or more masters reached through a merging rule's values are one
        // (part A2a): they merge, unless a steward keeps them apart. Any other
        // master the record reaches is still a conflict, so nothing merges.
        let merging: Vec<String> = if merging.len() > 1 { merging.into_iter().collect() } else { Vec::new() };
        let reached = matches
            .values()
            .filter_map(|items| items.last().map(|item| item.namespace.clone()))
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>()
            .join(",");
        // A conflict a `first` rule settles (part A2b): the one master its
        // value reaches; the values the others hold are withheld.
        let mut first = None;
        if problem.is_none() && merging.is_empty() && matches.len() > 1 {
            let firsts: Vec<&String> = matches
                .iter()
                .filter(|(_, items)| items.iter().any(|item| item.outcomes.on_conflict == OnConflict::First))
                .map(|(entity, _)| entity)
                .collect();
            if let [only] = firsts[..] {
                first = Some(only.clone());
            }
        }
        if problem.is_none() && matches.len() > 1 && first.is_none() {
            if merging.is_empty() || matches.keys().any(|entity| !merging.contains(entity)) {
                problem = Some(("conflicting_identifiers", reached));
            } else if consolidations.excluded(&merging) {
                problem = Some(("excluded_consolidation", reached));
            }
        }
        if let Some((reason, namespace)) = problem {
            result.get_mut("reviews").unwrap().push(Object::from([
                ("reason".into(), values::write_value(&reason)?),
                ("namespace".into(), values::write_value(&namespace)?),
                ("subject".into(), values::write_value(subject)?),
                (
                    "assertion_id".into(),
                    values::read_optional_value(record, "assertion_id")?,
                ),
            ]));
            continue;
        }
        let created = matches.is_empty();
        let (entity, selected) = if !matches.is_empty() {
            // The master it binds to: the one it reaches, else the first of
            // those it merges (replay keeps the oldest; any of them is it).
            let entity = first
                .as_ref()
                .or(merging.first())
                .unwrap_or(matches.keys().next().unwrap())
                .clone();
            // One join per master reached, by its stored holding; a conflict
            // settled first joins only the master it binds to.
            for (reached, matched) in matches.iter().filter(|(e, _)| first.is_none() || **e == entity) {
                for item in matched {
                    let Some(held) = stored.get(&(item.namespace.clone(), item.value.clone())) else {
                        continue;
                    };
                    for holder in held.keys().filter(|holder| &resolve(&moved, holder) == reached) {
                        result.get_mut("joins").unwrap().push(Object::from([
                            ("entity_id".into(), values::write_value(holder)?),
                            ("namespace".into(), values::write_value(&item.namespace)?),
                            ("raw".into(), values::write_value(&item.raw)?),
                        ]));
                    }
                }
            }
            let matched = &matches[&entity];
            let selected = if first.is_some() {
                matched.iter().rev().find(|item| item.outcomes.on_conflict == OnConflict::First)
            } else if merging.is_empty() {
                matched.last()
            } else {
                matched.iter().rev().find(|item| item.outcomes.on_several == OnSeveral::Merge)
            };
            (entity, (*selected.ok_or("Missing matched rule")?).clone())
        } else {
            let Some(item) = items.iter().find(|item| item.outcomes.on_no_match == OnNoMatch::Mint) else {
                continue;
            };
            let entity = ids.next().ok_or("Not enough allocated record identities")?;
            if !floors.contains_key(&kind) {
                let at = values::read_time(&input.as_of)?;
                let floor =
                    if let Some(newest) = input.newest.get(&kind).and_then(Option::as_ref) {
                        let newest = values::read_time(newest)?;
                        if at > newest {
                            input.as_of.clone()
                        } else {
                            prepare_decision_time(
                                &newest
                                    .checked_add_signed(Duration::microseconds(1))
                                    .ok_or("Publication time overflow")?
                                    .to_rfc3339(),
                            )?
                        }
                    } else {
                        input.as_of.clone()
                    };
                floors.insert(kind.clone(), floor);
            }
            result.get_mut("identities").unwrap().push(Object::from([
                ("entity_id".into(), values::write_value(&entity)?),
                ("kind".into(), values::write_value(&kind)?),
                ("published_at".into(), values::write_value(&floors[&kind])?),
            ]));
            (entity, item.clone())
        };
        let rule_id = read_rule_text(&selected.rule, "rule_id")?;
        let version = read_rule_text(&selected.rule, "version")?;
        if input
            .refused
            .contains(&(subject.clone(), rule_id.clone(), version.clone()))
        {
            continue;
        }
        let actor = format!("rule:{rule_id}@{version}");
        let at = prepare_decision_time(&input.as_of)?;
        for other in merging.iter().filter(|other| **other != entity) {
            // No survivor named: replay keeps the oldest. It names every live
            // merge either side rests on, this batch's too, and replay applies
            // it after them.
            let mut merge = Object::from([
                ("operation".into(), values::write_value(&"merge")?),
                ("actor".into(), values::write_value(&actor)?),
                ("reason".into(), values::write_value(&format!("identifier_match {}", selected.namespace))?),
                ("at".into(), values::write_value(&at)?),
                ("left".into(), values::write_value(&entity)?),
                ("right".into(), values::write_value(other)?),
                ("depends_on".into(), values::write_value(&consolidations.depends(&entity, other))?),
                ("evidence".into(), values::write_value(&vec![read_rule_text(record, "assertion_id")?])?),
                ("rule_id".into(), values::write_value(&rule_id)?),
                ("rule_version".into(), values::write_value(&version)?),
            ]);
            let hash = values::calculate_content_hash(&values::write_value(&merge)?)?;
            merge.insert("decision_id".into(), values::write_value(&hash)?);
            consolidations.join(&entity, other, hash);
            moved.insert(other.clone(), entity.clone());
            result.get_mut("decisions").unwrap().push(merge);
        }
        // Every identifier no master held, from the source that issues it, is
        // the master's from now on (the value a new master was created by
        // too): a later record in this batch sharing any one of them finds
        // it, and the save re-checks each under the lock (a concurrent run
        // may have taken it).
        for item in items {
            let key = (item.namespace.clone(), item.value.clone());
            let creates = created && key == (selected.namespace.clone(), selected.value.clone());
            if found.contains_key(&key) || !(item.issued || creates) {
                continue;
            }
            found
                .entry(key)
                .or_default()
                .insert(entity.clone(), kind.clone());
            result.get_mut("mints").unwrap().push(Object::from([
                ("entity_id".into(), values::write_value(&entity)?),
                ("namespace".into(), values::write_value(&item.namespace)?),
                ("raw".into(), values::write_value(&item.raw)?),
            ]));
        }
        let withheld: BTreeSet<Withheld> = matches
            .iter()
            .filter(|(other, _)| first.is_some() && **other != entity)
            .flat_map(|(_, items)| items.iter())
            .map(|item| Withheld { namespace: item.namespace.clone(), raw: item.raw.clone() })
            .collect();
        let mut decision = Object::from([
            ("operation".into(), values::write_value(&"bind")?),
            ("actor".into(), values::write_value(&actor)?),
            (
                "reason".into(),
                values::write_value(&format!("identifier_match {}", selected.namespace))?,
            ),
            ("at".into(), values::write_value(&at)?),
            ("subject".into(), values::write_value(subject)?),
            ("entity_id".into(), values::write_value(&entity)?),
            (
                "evidence".into(),
                values::write_value(&vec![read_rule_text(record, "assertion_id")?])?,
            ),
            ("rule_id".into(), values::write_value(&rule_id)?),
            ("rule_version".into(), values::write_value(&version)?),
        ]);
        if !withheld.is_empty() {
            decision.insert("withheld".into(), values::write_value(&withheld)?);
        }
        let hash = values::calculate_content_hash(&values::write_value(&decision)?)?;
        decision.insert("decision_id".into(), values::write_value(&hash)?);
        result.get_mut("decisions").unwrap().push(decision);
    }
    serde_json::to_string(&result).map_err(|_| "Cannot serialize matched record decisions".into())
}
