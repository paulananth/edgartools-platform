# Exact calendar intervals on MySQL Silver

Status: deferred by operator, 2026-10-29.
Parent: [Silver two-engine completion](TICKET.md).

The operator selected “Defer calendar intervals; finish the other Silver gaps.”
Current MySQL INTERVAL storage preserves elapsed microseconds and refuses
calendar-month/year text. PostgreSQL retains its existing native interval forms.
No month-to-day approximation or implicit populated-table conversion is allowed.

- [ ] Define exact calendar semantics and a portable physical representation against an actual approved configuration need.
- [ ] Implement and qualify new registration plus recoverable populated conversion, keys/indexes, restricted rights and readback.
- [ ] Prove replay, mixed signs, precision, bounds and interruption without changing historical migrations.
- [ ] Learning → skill: update the owning operational guidance or record none.
