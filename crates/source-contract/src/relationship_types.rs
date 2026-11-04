//! The relationship types MDM masters, read from their RDM code set (ticket 132).
//! Each type is a code whose properties are its rules; its capacities are its
//! child codes, `TYPE:capacity`. This module is the one place the rules are
//! read and checked: at policy registration and before every calculation.

use indexmap::IndexMap;
use serde::Deserialize;
use serde_json::{Map, Value};
use std::collections::BTreeSet;

const CYCLES: &[&str] = &["invalid", "review"];

/// The ultimate-parent algorithms, named once: the check and the calculation both read this list.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UltimateParent {
    /// The current parent chain of each entity.
    ChainV1,
    /// The parent chain's whole history.
    ChainV2,
}

impl UltimateParent {
    const NAMES: [(UltimateParent, &'static str); 2] =
        [(UltimateParent::ChainV1, "accounting-chain-v1"), (UltimateParent::ChainV2, "accounting-chain-v2")];

    pub fn name(self) -> &'static str {
        Self::NAMES.iter().find(|(algorithm, _)| *algorithm == self).map_or("", |(_, name)| name)
    }

    pub fn from_name(name: &str) -> Option<Self> {
        Self::NAMES.iter().find(|(_, known)| *known == name).map(|(algorithm, _)| *algorithm)
    }
}

/// One type's rules, as written. An unknown property refuses the type.
#[derive(Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TypeRules {
    pub from: Vec<String>,
    pub to: Vec<String>,
    pub from_profile: Option<String>,
    pub to_profile: Option<String>,
    pub capacities: Option<Vec<String>>,
    hierarchy: Option<bool>,
    cycles: Option<String>,
    one_parent: Option<bool>,
    ultimate_parent: Option<String>,
    pub ultimate_type: Option<String>,
    ends_parent_links: Option<bool>,
    keeps_start: Option<bool>,
    one_target: Option<bool>,
}

impl TypeRules {
    /// Links of this type form a hierarchy.
    pub fn is_hierarchy(&self) -> bool {
        self.hierarchy == Some(true)
    }

    /// An entity has one parent at a time.
    pub fn is_one_parent(&self) -> bool {
        self.one_parent == Some(true)
    }

    /// A cycle sets its links aside (`invalid`) rather than only asking for review.
    pub fn cycles_are_invalid(&self) -> bool {
        self.cycles.as_deref() == Some("invalid")
    }

    /// A link of this type ends the entity's parent links when it starts.
    pub fn ends_parent_links(&self) -> bool {
        self.ends_parent_links == Some(true)
    }

    /// The earliest start seen is kept.
    pub fn keeps_start(&self) -> bool {
        self.keeps_start == Some(true)
    }

    /// An entity has one target at a time (a Security has one issuer): two targets over
    /// overlapping periods set both links aside and ask for review.
    pub fn is_one_target(&self) -> bool {
        self.one_target == Some(true)
    }

    /// The type's ultimate-parent algorithm; the check refuses a name it does not know.
    pub fn ultimate(&self) -> Option<UltimateParent> {
        self.ultimate_parent.as_deref().and_then(UltimateParent::from_name)
    }
}

/// The types as typed rules, parsed once. Call after `check`, which gives the refusals their words.
pub fn parse(types: &Map<String, Value>) -> Result<IndexMap<String, TypeRules>, String> {
    types
        .iter()
        .map(|(name, spec)| {
            serde_json::from_value(spec.clone())
                .map(|rules| (name.clone(), rules))
                .map_err(|error| format!("Relationship type {name} has rules it cannot run: {error}"))
        })
        .collect()
}

/// Refuse types that could not run exactly as written. `kinds`, when given,
/// are the kinds an end may name.
pub fn check(types: &Map<String, Value>, kinds: Option<&BTreeSet<String>>) -> Result<(), String> {
    if types.is_empty() {
        return Err("The relationship types declare at least one type".into());
    }
    for (name, spec) in types {
        let rules: TypeRules = serde_json::from_value(spec.clone())
            .map_err(|error| format!("Relationship type {name} has rules it cannot run: {error}"))?;
        for (end, named) in [("from", &rules.from), ("to", &rules.to)] {
            if named.is_empty() {
                return Err(format!("Relationship type {name} names at least one kind at its {end} end"));
            }
            if let Some(kinds) = kinds {
                let unknown: Vec<_> = named.iter().filter(|kind| !kinds.contains(*kind)).collect();
                if !unknown.is_empty() {
                    return Err(format!("Relationship type {name} names an unknown kind: {unknown:?}"));
                }
            }
        }
        for profile in [&rules.from_profile, &rules.to_profile].into_iter().flatten() {
            if profile.trim().is_empty() {
                return Err(format!("Relationship type {name}: a profile is a role's name"));
            }
        }
        if rules.capacities.as_ref().is_some_and(Vec::is_empty) {
            return Err(format!("Relationship type {name}: capacities is a list of names"));
        }
        let hierarchy = rules.hierarchy == Some(true);
        if hierarchy {
            if !rules.cycles.as_deref().is_some_and(|c| CYCLES.contains(&c)) {
                return Err(format!("Relationship type {name}: a hierarchy says what its cycles do: invalid or review"));
            }
        } else if rules.cycles.is_some() || rules.one_parent.is_some() || rules.ultimate_parent.is_some() {
            return Err(format!("Relationship type {name}: cycles, one_parent and ultimate_parent go only on a hierarchy"));
        }
        if let Some(algorithm) = &rules.ultimate_parent {
            if UltimateParent::from_name(algorithm).is_none() {
                return Err(format!("Relationship type {name}: unknown ultimate-parent algorithm {algorithm}"));
            }
        }
        match (&rules.ultimate_parent, &rules.ultimate_type) {
            (None, None) => {}
            (Some(_), Some(named_type)) if types.contains_key(named_type) => {}
            _ => {
                return Err(format!(
                    "Relationship type {name}: an ultimate parent names its ultimate_type, a declared type"
                ))
            }
        }
        for (flag, value) in [
            ("ends_parent_links", rules.ends_parent_links),
            ("keeps_start", rules.keeps_start),
            ("one_target", rules.one_target),
        ] {
            if value.is_some() && (value != Some(true) || hierarchy) {
                return Err(format!("Relationship type {name}: {flag} is true, on a link that is no parent"));
            }
        }
    }
    Ok(())
}

/// The types of a published code set version's rows (RDM's canonical form):
/// each valid top code a type with its properties, each valid child code
/// `TYPE:capacity` one of its type's capacities. The result is checked.
pub fn from_codes(rows: &[Map<String, Value>], kinds: &BTreeSet<String>) -> Result<Map<String, Value>, String> {
    let text = |row: &Map<String, Value>, field: &str| row.get(field).and_then(Value::as_str).map(str::to_owned);
    let mut types = Map::new();
    let valid = |row: &&Map<String, Value>| text(row, "status").as_deref() != Some("invalid");
    for row in rows.iter().filter(valid).filter(|row| text(row, "parent_code").is_none()) {
        let code = text(row, "code").ok_or("A relationship type code has no code")?;
        let properties = match row.get("properties") {
            Some(Value::Object(properties)) => properties.clone(),
            _ => return Err(format!("Relationship type {code} has no properties")),
        };
        if properties.contains_key("capacities") {
            return Err(format!("Relationship type {code}: its capacities are its child codes"));
        }
        types.insert(code, Value::Object(properties));
    }
    // A retired type's capacities go with it.
    let retired: BTreeSet<String> = rows
        .iter()
        .filter(|row| !valid(row) && text(row, "parent_code").is_none())
        .filter_map(|row| text(row, "code"))
        .collect();
    for row in rows.iter().filter(valid) {
        let Some(parent) = text(row, "parent_code") else { continue };
        if retired.contains(&parent) {
            continue;
        }
        let code = text(row, "code").unwrap_or_default();
        let capacity = code
            .strip_prefix(&format!("{parent}:"))
            .filter(|capacity| !capacity.is_empty())
            .ok_or_else(|| format!("Capacity code {code} is named TYPE:capacity under its type"))?;
        let Some(Value::Object(spec)) = types.get_mut(&parent) else {
            return Err(format!("Capacity code {code} is under no relationship type"));
        };
        let held = spec.entry("capacities").or_insert_with(|| Value::Array(Vec::new()));
        if let Value::Array(held) = held {
            held.push(Value::String(capacity.to_owned()));
        }
    }
    check(&types, Some(kinds))?;
    Ok(types)
}

/// The Python binding's entry: `{"codes": [...], "kinds": [...]}` to the types.
pub fn prepare_relationship_types(raw: &str) -> Result<String, String> {
    #[derive(Deserialize)]
    struct Command {
        codes: Vec<Map<String, Value>>,
        kinds: BTreeSet<String>,
    }
    let command: Command = serde_json::from_str(raw).map_err(|_| "Invalid relationship types command")?;
    serde_json::to_string(&from_codes(&command.codes, &command.kinds)?).map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn kinds() -> BTreeSet<String> {
        ["company", "person"].into_iter().map(String::from).collect()
    }

    fn rows(value: Value) -> Vec<Map<String, Value>> {
        serde_json::from_value(value).unwrap()
    }

    #[test]
    fn types_come_from_codes_with_capacities_from_child_codes() {
        let found = from_codes(&rows(json!([
            {"code": "OWNS", "parent_code": null, "status": "valid", "properties": {"from": ["person"], "to": ["company"]}},
            {"code": "OWNS:director", "parent_code": "OWNS", "status": "valid"},
            {"code": "OWNS:officer", "parent_code": "OWNS", "status": "valid"},
            {"code": "GONE", "parent_code": null, "status": "invalid", "properties": {"from": ["x"], "to": ["y"]}},
            {"code": "GONE:director", "parent_code": "GONE", "status": "valid"},
            {"code": "PARENT", "parent_code": null, "status": "valid", "properties": {
                "from": ["company"], "to": ["company"], "hierarchy": true, "cycles": "invalid",
                "ultimate_parent": "accounting-chain-v2", "ultimate_type": "ULTIMATE"}},
            {"code": "ULTIMATE", "parent_code": null, "status": "valid", "properties": {
                "from": ["company"], "to": ["company"], "hierarchy": true, "cycles": "invalid"}}
        ])), &kinds())
        .unwrap();
        assert_eq!(found["OWNS"]["capacities"], json!(["director", "officer"]));
        assert!(!found.contains_key("GONE"));
        assert_eq!(found["PARENT"]["ultimate_type"], json!("ULTIMATE"));
    }

    #[test]
    fn each_refusal_is_named() {
        let base = json!({"from": ["company"], "to": ["company"]});
        let with = |extra: Value| {
            let mut spec = base.as_object().unwrap().clone();
            spec.extend(extra.as_object().unwrap().clone());
            rows(json!([{"code": "T", "parent_code": null, "status": "valid", "properties": spec}]))
        };
        for (extra, words) in [
            (json!({"invented": true}), "rules it cannot run"),
            (json!({"from": []}), "at least one kind"),
            (json!({"to": ["invented"]}), "unknown kind"),
            (json!({"cycles": "invalid"}), "only on a hierarchy"),
            (json!({"hierarchy": true}), "what its cycles do"),
            (json!({"hierarchy": true, "cycles": "invalid", "ultimate_parent": "accounting-chain-v2"}), "names its ultimate_type"),
            (json!({"hierarchy": true, "cycles": "invalid", "ultimate_parent": "invented", "ultimate_type": "T"}), "unknown ultimate-parent"),
            (json!({"ultimate_type": "T"}), "names its ultimate_type"),
            (json!({"keeps_start": false}), "no parent"),
            (json!({"one_target": false}), "no parent"),
            (json!({"hierarchy": true, "cycles": "review", "one_target": true}), "no parent"),
            (json!({"hierarchy": true, "cycles": "review", "ends_parent_links": true}), "no parent"),
            (json!({"capacities": ["director"]}), "its child codes"),
            (json!({"to_profile": " "}), "a role's name"),
        ] {
            let error = from_codes(&with(extra.clone()), &kinds()).unwrap_err();
            assert!(error.contains(words), "{extra}: {error}");
        }
        let orphan = rows(json!([{"code": "X:director", "parent_code": "X", "status": "valid"}]));
        assert!(from_codes(&orphan, &kinds()).unwrap_err().contains("no relationship type"));
        assert!(from_codes(&[], &kinds()).unwrap_err().contains("at least one type"));
    }

    #[test]
    fn the_rules_are_typed_and_the_algorithms_named_once() {
        let types = from_codes(&rows(json!([
            {"code": "PARENT", "parent_code": null, "status": "valid", "properties": {
                "from": ["company"], "to": ["company"], "hierarchy": true, "cycles": "invalid", "one_parent": true,
                "ultimate_parent": "accounting-chain-v1", "ultimate_type": "ULTIMATE"}},
            {"code": "ULTIMATE", "parent_code": null, "status": "valid", "properties": {
                "from": ["company"], "to": ["company"], "hierarchy": true, "cycles": "review"}},
            {"code": "SUCCEEDS", "parent_code": null, "status": "valid", "properties": {
                "from": ["company"], "to": ["company"], "ends_parent_links": true, "keeps_start": true}}
        ])), &kinds())
        .unwrap();
        let rules = parse(&types).unwrap();
        let parent = &rules["PARENT"];
        assert!(parent.is_hierarchy() && parent.is_one_parent() && parent.cycles_are_invalid());
        assert_eq!(parent.ultimate(), Some(UltimateParent::ChainV1));
        assert!(!rules["ULTIMATE"].cycles_are_invalid() && rules["ULTIMATE"].ultimate().is_none());
        assert!(rules["SUCCEEDS"].ends_parent_links() && rules["SUCCEEDS"].keeps_start() && !rules["SUCCEEDS"].is_hierarchy());
        for algorithm in [UltimateParent::ChainV1, UltimateParent::ChainV2] {
            assert_eq!(UltimateParent::from_name(algorithm.name()), Some(algorithm));
        }
        assert_eq!(UltimateParent::from_name("accounting-chain-v3"), None);
    }

    /// The calculation reads typed fields: no rule is read by its name from an untyped object, where a
    /// misspelt key reads as absent and passes the check (ticket 140).
    #[test]
    fn the_calculation_reads_no_rule_by_its_name() {
        let calculation = include_str!("relationships.rs");
        for name in ["keeps_start", "ends_parent_links", "one_parent", "ultimate_parent", "from_profile", "to_profile"] {
            assert!(!calculation.contains(&format!("\"{name}\"")), "relationships.rs reads {name} by its name");
        }
        assert!(!calculation.contains("\"accounting-chain-"), "an algorithm is named once, in relationship_types.rs");
    }
}
