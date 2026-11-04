# 191: The LEI on the series GLEIF names

Switch-on: standing approval (operator, 2026-11-04 07:00 ET: "switch on for form 4 keep it standing approval for ticket 190 191"): it is switched on once its limited test passes, with the counts recorded here and no question asked.

Priority: 191. Map: [Rebuild priorities](../map.md). Opened 2026-11-04 04:22 ET, from [ticket 125](125-securities-and-funds-uniquely-identifiable.md) (its third slice).

Type: task. Status: approved to build (operator, 2026-11-04 06:46 ET: "approve 190 and 191"). Blocked by: none.

## Question

Today the Fund source keeps a series' LEI only when that LEI belongs to one series and the series files one LEI (`lei_once` in `rules/sources/sec.nport.fund/combine.yaml`). In the 2026 Q2 data set 15 LEIs are filed by two or more series. GLEIF names one series for 12 of them (its legal name is that series' name) and the adviser, the trust or the company for 3 (one of them on 27 series). One series files two LEIs, and GLEIF gives one of them the series' own name.

Keep the LEI on the series GLEIF names, and keep it as a filed value only on the others; the 3 LEIs GLEIF gives to the adviser, the trust or the company attach to no series. Counts to the operator.

## Parts

- [ ] GoF consult on the Fund source's combination
- [ ] Design read from the code (2026-11-04 12:19 ET): GLEIF has no run that gives an LEI's legal name (`subfund-pairs` is the only pair run), so the input is a new generic GLEIF target `legal-names` (a read contract over the Golden Copy, one row per LEI: the LEI and its legal name written in the shape the Fund source compares, with `level1-json.yaml`'s stream settings) that any source can read, not a Fund-only file. The Fund source reads it as a lookup set (`{run: {source: gleif, target: legal-names, step: names}}`, as the umbrella pairs), writes at read time whether each series' own normalized name equals the legal name of its LEI (`lei_named`), and `combine.yaml` keeps the LEI on a series when it is filed once (today) or when `lei_named` holds, as a second group the record reads after `lei`. A combine cannot read a lookup, so the comparison sits in the reading, not in `lei-pairs.yaml`. Cost: a GLEIF run over about 2.3 million entries before the Fund source runs; gain: 12 series and the one series with two LEIs
- [ ] A GLEIF input to the Fund source: each shared LEI's legal name, read from GLEIF's run (the "read another run" input of ticket 120, as the umbrella pairs do), not from a download
- [ ] The combination joins the LEI to the one series whose normalized name equals GLEIF's legal name; a name that is another entity's joins none
- [ ] The series with two LEIs keeps the one GLEIF names for it; the other stays a filed value
- [ ] Tests on invented data: a shared LEI joins the named series only, an adviser-named LEI joins none, two LEIs on one series keep the named one (each failing before)
- [ ] Mapping Document regenerated; the whole CI set; counts per case reported to the operator
- [ ] PR, CI green, merged on green
- [ ] Learning → skill (`security-master`)
