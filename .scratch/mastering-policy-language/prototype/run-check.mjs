// THROWAWAY PROTOTYPE — Mastering Policy Language, ticket 04.
//
// The verdict run. Reads the Person policy document, validates it the way a
// registration would, then evaluates rule C-J *from the document* over research
// 18's real data and compares with the measured result.
//
//   node run-check.mjs
//
// Expected, if the language is expressive enough: 841/841 on the person arm,
// 353/353 on the entity arm, and the same deferral counts research 18 reports.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { validate, classify, bindings, record } from './interpret.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, '..', '..', '..');
const research = join(repo, '.scratch', 'person-consumer-contract', 'research');

const person = JSON.parse(readFileSync(join(here, 'policy-person.json'), 'utf8'));
const company = JSON.parse(readFileSync(join(here, 'policy-company.json'), 'utf8'));

// The document addresses fields by path; research 18's rows use its own names.
// In production this mapping is the dataset contract's adapter block.
const ALIAS = {
  'sec.submissions.owner': 'sub_present',
  'sec.submissions.entityType': 'entity_type',
  'sec.submissions.sic': 'sic',
  'sec.submissions.stateOfIncorporation': 'state_of_incorporation',
  'sec.submissions.ein': 'ein',
  'sec.submissions.tickers': 'n_tickers',
  'sec.submissions.ownerOrg': 'owner_org',
  'sec.submissions.fiscalYearEnd': 'fiscal_year_end',
  owner_name: 'owner_name',
  owner_cik: 'owner_cik',
};

const lines = (f) =>
  readFileSync(join(research, f), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));

// ---- 1. registration ------------------------------------------------------
for (const [name, doc] of [['person', person], ['company', company]]) {
  const v = validate(doc);
  console.log(`registration: ${name} ${v.ok ? 'ACCEPTED' : 'REFUSED'}`);
  v.errors.forEach((e) => console.log(`  ! ${e}`));
  console.log(`  primitives used: ${v.primitives_used.join(', ')}`);
}

// ---- 2. the refusals a registration must make -----------------------------
const mutate = (o) => JSON.parse(JSON.stringify(o));
const cases = [
  ['rule edited after its proof', (d) => { d.rules[0].version = '2026-09-21'; }],
  ['bar raised above the proof', (d) => { d.bars.classification.min_precision = 0.999; }],
  ['proof at a different coverage', (d) => { d.automatic_rules[0].proof.one_sided_confidence = 0.95; }],
  ['fabricated lower bound', (d) => { d.automatic_rules[0].proof.lower_bound = 0.9999; }],
  ['activating a verdict the rule cannot emit', (d) => { d.automatic_rules[0].verdict = 'fund'; }],
  ['binding on name similarity alone', (d) => {
    d.rules.push({ rule_id: 'bad', version: '1', family: 'binding', emits: ['bind'],
      when: [{ primitive: 'name_similarity@1', args: { min_score: 0.9 } }] });
  }],
];
console.log('\nrefusals a registration must make:');
for (const [label, mut] of cases) {
  const d = mutate(person); mut(d);
  const v = validate(d);
  console.log(`  ${v.ok ? 'MISSED  ' : 'refused '} ${label}${v.ok ? '' : ` — ${v.errors[0]}`}`);
}

// ---- 3. reproduce research 18 --------------------------------------------
const sample = lines('18-sample.jsonl');
const owners = lines('18-owners.jsonl');

const arms = {};
let uncertain = 0;
for (const row of sample) {
  if (row.uncertain) uncertain++; // research 18 keeps these, with their resolved label
  const { verdict, automatic } = classify(person, 'C-J', record(row, ALIAS));
  const arm = verdict === 'person' ? 'person' : verdict === 'deferred' ? 'deferred'
    : 'entity';
  const truth = row.label; // 'person' | 'entity'
  arms[arm] ??= { n: 0, correct: 0, automatic: 0 };
  arms[arm].n++;
  if (automatic) arms[arm].automatic++;
  if (arm !== 'deferred' && arm === truth) arms[arm].correct++;
}

console.log('\nrule C-J, evaluated from the document over research 18\'s labeled sample:');
console.log(`  labeled rows: ${sample.length} (${uncertain} marked uncertain, kept with their resolved label)`);
for (const [arm, s] of Object.entries(arms)) {
  const prec = arm === 'deferred' ? '—' : `${s.correct}/${s.n} = ${(s.correct / s.n * 100).toFixed(2)}%`;
  console.log(`  ${arm.padEnd(9)} n=${String(s.n).padStart(4)}  precision ${prec}   automatic: ${s.automatic}`);
}
console.log('  research 18 (C-J): person 841/841, entity 353/353, deferred 26 of 1,220');

// whole population, for the deferral cost
const pop = {};
for (const row of owners) {
  const { verdict } = classify(person, 'C-J', record(row, ALIAS));
  pop[verdict] = (pop[verdict] ?? 0) + 1;
}
const total = owners.length;
console.log('\n  whole corpus (rows, not distinct owners):');
for (const [v, n] of Object.entries(pop).sort((a, b) => b[1] - a[1]))
  console.log(`    ${v.padEnd(20)} ${String(n).padStart(5)}  ${(n / total * 100).toFixed(1)}%`);

// ---- 4. binding rules fire, and only the proven ones bind alone -----------
const someone = record(owners.find((r) => r.owner_cik && r.person_name_shape), ALIAS);
console.log('\nbinding rules for one person record:');
for (const b of bindings(person, someone, { verdict: 'person' }))
  console.log(`  ${b.fires ? 'fires ' : 'quiet '} ${b.rule_id.padEnd(32)} ${b.automatic ? 'AUTOMATIC' : 'review'}`);
