// THROWAWAY PROTOTYPE — Mastering Policy Language, research 07 (ticket 07).
//
// A COPY of interpret.mjs (ticket 04) with the two binding primitives made real against
// a small in-memory identity store, so the deterministic Person Tier A rule
// (`person-tier-a-owner-cik`) can be run over the union corpus and the three Q2
// behaviours (defer / deactivate / defer-and-count) tried as switches. interpret.mjs
// itself is untouched so run-check.mjs stays reproducible. Classification paths are
// byte-identical to interpret.mjs; only `identifier_match@1`, `identifier_cardinality@1`,
// `holds`, `bindings` and the exported `IdentityStore` / `nameRelation` differ.
//
// What "violation" means here, and why a name is involved at all: binding by
// `owner_cik` alone can never contradict itself. The claim `max_identities: 1` ("one CIK,
// one Person") is only *testable* if a Person has a second handle — the normalized
// owner name. So `identifier_cardinality@1` compares the incoming record's name with the
// names already on the Person the CIK is bound to, and a "materially new" name is the
// candidate violation. Which name relations count as "materially new" is the
// `ctx.predicate` switch: 'strict' (any non-identical name) or 'lenient' (only relations
// the research-07 pre-sort could not explain as a variant / typo / nickname).
//
// The reverse direction (one Person, two CIKs) is NOT a violation of this rule
// (ticket 02 Answer #1: a Person holds any number of cross-reference ids). It is detected
// as `ctx.consolidation_candidate` and reported, never vetoed.

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

  // Binding primitives — real in this copy, against ctx.store (an IdentityStore).
  // identifier_match: the identifier is present and normalizes; records the lookup
  // result on ctx (bound Person or none). An unbound id still "matches" — creation is
  // the last outcome after matching (ticket 02 Answer #3), and the rule emits 'bind'.
  'identifier_match@1': (rec, args, doc, ctx) => {
    const norm = NORMALIZERS[args.normalizer];
    const id = norm ? norm(rec.get(args.field)) : String(rec.get(args.field) ?? '');
    if (!id) return false;
    if (!ctx?.store) return true; // static-check / no-store mode behaves like interpret.mjs
    ctx.identifier = { namespace: args.namespace, value: id };
    ctx.person = ctx.store.byIdentifier(args.namespace, id) ?? null;
    return true;
  },
  // identifier_cardinality: `max_identities` Persons per identifier value. Holds when the
  // id is unbound, or bound to a Person whose names are compatible with this record's
  // name under ctx.predicate. Otherwise records the violation on ctx and fails (veto).
  'identifier_cardinality@1': (rec, args, doc, ctx) => {
    if (!ctx?.store) return true;
    const p = ctx.person;
    if (!p) return true;
    const name = String(rec.get('owner_name') ?? '');
    const rel = ctx.store.worstRelation(p, name);
    ctx.relation = rel;
    const incompatible = ctx.predicate === 'strict' ? rel !== 'identical' : LENIENT_INCOMPATIBLE.has(rel);
    if (!incompatible) return true;
    ctx.violation = { person_id: p.id, identifier: ctx.identifier, relation: rel,
      names_on_person: [...p.rawNames], incoming_name: name };
    return false;
  },
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

function holds(call, rec, doc, ctx) {
  const fn = PRIMITIVES[call.primitive];
  if (!fn) throw new Error(`unknown primitive ${call.primitive}`);
  const v = fn(rec, call.args ?? {}, doc, ctx);
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

/** Which binding rules fire for a record, and whether each may bind automatically.
 *  `ctx` ({store, predicate}) is per-record scratch: the primitives write their lookup
 *  result / violation onto it, and the caller reads it back after the call. */
export function bindings(doc, rec, { verdict, ctx } = {}) {
  return (doc.rules ?? [])
    .filter((r) => r.family === 'binding')
    .filter((r) => !r.applies_to_verdict || !verdict || r.applies_to_verdict === verdict)
    .map((r) => ({
      rule_id: r.rule_id,
      fires: (r.when ?? []).every((c) => holds(c, rec, doc, ctx)),
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

// ---------------------------------------------------------------------------
// Research 07 additions: the name-relation pre-sort (a port of 07-measure.py's
// `name_relation`, same classes, same nickname map) and the in-memory identity store.
// ---------------------------------------------------------------------------

const NICKNAMES = {
  BOB: 'ROBERT', ROB: 'ROBERT', BOBBY: 'ROBERT', BILL: 'WILLIAM', WILL: 'WILLIAM', BILLY: 'WILLIAM',
  JIM: 'JAMES', JIMMY: 'JAMES', MIKE: 'MICHAEL', DICK: 'RICHARD', RICK: 'RICHARD', RICH: 'RICHARD',
  TOM: 'THOMAS', TOMMY: 'THOMAS', DAVE: 'DAVID', DAN: 'DANIEL', DANNY: 'DANIEL', STEVE: 'STEVEN',
  STEPHEN: 'STEVEN', ED: 'EDWARD', TED: 'EDWARD', EDDIE: 'EDWARD', CHRIS: 'CHRISTOPHER', CHUCK: 'CHARLES',
  CHARLIE: 'CHARLES', JOE: 'JOSEPH', JOEY: 'JOSEPH', TONY: 'ANTHONY', ANDY: 'ANDREW', DREW: 'ANDREW',
  MATT: 'MATTHEW', PAT: 'PATRICK', PATTY: 'PATRICIA', PEGGY: 'MARGARET', MEG: 'MARGARET', BETH: 'ELIZABETH',
  LIZ: 'ELIZABETH', BETTY: 'ELIZABETH', SUE: 'SUSAN', KATE: 'KATHERINE', KATHY: 'KATHERINE', KATIE: 'KATHERINE',
  CATHY: 'CATHERINE', JEN: 'JENNIFER', JENNY: 'JENNIFER', JACK: 'JOHN', JOHNNY: 'JOHN', JON: 'JONATHAN',
  NICK: 'NICHOLAS', GREG: 'GREGORY', JEFF: 'JEFFREY', GEOFF: 'GEOFFREY', KEN: 'KENNETH', KENNY: 'KENNETH',
  LARRY: 'LAWRENCE', TIM: 'TIMOTHY', SAM: 'SAMUEL', BEN: 'BENJAMIN', ALEX: 'ALEXANDER', FRED: 'FREDERICK',
  HANK: 'HENRY', HARRY: 'HENRY', RON: 'RONALD', RONNIE: 'RONALD', DON: 'DONALD', DONNIE: 'DONALD', RAY: 'RAYMOND',
  PHIL: 'PHILIP', PHILLIP: 'PHILIP', LEN: 'LEONARD', LEO: 'LEONARD', GENE: 'EUGENE', ART: 'ARTHUR', BRAD: 'BRADLEY',
  DOUG: 'DOUGLAS', GABE: 'GABRIEL', HERB: 'HERBERT', JERRY: 'GERALD', TERRY: 'TERENCE', VINCE: 'VINCENT',
  WALT: 'WALTER', ZACH: 'ZACHARY', ABE: 'ABRAHAM', MAX: 'MAXIMILIAN', NATE: 'NATHAN', NATHANIEL: 'NATHAN',
  STAN: 'STANLEY', JOSH: 'JOSHUA', MARTY: 'MARTIN', NORM: 'NORMAN', RANDY: 'RANDALL', RUSS: 'RUSSELL',
  SANDY: 'SANDRA', DEBBIE: 'DEBORAH', DEB: 'DEBORAH', BARB: 'BARBARA', TRISH: 'PATRICIA', CINDY: 'CYNTHIA',
  MANDY: 'AMANDA', BECKY: 'REBECCA', VICKI: 'VICTORIA', TINA: 'CHRISTINA', CHRISTINE: 'CHRISTINA', MOLLY: 'MARY',
  POLLY: 'MARY', JAKE: 'JACOB', JOSE: 'JOSEPH', GUS: 'AUGUSTUS', LOU: 'LOUIS', LEW: 'LEWIS', AL: 'ALBERT',
  BERT: 'ALBERT', BERNIE: 'BERNARD', CAL: 'CALVIN', CLIFF: 'CLIFFORD', DUKE: 'MARMADUKE', ELI: 'ELIJAH',
  FRANK: 'FRANCIS', FRANKIE: 'FRANCIS', HAL: 'HAROLD', HOWIE: 'HOWARD', IKE: 'ISAAC', JEB: 'JEBEDIAH', JOEL: 'JOEL',
  MANNY: 'MANUEL', MEL: 'MELVIN', MITCH: 'MITCHELL', MORT: 'MORTIMER', NED: 'EDWARD', OLLIE: 'OLIVER',
  OZZIE: 'OSWALD', PETE: 'PETER', RALPH: 'RAPHAEL', REG: 'REGINALD', ROD: 'RODNEY', ROGER: 'ROGER', SID: 'SIDNEY',
  SOL: 'SOLOMON', SY: 'SEYMOUR', TEDDY: 'THEODORE', THEO: 'THEODORE', VIC: 'VICTOR', WES: 'WESLEY', WOODY: 'WOODROW',
};

export const RELATION_ORDER = ['identical', 'variant_subset', 'variant_reorder_or_middle', 'typo_or_prefix',
  'suffix_differs', 'one_shared_other_token', 'one_shared_first_token', 'one_near_token',
  'entity_vs_person_name', 'no_overlap'];
const SEVERITY = Object.fromEntries(RELATION_ORDER.map((c, i) => [c, i]));
// 'lenient' veto: relations the research-07 pre-sort could not explain as variant/typo/nickname.
export const LENIENT_INCOMPATIBLE = new Set(['suffix_differs', 'one_shared_other_token', 'one_shared_first_token',
  'one_near_token', 'entity_vs_person_name', 'no_overlap']);

const normName = NORMALIZERS['normalize_text@edgar-conformed-v1'];

function canonTokens(name, suffixes) {
  const toks = normName(name).split(' ').filter(Boolean);
  const suf = toks.filter((t) => suffixes.has(t));
  const rest = toks.filter((t) => !suffixes.has(t));
  const full = rest.filter((t) => t.length > 1).map((t) => NICKNAMES[t] ?? t);
  const init = rest.filter((t) => t.length === 1);
  return { full, init, suf };
}
const subset = (a, b) => [...a].every((x) => b.has(x));
const initialsCompatible = (init, full) => { const f = new Set(full.map((t) => t[0])); return init.every((i) => f.has(i)); };
const near = (x, y) => {
  if (x.length < 4 || y.length < 4) return false;
  if (x.startsWith(y.slice(0, 4)) || y.startsWith(x.slice(0, 4))) return true;
  let d = 0; for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) d++;
  return d + Math.abs(x.length - y.length) <= 2;
};

/** Port of 07-measure.py `name_relation(a, b)`; `doc` supplies the token and suffix lists. */
export function nameRelation(a, b, doc) {
  if (normName(a) === normName(b)) return 'identical';
  const list = doc.lists.entity_legal_form;
  const ea = tokensFound(a, list, normName), eb = tokensFound(b, list, normName);
  if ((ea.length > 0) !== (eb.length > 0)) return 'entity_vs_person_name';
  const suffixes = new Set(doc.lists.person_suffix);
  const A = canonTokens(a, suffixes), B = canonTokens(b, suffixes);
  const SA = new Set(A.full), SB = new Set(B.full);
  const shared = [...SA].filter((x) => SB.has(x));
  const sameSuf = A.suf.length === B.suf.length && A.suf.every((s) => B.suf.includes(s));
  if (!sameSuf && shared.length && (subset(SA, SB) || subset(SB, SA) || shared.length >= 2)) return 'suffix_differs';
  if ((subset(SA, SB) && initialsCompatible(A.init, B.full)) || (subset(SB, SA) && initialsCompatible(B.init, A.full))) return 'variant_subset';
  if (shared.length >= 2) return 'variant_reorder_or_middle';
  if (shared.length === 1) {
    const t = shared[0];
    return A.full.indexOf(t) === 0 && B.full.indexOf(t) === 0 ? 'one_shared_first_token' : 'one_shared_other_token';
  }
  let nears = 0; for (const x of SA) for (const y of SB) if (near(x, y)) nears++;
  if (nears >= 2 || (nears >= 1 && (initialsCompatible(A.init, B.full) || initialsCompatible(B.init, A.full)) && (A.init.length || B.init.length))) return 'typo_or_prefix';
  if (nears === 1) return 'one_near_token';
  return 'no_overlap';
}

/** Minimal identity store: Persons, their cross-reference ids, their names, their issuers. */
export class IdentityStore {
  constructor(doc) {
    this.doc = doc;
    this.persons = new Map();      // id -> {id, ids: Map<namespace, Set<value>>, names: Set, rawNames: Set, issuers: Set, firstSeen}
    this.index = new Map();        // `${namespace}:${value}` -> person id
    this.byIssuerName = new Map(); // `${issuer}|${normName}` -> Set<person id>
    this.byName = new Map();       // normName -> Set<person id>
    this.next = 1;
  }
  byIdentifier(ns, value) { const id = this.index.get(`${ns}:${value}`); return id ? this.persons.get(id) : undefined; }
  worstRelation(person, name) {
    let worst = 'identical';
    for (const raw of person.rawNames) {
      const rel = nameRelation(raw, name, this.doc);
      if (SEVERITY[rel] > SEVERITY[worst]) worst = rel;
    }
    return worst;
  }
  /** Persons that already carry this (issuer, name) under a *different* identifier value. */
  consolidationCandidates(ns, value, issuer, name) {
    const out = [];
    for (const pid of this.byIssuerName.get(`${issuer}|${normName(name)}`) ?? []) {
      const p = this.persons.get(pid);
      if (!(p.ids.get(ns)?.has(value))) out.push(p);
    }
    return out;
  }
  homonyms(ns, value, name) {
    const out = [];
    for (const pid of this.byName.get(normName(name)) ?? []) {
      const p = this.persons.get(pid);
      if (!(p.ids.get(ns)?.has(value))) out.push(p);
    }
    return out;
  }
  /** Bind a record to the Person its identifier resolves to, creating one if unbound. */
  bind(ns, value, { name, issuer, seq }) {
    let p = this.byIdentifier(ns, value);
    if (!p) {
      p = { id: `P${this.next++}`, ids: new Map([[ns, new Set([value])]]), names: new Set(), rawNames: new Set(), issuers: new Set(), firstSeen: seq };
      this.persons.set(p.id, p);
      this.index.set(`${ns}:${value}`, p.id);
    }
    const nn = normName(name);
    p.names.add(nn); p.rawNames.add(name); p.issuers.add(issuer);
    const k1 = `${issuer}|${nn}`;
    if (!this.byIssuerName.has(k1)) this.byIssuerName.set(k1, new Set());
    this.byIssuerName.get(k1).add(p.id);
    if (!this.byName.has(nn)) this.byName.set(nn, new Set());
    this.byName.get(nn).add(p.id);
    return p;
  }
}
