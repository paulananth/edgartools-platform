//! Configured field ranking over metadata. Payloads and custom code stay Python.

pub type Candidate = (String, String, Option<f64>, bool, String, String);

/// Return source indices in winner order and unauthorized clears in input order.
/// Freshness is prepared by Python's existing timezone/timedelta contract.
pub fn rank(
    sources: &[String],
    clear_sources: &[String],
    allow_unknown_effective: bool,
    candidates: &[Candidate],
) -> (Vec<usize>, Vec<usize>) {
    let mut eligible = Vec::new();
    let mut unauthorized = Vec::new();
    for (index, (source, op, effective, fresh, _, _)) in candidates.iter().enumerate() {
        let Some(priority) = sources.iter().position(|s| s == source) else {
            continue;
        };
        if op == "clear" && !clear_sources.contains(source) {
            unauthorized.push(index);
        } else if (effective.is_some() || allow_unknown_effective) && *fresh {
            eligible.push((priority, index));
        }
    }
    // Stable sorting preserves input order when every configured key ties.
    eligible.sort_by(|(priority_a, a), (priority_b, b)| {
        let ca = &candidates[*a];
        let cb = &candidates[*b];
        priority_a
            .cmp(priority_b)
            .then_with(|| {
                (-ca.2.unwrap_or(f64::NEG_INFINITY))
                    .partial_cmp(&(-cb.2.unwrap_or(f64::NEG_INFINITY)))
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
            .then_with(|| ca.0.cmp(&cb.0))
            .then_with(|| ca.4.cmp(&cb.4))
            .then_with(|| ca.5.cmp(&cb.5))
    });
    (
        eligible.into_iter().map(|(_, index)| index).collect(),
        unauthorized,
    )
}
