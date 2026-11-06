//! Group a batch's records that share a matching key, before any store is read.

use std::collections::{BTreeMap, HashMap};

fn root(parent: &mut [usize], mut at: usize) -> usize {
    while parent[at] != at {
        parent[at] = parent[parent[at]];
        at = parent[at];
    }
    at
}

fn join(parent: &mut [usize], left: usize, right: usize) {
    let (left, right) = (root(parent, left), root(parent, right));
    parent[left] = right;
}

/// Reads `[[record, [key, ...]], ...]` and returns each record with its group's
/// lowest record, so the answer does not depend on the order of the input.
pub fn group_batch_records(raw: &str) -> Result<String, String> {
    let entries: Vec<(String, Vec<String>)> =
        serde_json::from_str(raw).map_err(|_| "Invalid batch records")?;
    let mut parent: Vec<usize> = (0..entries.len()).collect();
    let mut records: HashMap<&str, usize> = HashMap::new();
    let mut keys: HashMap<&str, usize> = HashMap::new();
    for (at, (record, held)) in entries.iter().enumerate() {
        if let Some(first) = records.insert(record, at) {
            join(&mut parent, at, first);
        }
        for key in held {
            if let Some(first) = keys.insert(key, at) {
                join(&mut parent, at, first);
            }
        }
    }
    let mut lowest: HashMap<usize, &str> = HashMap::new();
    for (at, (record, _)) in entries.iter().enumerate() {
        let group = root(&mut parent, at);
        let held = lowest.entry(group).or_insert(record);
        if record.as_str() < *held {
            *held = record;
        }
    }
    let mut grouped = BTreeMap::new();
    for (at, (record, _)) in entries.iter().enumerate() {
        let group = root(&mut parent, at);
        grouped.insert(record.as_str(), lowest[&group]);
    }
    serde_json::to_string(&grouped).map_err(|_| "Cannot serialize batch groups".into())
}
