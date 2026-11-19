# History, as-of questions and corrections in a Gold model

Read this when a Gold design must answer "as of", "at the time", "what did we know then", must keep a dimension's history,
or must correct a value. It adds the anchor-modeling author's published practice to [DIMENSIONAL.md](DIMENSIONAL.md)'s
history types and [SKILL.md](SKILL.md)'s two times. The practices are one author's positions with their reasons, not
laws; the figures were measured on one database and one data set each (a row-store and a massively parallel column
store) and show the kind of effect to look for, never what this platform's database will do. Measure before relying on one.

## Five kinds of time, and where each lives

| Kind | Means | Here |
|---|---|---|
| Appearance time (valid, effective) | Since when a value or relationship holds in the domain | Business time: a master version's valid-from, a report's period |
| Assertion time | When someone asserted or assessed a statement | A restated or amended report's own date |
| Recording time | When a system stored it | Recorded time: when the platform learned it (the mirror, the load) |
| Happening time | When a domain event occurred or is scheduled | An ordinary date attribute (an order date, a birth date), never the version's valid-from |
| Structuring time | When the model had this shape | The rules or mapping version, not a timestamp on a value |

- A column that holds a date is not automatically one of these: a happening date is an attribute. If it is itself
  corrected, that is a change of the attribute's value.
- Keep the kinds apart; if one timestamp stands in for another, label the proxy and what it cannot say.
- Store times that order things in UTC, never local time or a time of day alone; convert at the edge. Make the precision
  finer than the shortest gap between two events of one identity, and no finer than the source states: a date-only source
  needs a date column.
- Choose the least history that answers the questions: one time axis when changing time is enough, two when past
  assertions must be answerable, a position per asserter only when separately attributed assertions are required.

## Unknown, ended, retracted, absent

- Unknown has no value, and no stand-in. Where the business acts on not knowing (an order with an open delivery date),
  give the code an explicit value; where nobody does, leave it out.
- An ended fact is a change in the domain: record the end, keep the earlier history. A retraction withdraws a claim; it
  does not say when the fact ended in the world.
- **Absence from a snapshot is not evidence** of an end, a delete or a timestamp. Ask what the source guarantees.
- **The ABA problem.** A snapshot cannot tell "A, then B, then A" from "A throughout" when both fall between two loads.
  If the questions need those changes, ask the source for change times, deltas or an audit log; no model recovers them.
- When a source gives no change time, a stable observation time (the first load or extract) may stand in: keep the real
  recording time separately, never recompute the proxy on a retry, and say how far it can lag.

## Corrections never overwrite

A mistake is corrected by retracting the wrong version and asserting the right one, never by updating in place: both stay
queryable ("what was true" and "what did we believe that day"). Restating what is already asserted changes nothing. Two
different reliabilities for one statement by one asserter at one moment contradict each other and the load must not make
them. When identity is uncertain, keep the candidates with a weight and correct later; a count then weights by reliability,
not by rows. This is why an append fact stays append (GOLD.md): a later correction is a new row.

## The three questions a dimension must answer

| Question | Means | Answer |
|---|---|---|
| Today is yesterday (TIY) | Facts show the current value of an attribute | Join to the current master (type 1) |
| Yesterday is today (YIT) | Facts show the value as of a chosen date | One as-of cut of the master's versions, then an ordinary join |
| Today or yesterday (TOY) | Each fact shows the value in effect when it happened | An as-of join from each fact's date to the versions (below) |

One benchmark of a design where a dimension is an immutable key table plus insert-only history tables, against the
slowly changing types, on about fifty million facts: type 1 and 3 cannot answer YIT; type 2 answers TIY, YIT and TOY but
rewrites or stores a key per fact, so loading its facts was several times slower; types 5 and 7 were far slower to write
facts; the temporal design wrote fastest and answered all three. Read it as direction. The rules it supports:

- **History stays in the master's versions; a Gold dimension is cut from them for a time or a range of times.** Do not
  store a "valid from" on the fact to answer TOY: it only halved the time in the test, enlarges the fact and is wrong if
  that version is later corrected.
- Avoid types 5 and 7 where loads arrive often: their updates find the version in effect, then rewrite rows.
- Where the version in effect must be found at load time, use the as-of join below there too.

## As-of joins

*For each fact row, the version in effect at its date.*

- **The date is a constant** ("as of a quarter end"): reduce each history table to its row in effect, then join normally.
  In an outer join say why a value is missing (no history for the identity, history that starts after the date, or a null
  date) instead of leaving a bare null.
- **The date comes from the fact** (a temporal dependent join). First try the direct forms: derive each version's end
  with `LEAD(valid_from, 1, end_of_time) OVER (PARTITION BY id ORDER BY valid_from)` and join on `valid_from <= t AND
  valid_to > t`; or an inequality join then keep the latest row. Optimizers plan inequality joins poorly on long histories
  (one was cancelled after hours).
- **The twine** replaces the inequality join with one ordered pass: tag each row with the timeline it came from, put the
  history rows and the fact rows on one line sorted by (identity, time), and carry the latest history time forward with a
  conditional running `MAX`; then one exact key lookup per fact row. No end dates are needed, which suits insert-only
  tables. Variants: one fact row per identity and many versions, take the preceding row's value with `LAG`; many fact rows per identity, the running `MAX`; several
  histories in one pass, one timeline number each, cast every time column to the most granular type first.
- Rules for any of them: one row per identity and time in both inputs or rows join twice; a version starting at `t` counts
  at `t` (history rows sort first at equal times, make the order explicit); the cost is the sort, so a key of (identity,
  time) on the history helps; test the result against the direct form on a sample before trusting it.

## Keys and identity

- An identity is a meaningless surrogate, assigned in one place; a natural or source key is a way to find it. The master
  id already is one. **Do not hash a natural key to make an identity**: a corrected key makes a new identity, every key
  and join pays the width, and nothing is gained since the natural key is already stored. A hash is for a cheap comparison of
  long values (change detection, uniqueness), never the identity.
- A hash computed from the grain's natural key is a convenience for a fact's own row key, never a dimension's identity.
- Where a key can change or be reused, match at the relevant time, not against any or the latest version, scope the match
  by namespace, and stop on an ambiguous match.

## Layers and where a Gold table earns its place

The author argues that each persisted layer between landing and the business-facing model is a cost of upkeep for the
people who maintain it: ask what each buys, count what it costs, and keep the ones that can be justified; and that a
mart is a simplified copy of a richer model, so a semantic layer over views with business names and descriptions serves
people and agents better. His own reporting warehouse still built denormalized marts where business users did not want
full history, and his claims about speed are impressions, not measurements. Apply it as a test, not a ruling:

- A Gold table that is only a pass-through of a mirror table is a layer that buys nothing: read the mirror (GOLD.md).
- Business rules are descriptive: what things are and when. How they are interpreted (a customer, active, a margin) lives in
  views and the semantic layer, so a changed definition is a changed view, not a rebuild.
- A question like "how many customers" has several answers (as of when, by which definition, counting which identity):
  state the definition in the answer, put the agreed definition in a view once, and state the cutoff the answer uses.
- Descriptions on every table and column are what lets an agent read the model without guessing.

## When many narrow tables win, and when they do not

One experiment compared a fully normalized, historized model queried through its latest view with a wide table of the same
data: the narrow model won (up to about fourteen times on few attributes with conditions, ten million rows) when history is
kept, data is sparse, values repeat (a small shared list), and queries read few attributes with conditions; it lost
(two to twenty-six times slower) on queries that read every attribute with no condition, and was larger when values are tiny.
It depends on declared keys and table elimination, and on a recent optimizer. It covered one database, one machine, one
entity. Gold's wide reads therefore stay a mart of the star, and a narrow-table model is not adopted for Gold.

## Examples

- A row-store and a massively parallel column store: one benchmark each; the parallel store segmented every attribute of an
  anchor by its identity, duplicated a tie once per role and replicated each knot, and beat a spilled third-normal-form
  join but not an in-memory one.
- The author's anchor modeling skill (an installable agent skill with generators for six databases) is the tool if an
  anchor model is ever chosen: github.com/paulananth/anchor-modeling-skill. Nothing here depends on it.
