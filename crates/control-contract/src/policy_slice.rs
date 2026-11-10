//! The part of the merge policy that acts on one source's files.
//!
//! The Change Journal skips a file already processed under the same processing identity. That identity must change
//! when something that decides how the source's records are read or merged changes, and not when a rule of another
//! source changes: a new rule for N-PORT must not reprocess OpenFIGI (operator, 2026-11-10: "Change journal must
//! work"). The slice holds, per identity kind that has a rule of the source:
//! - the kind's own settings (its field defaults, normalizers and lists), and
//! - the source's rules, with their activations, and
//! - the identifier contracts those rules search or that name the source as an issuer;
//!
//! and every top-level section that is not per kind (the shared reference pins, bars, relationship types).
use serde_json::{Map, Value};
use std::collections::BTreeSet;

fn namespaces_of(rule: &Value) -> BTreeSet<String> {
    rule.get("when")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|test| test.get("args")?.get("namespace")?.as_str())
        .map(str::to_owned)
        .collect()
}

fn names_source(contract: &Value, source: &str) -> bool {
    contract
        .get("sources")
        .and_then(Value::as_array)
        .is_some_and(|sources| sources.iter().any(|s| s.as_str() == Some(source)))
}

/// The slice of `policy` for the files of dataset `source` (a Dataset Contract code such as `openfigi.security.v4`).
pub fn source_policy_slice(policy: &Value, source: &str) -> Value {
    let mut out = Map::new();
    let Some(body) = policy.as_object() else {
        return Value::Object(out);
    };
    for (key, value) in body {
        if key != "kinds" && key != "automatic_rules" {
            out.insert(key.clone(), value.clone());
        }
    }
    let mut kinds = Map::new();
    let mut selected = BTreeSet::new();
    for (kind, block) in body
        .get("kinds")
        .and_then(Value::as_object)
        .into_iter()
        .flatten()
    {
        let rules: Vec<Value> = block
            .get("rules")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter(|rule| rule.get("source").and_then(Value::as_str) == Some(source))
            .cloned()
            .collect();
        if rules.is_empty() {
            continue;
        }
        let searched: BTreeSet<String> = rules.iter().flat_map(namespaces_of).collect();
        let mut part = Map::new();
        for (key, value) in block.as_object().into_iter().flatten() {
            if key != "rules" && key != "identifiers" {
                part.insert(key.clone(), value.clone());
            }
        }
        let contracts: Map<String, Value> = block
            .get("identifiers")
            .and_then(Value::as_object)
            .into_iter()
            .flatten()
            .filter(|(namespace, contract)| {
                searched.contains(*namespace) || names_source(contract, source)
            })
            .map(|(namespace, contract)| (namespace.clone(), contract.clone()))
            .collect();
        part.insert("identifiers".into(), Value::Object(contracts));
        for rule in &rules {
            if let Some(id) = rule.get("rule_id").and_then(Value::as_str) {
                selected.insert((kind.clone(), id.to_owned()));
            }
        }
        part.insert("rules".into(), Value::Array(rules));
        kinds.insert(kind.clone(), Value::Object(part));
    }
    out.insert("kinds".into(), Value::Object(kinds));
    let active: Vec<Value> = body
        .get("automatic_rules")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|entry| {
            let kind = entry
                .get("kind")
                .and_then(Value::as_str)
                .unwrap_or_default();
            let id = entry
                .get("rule_id")
                .and_then(Value::as_str)
                .unwrap_or_default();
            selected.contains(&(kind.to_owned(), id.to_owned()))
        })
        .cloned()
        .collect();
    out.insert("automatic_rules".into(), Value::Array(active));
    Value::Object(out)
}

/// The digest of that slice, for the processing identity.
pub fn source_policy_digest(policy: &str, source: &str) -> Result<String, String> {
    let policy: Value = serde_json::from_str(policy).map_err(|_| "Invalid policy".to_string())?;
    crate::digest_json(&source_policy_slice(&policy, source).to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn policy() -> Value {
        json!({
            "bars": {"classification": 0.95},
            "kinds": {
                "security": {
                    "version": "security-v1",
                    "defaults": {"sources": ["figi", "nport"]},
                    "rules": [
                        {"rule_id": "figi-cusip", "version": "1", "source": "figi", "when": [{"args": {"namespace": "cusip"}}]},
                        {"rule_id": "nport-cusip", "version": "1", "source": "nport", "when": [{"args": {"namespace": "cusip"}}]},
                        {"rule_id": "nport-isin", "version": "1", "source": "nport", "when": [{"args": {"namespace": "isin"}}]}
                    ],
                    "identifiers": {
                        "cusip": {"sources": ["figi", "nport"], "claim": {"forward": 1}},
                        "isin": {"sources": ["nport"], "claim": {"forward": 1}},
                        "ticker": {"sources": ["figi"]}
                    }
                },
                "company": {"rules": [{"rule_id": "cik", "version": "1", "source": "sec"}], "identifiers": {}}
            },
            "automatic_rules": [
                {"kind": "security", "rule_id": "figi-cusip", "rule_version": "1"},
                {"kind": "security", "rule_id": "nport-cusip", "rule_version": "1"},
                {"kind": "company", "rule_id": "cik", "rule_version": "1"}
            ]
        })
    }

    fn digest(policy: &Value, source: &str) -> String {
        source_policy_digest(&policy.to_string(), source).unwrap()
    }

    #[test]
    fn the_slice_holds_only_the_sources_rules_activations_and_contracts() {
        let slice = source_policy_slice(&policy(), "figi");
        let kinds = slice["kinds"].as_object().unwrap();
        assert_eq!(kinds.keys().collect::<Vec<_>>(), ["security"]); // no rule of figi in company
        let security = &kinds["security"];
        let rules: Vec<_> = security["rules"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| r["rule_id"].as_str().unwrap())
            .collect();
        assert_eq!(rules, ["figi-cusip"]);
        let contracts: Vec<_> = security["identifiers"]
            .as_object()
            .unwrap()
            .keys()
            .collect();
        assert_eq!(contracts, ["cusip", "ticker"]); // cusip is searched, ticker names figi as an issuer, isin is neither
        assert_eq!(slice["automatic_rules"].as_array().unwrap().len(), 1);
        assert_eq!(slice["bars"]["classification"], json!(0.95)); // a shared section stays
    }

    #[test]
    fn a_change_to_another_sources_rule_does_not_change_the_identity() {
        let before = digest(&policy(), "figi");
        let mut changed = policy();
        changed["kinds"]["security"]["rules"][1]["version"] = json!("2"); // nport-cusip
        changed["kinds"]["security"]["identifiers"]["isin"]["claim"]["forward"] = json!(2);
        changed["kinds"]["company"]["rules"][0]["version"] = json!("2");
        assert_eq!(digest(&changed, "figi"), before);
        assert_ne!(digest(&changed, "nport"), digest(&policy(), "nport")); // but nport's own identity moves
    }

    #[test]
    fn a_change_to_the_sources_own_rule_contract_or_defaults_changes_it() {
        let before = digest(&policy(), "figi");
        let mut own = policy();
        own["kinds"]["security"]["rules"][0]["version"] = json!("2");
        assert_ne!(digest(&own, "figi"), before);
        let mut contract = policy();
        contract["kinds"]["security"]["identifiers"]["cusip"]["claim"]["forward"] = json!(2);
        assert_ne!(digest(&contract, "figi"), before); // a contract it searches
        let mut defaults = policy();
        defaults["kinds"]["security"]["defaults"]["sources"] = json!(["nport", "figi"]);
        assert_ne!(digest(&defaults, "figi"), before); // the kind's field defaults
        let mut shared = policy();
        shared["bars"]["classification"] = json!(0.9);
        assert_ne!(digest(&shared, "figi"), before); // a shared section
    }

    #[test]
    fn a_source_with_no_rule_gets_the_shared_sections_only() {
        let slice = source_policy_slice(&policy(), "nobody");
        assert!(slice["kinds"].as_object().unwrap().is_empty());
        assert!(slice["automatic_rules"].as_array().unwrap().is_empty());
        assert_eq!(digest(&policy(), "nobody"), digest(&policy(), "nobody2"));
    }

    #[test]
    fn a_policy_that_is_not_json_is_refused() {
        assert!(source_policy_digest("{", "figi").is_err());
    }
}
