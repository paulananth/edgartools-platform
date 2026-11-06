# Keep provisional dates visible as a quality limitation

Operator-approved file dates can make a relationship valid while its true
business start remains unknown. Preserve both facts through the existing
observed-start mechanism; a successful load does not resolve the missing fact.

- [x] Document the neutral rule in data-quality's Approved provisional dates:
  source provenance, endpoint coverage, nonblocking flags and later correction
  (2026-11-06 06:49 ET; reviewed against the configured relationship behavior).
- [x] Verify genericity: 96 checks pass (2026-11-06 06:50 ET).
- [ ] Publish the skill change for review.
- [x] Learning → skill: data-quality, Approved provisional dates distinguishes
  observed validity from an authoritative start (2026-11-06 06:49 ET).
