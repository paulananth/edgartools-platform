// THROWAWAY PROTOTYPE — Mastering Policy Language, ticket 04.
//
// The question this answers: can a policy document written in the twelve-primitive
// vocabulary (research 03) express rule C-J and the Person/Company binding rules,
// and does a machine reading that document reproduce research 18's measured result?
//
// This module is the part worth keeping if the answer is yes: a pure interpreter,
// no DOM, no I/O. The page and the checker call into it; nothing flows back.

// ---------------------------------------------------------------------------
// Primitive registry. `name@version` — an unknown pair is refused, fail closed.
// Only the primitives the two prototype documents actually call are implemented.
// ---------------------------------------------------------------------------

const NORMALIZERS = {
  'normalize_text@edgar-conformed-v1': (s) =>
    String(s ?? '')
      .toUpperCase()
      .replace(/&/g, ' AND ')
      .replace(/[.,;:/()'"\-]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim(),
  'normalize_identifier@sec-cik-v1': (s) =>
    String(s ?? '').replace(/\D/g, '').replace(/^0+/, ''),
  'normalize_identifier@crd-v1': (s) => String(s ?? '').replace(/\D/g, ''),
  'normalize_identifier@lei-v1': (s) => String(s ?? '').toUpperCase().replace(/[^A-Z0-9]/g, ''),
};

const isEmpty = (v) =>
  v === null || v === undefined || v === '' || v === 0 ||
  (Array.isArray(v) && v.length === 0) ||
  (typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0);

// token_match: which entries of a declared list appear in a normalized name as
// whole tokens. `&` is its own signal in EDGAR conformed names (it normalizes to
// ' AND '), so the list carries "AND" and the ampersand adds one synthetic token.
function tokensFound(rawName, list, normalize) {
  const n = normalize(rawName);
  const found = new Set();
  const padded = ` ${n} `;
  for (const t of list) {
    if (t === 'AND') continue;
    const tok = t.replace(/\s+/g, ' ');
    const re = new RegExp(`(?<![A-Z0-9])${tok.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Z0-9])`);
    if (re.test(n)) found.add(t);
  }
  if (String(rawName ?? '').includes('&') && padded.includes(' AND ')) found.add('&');
  return [...found].sort();
}

const PRIMITIVES = {
  'evidence_present@1': (rec, args) => !isEmpty(rec.get(args.document)),

  'field_in_set@1': (rec, args) => args.values.includes(rec.get(args.field)),

  'token_match@1': (rec, args, doc) => {
    const list = doc.lists[args.token_list] ?? [];
    const exclude = new Set(args.exclude_list ? doc.lists[args.exclude_list] ?? [] : []);
    const norm = NORMALIZERS[doc.normalizers[args.normalizer] ?? args.normalizer];
    let found = tokensFound(rec.get(args.field), list, norm);
    if (exclude.size) found = found.filter((t) => !exclude.has(t));
    const n = found.length;
    if (args.min_count !== undefined && n < args.min_count) return false;
    if (args.max_count !== undefined && n > args.max_count) return false;
    return true;
  },

  // Raw-text checks (digits, '&') run on the ORIGINAL string, tokenization on the
  // normalized one — research 03 §6 flagged that collapsing this kills both checks.
  'name_shape@1': (rec, args, doc) => {
    const raw = String(rec.get(args.field) ?? '').trim();
    if (!raw) return false;
    for (const ch of args.forbid_characters?.value ?? []) if (raw.includes(ch)) return false;
    if (args.forbid_digits?.value && /\d/.test(raw)) return false;
    const norm = NORMALIZERS[doc.normalizers[args.normalizer] ?? args.normalizer];
    const toks = norm(raw).split(/[\s,]+/).filter(Boolean);
    if (toks.length < args.min_tokens || toks.length > args.max_tokens) return false;
    const suffixes = new Set(doc.lists[args.suffix_list] ?? []);
    if (toks.filter((t) => !suffixes.has(t)).length < 2) return false;
    return toks.every((t) => /^[A-Z]+$/.test(t));
  },

  'fields_all_empty@1': (rec, args, doc) => {
    const fields = Array.isArray(args.fields) ? args.fields : doc.lists[args.fields] ?? [];
    return fields.every((f) => isEmpty(rec.get(f)));
  },

  // Binding primitives. The prototype's checker does not exercise these (they need
  // a populated identity store); they are here so the documents parse and so the
  // static checks below have something to inspect.
  'identifier_match@1': (rec, args) => !isEmpty(rec.get(args.field)),
  'identifier_cardinality@1': () => true,
  'compound_key_equal@1': (rec, args) =>
    args.components.every((c) => !isEmpty(rec.get(c.field))),
  'name_similarity@1': () => false,
  'select_by_source_rank@1': () => true,
};

// ---------------------------------------------------------------------------
// Static checks performed at registration — research 03 §4. Fail closed.
// ---------------------------------------------------------------------------

const SURVIVORSHIP_PRIMITIVES = new Set(['select_by_source_rank@1']);

export function validate(doc) {
  const errors = [];
  const seen = new Set();

  const checkCall = (call, where) => {
    if (!PRIMITIVES[call.primitive]) errors.push(`${where}: unknown primitive ${call.primitive}`);
    seen.add(call.primitive);
  };

  for (const rule of doc.rules ?? []) {
    const calls = rule.family === 'classification'
      ? (rule.steps ?? []).flatMap((s) => s.when ?? [])
      : rule.when ?? [];
    calls.forEach((c) => checkCall(c, rule.rule_id));

    if (rule.family === 'binding') {
      // A binding rule may not reach a survivorship primitive (CONTEXT.md:23,51).
      for (const c of calls) {
        if (SURVIVORSHIP_PRIMITIVES.has(c.primitive))
          errors.push(`${rule.rule_id}: a binding rule may not call ${c.primitive}`);
      }
      // A binding rule may not decide on name similarity alone (GLEIF spec:95).
      const sims = calls.filter((c) => c.primitive.startsWith('name_similarity@'));
      if (sims.length && sims.length === calls.length && rule.emits?.includes('bind'))
        errors.push(`${rule.rule_id}: name similarity alone may not bind`);
    }
  }

  // Every activation entry must name a rule at that exact version and a verdict
  // the rule emits, and must clear its family's declared bar at equal coverage.
  for (const a of doc.automatic_rules ?? []) {
    const rule = (doc.rules ?? []).find((r) => r.rule_id === a.rule_id);
    if (!rule) { errors.push(`activation ${a.rule_id}: no such rule`); continue; }
    if (rule.version !== a.rule_version)
      errors.push(`activation ${a.rule_id}: proof measured on version ${a.rule_version}, rule is ${rule.version}`);
    if (!(rule.emits ?? []).includes(a.verdict))
      errors.push(`activation ${a.rule_id}: rule does not emit verdict ${a.verdict}`);
    const bar = doc.bars?.[rule.family];
    if (!bar) { errors.push(`activation ${a.rule_id}: no bar declared for family ${rule.family}`); continue; }
    if (bar.one_sided_confidence !== a.proof.one_sided_confidence)
      errors.push(`activation ${a.rule_id}: proof coverage ${a.proof.one_sided_confidence} != bar coverage ${bar.one_sided_confidence}`);
    const lb = wilsonLowerBound(a.proof.n, a.proof.correct, a.proof.one_sided_confidence);
    if (Math.abs(lb - a.proof.lower_bound) > 0.0005)
      errors.push(`activation ${a.rule_id}: stated lower bound ${a.proof.lower_bound}, recomputed ${lb.toFixed(4)}`);
    if (lb < bar.min_precision)
      errors.push(`activation ${a.rule_id}: lower bound ${lb.toFixed(4)} below bar ${bar.min_precision}`);
  }
  return { ok: errors.length === 0, errors, primitives_used: [...seen].sort() };
}

export function wilsonLowerBound(n, correct, oneSided) {
  const z = oneSided === 0.975 ? 1.959963985 : oneSided === 0.95 ? 1.644853627 : NaN;
  if (!n || Number.isNaN(z)) return NaN;
  const p = correct / n;
  const d = 1 + (z * z) / n;
  const c = p + (z * z) / (2 * n);
  const s = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return (c - s) / d;
}

// ---------------------------------------------------------------------------
// Evaluation. A record is anything with .get(path).
// ---------------------------------------------------------------------------

function holds(call, rec, doc) {
  const fn = PRIMITIVES[call.primitive];
  if (!fn) throw new Error(`unknown primitive ${call.primitive}`);
  const v = fn(rec, call.args ?? {}, doc);
  return call.negate ? !v : v;
}

/** Run a classification rule. Returns {verdict, step, trace, automatic}. */
export function classify(doc, ruleId, rec) {
  const rule = doc.rules.find((r) => r.rule_id === ruleId && r.family === 'classification');
  if (!rule) throw new Error(`no classification rule ${ruleId}`);
  const trace = [];
  for (const step of rule.steps) {
    const results = (step.when ?? []).map((c) => ({
      primitive: c.primitive, negate: !!c.negate, args: c.args, held: holds(c, rec, doc),
    }));
    const all = results.every((r) => r.held);
    trace.push({ step: step.step, verdict: step.verdict, note: step.note, results, fired: all });
    if (all) {
      const active = (doc.automatic_rules ?? []).some(
        (a) => a.rule_id === rule.rule_id && a.rule_version === rule.version && a.verdict === step.verdict);
      return { verdict: step.verdict, step: step.step, trace, automatic: active };
    }
  }
  return { verdict: 'deferred', step: null, trace, automatic: false };
}

/** Which binding rules fire for a record, and whether each may bind automatically. */
export function bindings(doc, rec, { verdict } = {}) {
  return (doc.rules ?? [])
    .filter((r) => r.family === 'binding')
    .filter((r) => !r.applies_to_verdict || !verdict || r.applies_to_verdict === verdict)
    .map((r) => ({
      rule_id: r.rule_id,
      fires: (r.when ?? []).every((c) => holds(c, rec, doc)),
      emits: r.emits,
      automatic: (doc.automatic_rules ?? []).some(
        (a) => a.rule_id === r.rule_id && a.rule_version === r.version && a.verdict === 'bind'),
      note: r.note,
    }));
}

export const record = (obj, alias = {}) => ({
  get: (path) => (path in alias ? obj[alias[path]] : obj[path]),
  raw: obj,
});
