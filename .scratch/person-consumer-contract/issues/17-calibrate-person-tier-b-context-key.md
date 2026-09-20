# Calibrate the Person Tier B compound context key on a held-out sample

Type: research
Status: open
Blocked by: none (03 resolved 2026-09-20)

## Question

Ticket 02 lets Tier B — same issuer/firm CIK + exact normalized name +
consistent role/flag — auto-merge once a held-out calibration proves
≥ 99% precision (one-sided 95% lower confidence bound, Clean MDM's own
method). No Snowflake: build the study from data the platform can reach
offline — the ADV `IA_Schedule_A_B` archive (research 16's
IAPD-corroborated `OwnerID` persons are a truth source for "same person
at the same firm") and the S3 export snapshots of 8-K events, plus a
frozen sample of Form 4 XML from bronze if reporting owners are needed.
Independently label at least 400 candidate pairs, including homonyms at
the same firm, reused ids, and transitive bridges (Clean MDM's stated
validation cases). Report precision with its lower bound, candidate
recall, and expected review volume. Blocked on ticket 03 because the
person-vs-entity classification decides which reporting-owner rows are
even eligible.
