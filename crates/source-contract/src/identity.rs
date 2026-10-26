//! Replay accepted, evidence-bearing commands; no automatic/domain matching.
use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

#[derive(Deserialize)]
pub struct Identity {
    pub id: String,
    pub kind: String,
    pub published: i64,
}
#[derive(Deserialize)]
pub struct Decision {
    pub id: String,
    pub at: i64,
    pub op: String,
    pub target: Option<String>,
    pub subject: Option<String>,
    pub entity: Option<String>,
    pub left: Option<String>,
    pub right: Option<String>,
    pub survivor: Option<String>,
    pub source: Option<String>,
    pub expires: Option<i64>,
    pub evidence: bool,
    pub depends: Vec<String>,
    pub entity_present: bool,
}
#[derive(Serialize)]
pub struct State {
    pub canonical: IndexMap<String, String>,
    pub bindings: IndexMap<String, String>,
    pub exclusions: Vec<(String, String)>,
    pub overrides: Vec<usize>,
    pub retired: HashSet<String>,
    pub quarantined: IndexMap<String, String>,
}
fn required(value: &Option<String>) -> Result<&str, String> {
    value
        .as_deref()
        .ok_or_else(|| "Missing decision operand".into())
}
fn root<'a>(parent: &'a IndexMap<String, String>, mut key: &'a str) -> Result<&'a str, String> {
    loop {
        let next = parent.get(key).ok_or("Unknown identity")?;
        if next == key {
            return Ok(key);
        }
        key = next;
    }
}
pub fn replay(
    identities: Vec<Identity>,
    decisions: Vec<Decision>,
    clock: i64,
) -> Result<State, String> {
    let ids: IndexMap<_, _> = identities.into_iter().map(|i| (i.id.clone(), i)).collect();
    let mut parent: IndexMap<_, _> = ids.keys().map(|i| (i.clone(), i.clone())).collect();
    let mut state = State {
        canonical: IndexMap::new(),
        bindings: IndexMap::new(),
        exclusions: Vec::new(),
        overrides: Vec::new(),
        retired: HashSet::new(),
        quarantined: IndexMap::new(),
    };
    let mut ordered: Vec<_> = decisions
        .iter()
        .enumerate()
        .filter(|(_, d)| d.at <= clock)
        .collect();
    // At one time, a merge comes after the merges it depends on (one batch
    // may make several, ticket 138 part A2a); otherwise by id.
    let at_once: HashMap<&str, &Decision> = ordered.iter().map(|(_, d)| (d.id.as_str(), *d)).collect();
    fn depth<'a>(d: &'a Decision, all: &HashMap<&str, &'a Decision>, seen: &mut HashMap<&'a str, usize>) -> usize {
        if let Some(found) = seen.get(d.id.as_str()) {
            return *found;
        }
        seen.insert(&d.id, 0);
        let found = d
            .depends
            .iter()
            .filter_map(|id| all.get(id.as_str()).filter(|other| other.at == d.at))
            .map(|other| 1 + depth(other, all, seen))
            .max()
            .unwrap_or(0);
        seen.insert(&d.id, found);
        found
    }
    let mut seen = HashMap::new();
    let depths: HashMap<&str, usize> = ordered
        .iter()
        .map(|(_, d)| (d.id.as_str(), if d.op == "merge" { depth(d, &at_once, &mut seen) } else { 0 }))
        .collect();
    ordered.sort_by(|(_, a), (_, b)| {
        (a.at, depths[a.id.as_str()], &a.id).cmp(&(b.at, depths[b.id.as_str()], &b.id))
    });
    let by_id: HashMap<_, _> = ordered.iter().map(|(_, d)| (d.id.as_str(), *d)).collect();
    let mut revoked = HashSet::new();
    let mut revoked_at = HashMap::new();
    let mut unbound: HashMap<&str, Vec<(i64, i64, &str)>> = HashMap::new();
    for (_, d) in &ordered {
        if d.op != "reverse" && d.op != "revoke" {
            continue;
        }
        let target = d
            .target
            .as_deref()
            .and_then(|target| by_id.get(target))
            .ok_or("Reversal/revocation must reference an earlier decision")?;
        if target.at >= d.at {
            return Err("Reversal/revocation must reference an earlier decision".into());
        }
        let valid = if d.op == "reverse" {
            target.op == "merge"
        } else {
            ["override", "exclude", "reverse", "bind", "quarantine"].contains(&target.op.as_str())
        };
        if !valid {
            return Err("Invalid reversal/revocation target".into());
        }
        if target.op == "bind" {
            if revoked.contains(target.id.as_str()) {
                return Err("This bind is already revoked".into());
            }
            if (d.subject.as_ref(), d.entity.as_ref())
                != (target.subject.as_ref(), target.entity.as_ref())
            {
                return Err("A revocation names the bind it revokes: its subject and entity".into());
            }
            unbound
                .entry(required(&target.subject)?)
                .or_default()
                .push((target.at, d.at, required(&target.entity)?));
        }
        revoked.insert(target.id.as_str());
        revoked_at.insert(target.id.as_str(), d.at);
    }
    let mut held: HashMap<&str, Vec<(i64, Option<i64>)>> = HashMap::new();
    for (_, d) in &ordered {
        if d.op == "quarantine" {
            held.entry(required(&d.subject)?)
                .or_default()
                .push((d.at, revoked_at.get(d.id.as_str()).copied()));
        }
        if d.op == "merge"
            && !revoked.contains(d.id.as_str())
            && d.depends.iter().any(|i| revoked.contains(i.as_str()))
        {
            return Err("Dependent merge requires review before reversal".into());
        }
    }
    let mut components: HashMap<&str, HashSet<String>> = HashMap::new();
    for (index, d) in &ordered {
        let is_revoked = revoked.contains(d.id.as_str());
        match d.op.as_str() {
            "bind" => {
                let subject = required(&d.subject)?;
                let entity = required(&d.entity)?;
                root(&parent, entity)?;
                if is_revoked {
                    continue;
                }
                if unbound.get(subject).is_some_and(|windows| {
                    windows.iter().any(|(start, end, other)| {
                        *start <= d.at && d.at < *end && *other != entity
                    })
                }) || state
                    .bindings
                    .get(subject)
                    .is_some_and(|other| other != entity)
                {
                    return Err(
                        "Moving an established source binding requires a correction contract"
                            .into(),
                    );
                }
                if held.get(subject).is_some_and(|windows| {
                    windows
                        .iter()
                        .any(|(start, end)| *start <= d.at && end.is_none_or(|end| d.at < end))
                }) {
                    return Err("A quarantined record is left out of matching".into());
                }
                if !d.evidence {
                    return Err("Binding requires source assertion evidence".into());
                }
                state.bindings.insert(subject.into(), entity.into());
            }
            "merge" => {
                if is_revoked {
                    if ordered.iter().any(|(_, x)| {
                        x.op == "reverse"
                            && x.target.as_deref() == Some(&d.id)
                            && !revoked.contains(x.id.as_str())
                    }) {
                        state
                            .exclusions
                            .push((required(&d.left)?.into(), required(&d.right)?.into()));
                    }
                    continue;
                }
                let left = root(&parent, required(&d.left)?)?.to_owned();
                let right = root(&parent, required(&d.right)?)?.to_owned();
                if left == right {
                    return Err("Already consolidated identities".into());
                }
                if ids[&left].kind != ids[&right].kind {
                    return Err("Incompatible identity kinds".into());
                }
                let members: HashSet<_> = ids
                    .keys()
                    .filter(|i| root(&parent, i).is_ok_and(|r| r == left || r == right))
                    .cloned()
                    .collect();
                if components.iter().any(|(id, group)| {
                    !group.is_disjoint(&members) && !d.depends.iter().any(|i| i == id)
                }) {
                    return Err("Merge is missing dependency evidence".into());
                }
                let survivor = d
                    .survivor
                    .as_deref()
                    .filter(|s| !s.is_empty())
                    .unwrap_or_else(|| {
                        if (ids[&left].published, &left) <= (ids[&right].published, &right) {
                            &left
                        } else {
                            &right
                        }
                    })
                    .to_owned();
                if survivor != left && survivor != right {
                    return Err("Survivor must be a current identity".into());
                }
                parent.insert(if survivor == left { right } else { left }, survivor);
                components.insert(&d.id, members);
            }
            "exclude" if !is_revoked => state
                .exclusions
                .push((required(&d.left)?.into(), required(&d.right)?.into())),
            "override" if !is_revoked => {
                if !d.evidence {
                    return Err("Override requires evidence".into());
                }
                if d.expires.is_none_or(|expires| expires > clock) {
                    state.overrides.push(*index)
                }
            }
            "quarantine" => {
                let subject = d.subject.as_deref().filter(|s| !s.is_empty());
                if subject.is_none() || !d.entity_present {
                    return Err(
                        "A quarantine names its record and the Company it was linked to".into(),
                    );
                }
                let subject = subject.unwrap();
                let entity = required(&d.entity)?;
                root(&parent, entity)?;
                if state.bindings.contains_key(subject)
                    || unbound.get(subject).is_some_and(|windows| {
                        windows
                            .iter()
                            .any(|(start, end, _)| *start <= d.at && d.at < *end)
                    })
                {
                    return Err("Revoke the record's bind before quarantining it".into());
                }
                if !is_revoked {
                    state.quarantined.insert(subject.into(), entity.into());
                }
            }
            "retire_source" => {
                if !d.evidence {
                    return Err("Retirement requires evidence".into());
                }
                state.retired.insert(required(&d.source)?.into());
            }
            "reverse" | "revoke" | "override" | "exclude" => {}
            _ => return Err("Unsupported decision operation".into()),
        }
    }
    state.canonical = ids
        .keys()
        .map(|i| Ok((i.clone(), root(&parent, i)?.to_owned())))
        .collect::<Result<_, String>>()?;
    for (left, right) in &state.exclusions {
        if root(&parent, left)? == root(&parent, right)? {
            return Err("Match Exclusion blocks consolidation".into());
        }
    }
    Ok(state)
}
