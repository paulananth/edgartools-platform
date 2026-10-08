# Configured census reading review

## Standards

The independent standards reviewer found eager reads on skipped records.
The fix projects identity selectively, reads registration only for wanted
legal keys, guards falsey containers and rejects truthy nonobjects. Regression
coverage preserves skip boundaries and source count limits. The canonical
transform invariant prevents census/name-rule drift. Immutable engine cache
keys and full-expression validation remain intact. No remaining scoped
standards or GoF blocker was found. Keep the interpreter and plain functions.

## Spec

The independent spec reviewer reproduced empty-container, skipped-BRANCH and
unmatched-registration regressions. After fixes, each matched historical
success. The reviewer then reproduced a paired-fault refusal-order change:
other names could fail before the matched timestamp. The caller now projects
legal key, wanted timestamp, then other names; cascade maps quality before
names. Paired-fault regressions cover malformed and oversized other names.
Historical AttributeError and configured typed SourceRejected are explicit
refusal boundaries. The historical test expectation was corrected to the
observed AttributeError; 97 affected checks passed afterward.

No remaining scoped production blocker was found. Whole-source construction,
remaining executable retirement, full population and recovery qualification
remain separate requirements.

Summary: Standards 1 resolved finding; Spec 4 resolved semantic findings and
1 corrected test expectation. No unresolved scoped finding on either axis.
