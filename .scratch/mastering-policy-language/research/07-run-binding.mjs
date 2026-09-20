// THROWAWAY — Mastering Policy Language research 07, part 2.
//
// Runs the Person policy document's deterministic Tier A rule (`person-tier-a-owner-cik`,
// policy-person.json) for real over the union corpus, with an in-memory identity store
// (prototype/interpret-binding.mjs), and tries the three ticket-06 Q2 behaviours as switches:
//
//   a  defer the violating record only (rule stays active)
//   b  deactivate the rule on the first violation (everything after goes to the Steward)
//   c  defer and count against a declared tolerance (violations per 10,000 decisions,
//      evaluated cumulatively once `min_decisions` have been made); deactivate when exceeded
//
// × two violation predicates ('strict': any non-identical name on the CIK's Person;
//   'lenient': only relations the research-07 pre-sort could not explain)
// × two corpus orders ('accession' = (accession, owner_index), the key 18-classify.py's
//   stage_sample uses; 'period' = (periodOfReport, accession, owner_index) as a
//   chronological sensitivity check).
//
//   node 07-run-binding.mjs <union-corpus.jsonl> <out.json>
//
// Only rows rule C-J classified `person` enter (the rule's `applies_to_verdict`). No I/O
// beyond the two files. Nothing here is production code.

import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { validate, bindings, record, IdentityStore, nameRelation, RELATION_ORDER } from '../prototype/interpret-binding.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const [corpusPath, outPath] = process.argv.slice(2);
if (!corpusPath || !outPath) { console.error('usage: node 07-run-binding.mjs <union-corpus.jsonl> <out.json>'); process.exit(2); }

const doc = JSON.parse(readFileSync(join(here, '..', 'prototype', 'policy-person.json'), 'utf8'));
const v = validate(doc);
if (!v.ok) { console.error('policy refused at registration:', v.errors); process.exit(1); }

const ALIAS = { owner_name: 'owner_name', owner_cik: 'owner_cik' };
const RULE = 'person-tier-a-owner-cik';
const NS = 'sec.cik';

const corpusBytes = readFileSync(corpusPath);
const all = corpusBytes.toString('utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
const personRows = all.filter((r) => r.cj === 'person' && r.owner_cik != null);

const orders = {
  accession: (rows) => [...rows].sort((x, y) => x.accession.localeCompare(y.accession) || x.owner_index - y.owner_index),
  period: (rows) => [...rows].sort((x, y) => (x.period ?? '').localeCompare(y.period ?? '') || x.accession.localeCompare(y.accession) || x.owner_index - y.owner_index),
};

const TOLERANCES = [0.5, 1, 2, 5, 10, 20]; // violations per 10,000 decisions
const MIN_DECISIONS = 1000;

// mode 'cumulative': violations/decisions since start; mode 'window': violations in the last
// WINDOW decisions. inject = {start, n}: rows[start, start+n) get owner_cik := issuer_cik — a
// synthetic broken identifier contract (a mis-mapped column / parser regression), to see what each
// option does when the claim fails in bulk rather than one record at a time.
const WINDOW = 10000;
// unit 'records': every violating record counts; 'items': only the first record of each distinct
// (identifier, incoming name) pair counts — one prolific filer with one typo'd registered name is
// one item, not a burst. minDecisions: decisions before the tolerance is evaluated at all.
function run(rows, { option, predicate, tolerance, mode = 'cumulative', inject = null, unit = 'records', minDecisions = MIN_DECISIONS }) {
  if (inject) rows = rows.map((r, i) => (i >= inject.start && i < inject.start + inject.n ? { ...r, owner_cik: r.issuer_cik, _injected: true } : r));
  const store = new IdentityStore(doc);
  const recent = []; // ring of 0/1 (violation) for the window mode
  const injected = { rows: 0, bound_silently: 0, bogus_persons_created: 0, deferred_violation: 0, deferred_inactive: 0 };
  let active = true;
  const stats = { bound: 0, deferred_violation: 0, deferred_rule_inactive: 0, not_fired: 0, decisions: 0 };
  const violations = [];          // one per violating record
  const steward = [];             // what the queue would hold (deduped per (cik, incoming name) at the end)
  const consolidation = [];       // reverse direction: Person would acquire a second CIK (informational)
  const homonyms = [];            // same name, different CIK, different issuer (Tier C territory; informational)
  let deactivated = null;
  const relationCounts = {};
  const seenItems = new Set(); let itemViolations = 0;
  rows.forEach((row, i) => {
    stats.decisions++;
    if (row._injected) injected.rows++;
    if (!active) {
      stats.deferred_rule_inactive++;
      if (row._injected) injected.deferred_inactive++;
      steward.push({ seq: i, reason: 'rule_deactivated', cik: row.owner_cik, name: row.owner_name, accession: row.accession });
      return;
    }
    const ctx = { store, predicate };
    const rec = record(row, ALIAS);
    const b = bindings(doc, rec, { verdict: 'person', ctx }).find((x) => x.rule_id === RULE);
    if (b.fires) {
      const cik = ctx.identifier.value;
      if (!ctx.person) {
        // fresh id: is there already a Person with this (issuer, name) under another CIK?
        for (const p of store.consolidationCandidates(NS, cik, row.issuer_cik, row.owner_name))
          consolidation.push({ seq: i, cik: row.owner_cik, name: row.owner_name, issuer_cik: row.issuer_cik, existing_person: p.id, existing_ciks: [...p.ids.get(NS)] });
        for (const p of store.homonyms(NS, cik, row.owner_name))
          if (![...p.issuers].includes(row.issuer_cik))
            homonyms.push({ seq: i, cik: row.owner_cik, name: row.owner_name, issuer_cik: row.issuer_cik, existing_person: p.id, existing_ciks: [...p.ids.get(NS)], existing_issuers: [...p.issuers] });
      } else if (ctx.relation && ctx.relation !== 'identical') {
        relationCounts[ctx.relation] = (relationCounts[ctx.relation] ?? 0) + 1; // absorbed as compatible (lenient only)
      }
      if (row._injected) { injected.bound_silently++; if (!ctx.person) injected.bogus_persons_created++; }
      store.bind(NS, cik, { name: row.owner_name, issuer: row.issuer_cik, seq: i });
      stats.bound++;
      recent.push(0); if (recent.length > WINDOW) recent.shift();
      return;
    }
    if (!ctx.violation) { stats.not_fired++; steward.push({ seq: i, reason: 'identifier_missing', accession: row.accession }); return; }
    // the claim would be violated: one CIK, a second Person (as far as the name can tell)
    stats.deferred_violation++;
    if (row._injected) injected.deferred_violation++;
    const itemKey = `${row.owner_cik}|${row.owner_name}`;
    const newItem = !seenItems.has(itemKey); if (newItem) { seenItems.add(itemKey); itemViolations++; }
    recent.push(unit === 'items' ? (newItem ? 1 : 0) : 1); if (recent.length > WINDOW) recent.shift();
    const vrec = { seq: i, accession: row.accession, period: row.period, corpus: row.corpus, cik: row.owner_cik, issuer_cik: row.issuer_cik,
      incoming_name: row.owner_name, names_on_person: ctx.violation.names_on_person, relation: ctx.violation.relation,
      cumulative_rate_per_10k: +(((stats.deferred_violation) / stats.decisions) * 1e4).toFixed(3) };
    violations.push(vrec);
    steward.push({ seq: i, reason: 'cardinality_violation', ...vrec });
    if (option === 'b') { active = false; deactivated = { at_decision: i + 1, ...vrec }; }
    if (option === 'c' && stats.decisions >= minDecisions) {
      const count = unit === 'items' ? itemViolations : stats.deferred_violation;
      const rate = mode === 'window' ? (recent.reduce((a, b) => a + b, 0) / recent.length) * 1e4 : (count / stats.decisions) * 1e4;
      if (rate > tolerance) { active = false; deactivated = { at_decision: i + 1, violations_so_far: stats.deferred_violation, rate_at_trip_per_10k: +rate.toFixed(3), ...vrec }; }
    }
  });
  // Steward queue as a Steward would see it: one item per (cik, incoming name), with a count
  const q = new Map();
  for (const s of steward) {
    if (s.reason !== 'cardinality_violation') continue;
    const k = `${s.cik}|${s.incoming_name}`;
    if (!q.has(k)) q.set(k, { cik: s.cik, incoming_name: s.incoming_name, names_on_person: s.names_on_person, relation: s.relation, first_seq: s.seq, records: 0 });
    q.get(k).records++;
  }
  const byCik = {}; const byIssuer = {};
  for (const x of violations) { byCik[x.cik] = (byCik[x.cik] ?? 0) + 1; byIssuer[x.issuer_cik] = (byIssuer[x.issuer_cik] ?? 0) + 1; }
  const decile = Array(10).fill(0);
  for (const x of violations) decile[Math.min(9, Math.floor((x.seq / rows.length) * 10))]++;
  return {
    option, predicate, tolerance: option === 'c' ? tolerance : null, mode: option === 'c' ? mode : null, unit: option === 'c' ? unit : null, min_decisions: option === 'c' ? minDecisions : null, inject,
    item_violations: itemViolations,
    ...stats, injected: inject ? injected : undefined,
    persons_created: store.persons.size,
    violation_rate_per_10k_decisions: +((stats.deferred_violation / stats.decisions) * 1e4).toFixed(3),
    distinct_ciks_violating: Object.keys(byCik).length,
    distinct_issuers_violating: Object.keys(byIssuer).length,
    violations_by_corpus_decile: decile,
    deactivated,
    steward_queue: { cardinality_items: [...q.values()], cardinality_records: stats.deferred_violation,
      rule_inactive_records: stats.deferred_rule_inactive, identifier_missing: stats.not_fired },
    consolidation_candidates: consolidation, homonym_candidates: homonyms,
    compatible_name_additions_absorbed: relationCounts,
    violations,
  };
}

const results = { _throwaway: 'research 07 binding run', corpus: { path: corpusPath, sha256: createHash('sha256').update(corpusBytes).digest('hex'), rows: all.length, person_rows: personRows.length }, rule: RULE, min_decisions_for_tolerance: MIN_DECISIONS, tolerances_per_10k: TOLERANCES, runs: [] };
for (const [orderName, sorter] of Object.entries(orders)) {
  const rows = sorter(personRows);
  for (const predicate of ['strict', 'lenient']) {
    results.runs.push({ order: orderName, ...run(rows, { option: 'a', predicate }) });
    results.runs.push({ order: orderName, ...run(rows, { option: 'b', predicate }) });
    for (const t of TOLERANCES) results.runs.push({ order: orderName, ...run(rows, { option: 'c', predicate, tolerance: t }) });
    for (const t of TOLERANCES) results.runs.push({ order: orderName, ...run(rows, { option: 'c', predicate, tolerance: t, mode: 'window' }) });
  }
}

// Tuned (c): count items not records, evaluate only after 10,000 decisions.
results.tuned = { note: 'option c with unit=items and min_decisions=10000, both orders, both predicates', runs: [] };
for (const [orderName, sorter] of Object.entries(orders)) {
  const rows = sorter(personRows);
  for (const predicate of ['strict', 'lenient'])
    for (const t of [1, 2, 5, 10, 20])
      for (const mode of ['cumulative', 'window'])
        results.tuned.runs.push({ order: orderName, ...run(rows, { option: 'c', predicate, tolerance: t, mode, unit: 'items', minDecisions: 10000 }) });
}

// Synthetic broken-contract scenario (accession order, both predicates): 2,000 rows starting at
// decision 40,000 carry the issuer's CIK as owner_cik. What does each option let through?
const INJECT = { start: 40000, n: 2000 };
results.injection = { scenario: INJECT, note: 'owner_cik := issuer_cik on rows [start, start+n): a mis-mapped identifier column', runs: [] };
{
  const rows = orders.accession(personRows);
  for (const predicate of ['strict', 'lenient']) {
    results.injection.runs.push(run(rows, { option: 'a', predicate, inject: INJECT }));
    results.injection.runs.push(run(rows, { option: 'b', predicate, inject: INJECT }));
    for (const t of [5, 20]) results.injection.runs.push(run(rows, { option: 'c', predicate, tolerance: t, inject: INJECT }));
    for (const t of [5, 20]) results.injection.runs.push(run(rows, { option: 'c', predicate, tolerance: t, mode: 'window', inject: INJECT }));
    for (const t of [2, 5]) for (const mode of ['cumulative', 'window'])
      results.injection.runs.push(run(rows, { option: 'c', predicate, tolerance: t, mode, unit: 'items', minDecisions: 10000, inject: INJECT }));
  }
}

// parity check with 07-measure.py's Python pre-sort: class of every multi-name CIK (first name vs each other)
const byCik = new Map();
for (const r of personRows) { if (!byCik.has(r.owner_cik)) byCik.set(r.owner_cik, new Map()); const m = byCik.get(r.owner_cik); m.set(r.owner_name, (m.get(r.owner_name) ?? 0) + 1); }
const classes = {};
for (const [cik, m] of byCik) {
  const names = [...m.entries()].sort((a, b) => b[1] - a[1]).map((x) => x[0]);
  const norm = new Set(names.map((n) => n.toUpperCase().replace(/&/g, ' AND ').replace(/[.,;:/()'"\-]/g, ' ').replace(/\s+/g, ' ').trim()));
  if (norm.size < 2) continue;
  let worst = 'identical';
  for (const o of names.slice(1)) { const rel = nameRelation(names[0], o, doc); if (RELATION_ORDER.indexOf(rel) > RELATION_ORDER.indexOf(worst)) worst = rel; }
  classes[worst] = (classes[worst] ?? 0) + 1;
}
results.js_presort_classes_of_multi_name_person_ciks = classes;

// keep the per-record violation lists and homonym lists only on the option (a) reference runs;
// every other run's list is a prefix of the same-order (a) list up to its deactivation point.
for (const r of [...results.runs, ...results.tuned.runs, ...results.injection.runs])
  if (r.option !== 'a') { delete r.violations; delete r.homonym_candidates; delete r.consolidation_candidates; }
writeFileSync(outPath, JSON.stringify(results, null, 1));
for (const r of results.runs) {
  const d = r.deactivated ? `deactivated at decision ${r.deactivated.at_decision} (cik ${r.deactivated.cik})` : 'never deactivated';
  console.log(`${r.order.padEnd(9)} ${r.predicate.padEnd(7)} ${r.option}${r.tolerance != null ? `@${r.tolerance}${r.mode === 'window' ? 'w' : ''}` : '   '}`.padEnd(30),
    `bound ${String(r.bound).padStart(6)}  deferred(viol) ${String(r.deferred_violation).padStart(4)}  deferred(inactive) ${String(r.deferred_rule_inactive).padStart(6)}  rate/10k ${String(r.violation_rate_per_10k_decisions).padStart(7)}  queue items ${String(r.steward_queue.cardinality_items.length).padStart(3)}  ${d}`);
}
console.log('js pre-sort classes:', JSON.stringify(classes));
console.log('\ntuned c (items, min 10,000):');
for (const r of results.tuned.runs) {
  const d = r.deactivated ? `deactivated at decision ${r.deactivated.at_decision} (cik ${r.deactivated.cik}, rate ${r.deactivated.rate_at_trip_per_10k})` : 'never deactivated';
  console.log(`${r.order.padEnd(9)} ${r.predicate.padEnd(7)} c@${r.tolerance}${r.mode === 'window' ? 'w' : ''}`.padEnd(30), `bound ${String(r.bound).padStart(6)}  items ${String(r.item_violations).padStart(3)}  records ${String(r.deferred_violation).padStart(4)}  ${d}`);
}
console.log('\ninjection scenario', JSON.stringify(INJECT));
for (const r of results.injection.runs) {
  const d = r.deactivated ? `deactivated at ${r.deactivated.at_decision}` : 'never deactivated';
  console.log(`${r.predicate.padEnd(7)} ${r.option}${r.tolerance != null ? `@${r.tolerance}${r.mode === 'window' ? 'w' : ''}${r.unit === 'items' ? ' items/10k' : ''}` : '   '}`.padEnd(26),
    `injected ${r.injected.rows}  bound silently ${String(r.injected.bound_silently).padStart(4)}  bogus persons ${String(r.injected.bogus_persons_created).padStart(4)}  deferred(viol) ${String(r.injected.deferred_violation).padStart(4)}  deferred(inactive) ${String(r.injected.deferred_inactive).padStart(4)}  ${d}`);
}
