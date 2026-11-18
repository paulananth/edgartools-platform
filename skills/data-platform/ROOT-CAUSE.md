# Find the root cause: five whys, silently

Part of the `data-platform` skill. The data skills (operate, onboard, refine, profile, quality, journal, bookkeeping) link it where
they handle a failure or a surprise; none copies it.

A result that surprises, a step that fails, two readings that disagree, or a fix that would treat a symptom is not
finished until its root cause is found. Run the whys yourself. The operator reads the conclusion, never the chain: do not
narrate each why, and do not ask the operator what a log, a query, a test or the code can answer.

## When

- a step, load or check fails (more than once, or in a way the message does not explain);
- a number surprises or disagrees with another (a step that reads idle while its store takes rows; a count that does not
  match its source);
- a retry, a larger window or a restart is about to be the fix;
- a fix you made makes the symptom go away but you cannot say why it was there.

## How

1. **Doubt the instrument first.** When two readings disagree, one tool is wrong before anything is broken. Ask what the
   reading counts and what it cannot see (a matcher that finds a process by its command line misses one that has none; a
   statistic flushed at commit shows nothing during a long transaction). Check the tool against a second source.
2. **Ask why, and answer each why from evidence**: a log line, a measurement, a query, the code. A why answered "probably"
   is not answered; test it by observing or changing the thing it names.
3. **Stop when the answer is a fact you can change** that, once changed, makes the symptom impossible: a missing grant, a
   design that holds a whole input in memory, a rule that was never written down. An answer that is another symptom
   ("the step is slow", "the retry failed again") is not the end. Three to five whys is usual; more is allowed, fewer is
   fine when the cause is plain.
4. **Fix the cause, not the instance.** Write the test that fails on the old behaviour, change the root, and run the case that
   showed it. Retrying, raising a limit or restarting is a fix only when the cause is a window that ran out or a resource
   that came back.
5. **Look sideways once.** Ask where else the same cause sits (the other sources, stores, lanes, readers) and fix or list
   what you find, so the lesson is not learned twice.
6. **Put the lesson where it belongs**: a skill or runbook line for a method or rule; a ticket for the work; never only in
   a conversation. Use the repository's lines: Problem, Root cause, Fix, Lesson, in four to eight lines.

## What you report

Four lines in business words, in addition to anything the repository requires in a report (the elapsed time of a step over ten
minutes; "incomplete" and the unchecked part for a ticket): what was seen, the cause and the evidence for it (the one or two facts that prove
it), what was changed and how it was proved, and what remains open and why. Not the whys, not the dead ends, not "I checked
X". If the evidence points two ways, say so and what would decide it.

## Examples (invented)

- A step reads idle while its store takes rows. The reading finds its processes by command line; the step's workers are
  started with none, so the reading saw the driver only. Root cause: processes are found by parentage. Fix the reading, test
  it, say so in the skill that reports status.
- A load stops with "a value is not its column's type". The database's own error code is a missing right, which the writer's
  message hid. Root cause: a catch-all that reports every database error as a value error. Fix the message, grant the right
  where grants are made, and check the other writers for the same catch-all.
