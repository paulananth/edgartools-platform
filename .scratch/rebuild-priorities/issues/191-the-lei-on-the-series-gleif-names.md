# 191: The LEI on the series GLEIF names

Switch-on: standing approval (operator, 2026-11-04 07:00 ET: "switch on for form 4 keep it standing approval for ticket 190 191"): it is switched on once its limited test passes, with the counts recorded here and no question asked.

Priority: 191. Map: [Rebuild priorities](../map.md). Opened 2026-11-04 04:22 ET, from [ticket 125](125-securities-and-funds-uniquely-identifiable.md) (its third slice).

Type: task. Status: closed, not needed (operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"). Blocked by: none.

## Question

Today the Fund source keeps a series' LEI only when that LEI belongs to one series and the series files one LEI (`lei_once` in `rules/sources/sec.nport.fund/combine.yaml`). In the 2026 Q2 data set 15 LEIs are filed by two or more series. GLEIF names one series for 12 of them (its legal name is that series' name) and the adviser, the trust or the company for 3 (one of them on 27 series). One series files two LEIs, and GLEIF gives one of them the series' own name.

Keep the LEI on the series GLEIF names, and keep it as a filed value only on the others; the 3 LEIs GLEIF gives to the adviser, the trust or the company attach to no series. Counts to the operator.

## Parts

- [ ] ~~GoF consult on the Fund source's combination~~ not needed: operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"
- [ ] ~~Design read from the code (2026-11-04 12~~ not needed: operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"
- [ ] ~~A GLEIF input to the Fund source~~ not needed: operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"
- [ ] ~~The combination joins the LEI to the one series whose normalized name equals GLEIF's legal name; a name that is another ~~ not needed: operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"
- [ ] ~~The series with two LEIs keeps the one GLEIF names for it; the other stays a filed value~~ not needed: operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"
- [ ] ~~Tests on invented data~~ not needed: operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"
- [ ] ~~Mapping Document regenerated; the whole CI set; counts per case reported to the operator~~ not needed: operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"
- [ ] ~~PR, CI green, merged on green~~ not needed: operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"
- [ ] ~~Learning → skill (`security-master`)~~ not needed: operator, 2026-11-04 12:23 ET: "Continue and finish ticket 190 no need for 191"
