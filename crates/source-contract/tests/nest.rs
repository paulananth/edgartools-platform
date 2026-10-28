use source_contract::{Engine, Lookups, Steps, Val};
// facts.<concept>.units.<unit>[], as SEC company facts nests them; invented values.
const BASE: &str = r#"read:
  format: json
  limits: {max_records: 4}
  tables:
    facts:
      each:
        nest:
          each: {entries: {path: facts, key_field: concept, value_field: body}}
          keep: {concept: concept}
          then:
            nest:
              each: {entries: {path: body.units, key_field: unit, value_field: rows}}
              keep: {unit: unit}
              then: {values: {path: rows}}
      columns:
        id: {integer: {path: id, from: document}}
        concept: {text: {path: concept, trim: false}}
        unit: {text: {path: unit, trim: false}}
        end: {text: {path: end, trim: false}}
        val: {value: {path: val, big_numbers: text, decimals: text}}
"#;
const DOC: &str = r#"{"id": 7, "facts": {
  "Alpha": {"label": "A", "units": {"USD": [{"end": "2024-12-31", "val": 123456789012345678901234},
                                            {"end": "2025-12-31", "val": 0.1}],
                                    "shares": [{"end": "2025-12-31", "val": 5}]}},
  "Beta": {"units": {}}}}"#;

fn read(yaml: &str, raw: &str) -> Result<source_contract::Reading, source_contract::Rejected> {
    Engine::from_yaml(yaml, Steps::new()).unwrap().read(raw.as_bytes(), &Lookups::new())
}

#[test]
fn nested_entries_give_one_row_per_inner_item_with_the_kept_fields() {
    let rows = &read(BASE, DOC).unwrap().tables["facts"];
    let got: Vec<_> = rows.iter().map(|r| (r["concept"].clone(), r["unit"].clone(), r["end"].clone(), r["val"].clone())).collect();
    let s = |v: &str| Val::Str(v.into());
    assert_eq!(got, vec![
        (s("Alpha"), s("USD"), s("2024-12-31"), s("123456789012345678901234")),
        (s("Alpha"), s("USD"), s("2025-12-31"), s("0.1")),
        (s("Alpha"), s("shares"), s("2025-12-31"), Val::Int(5)),
    ]);
    assert!(rows.iter().all(|r| r["id"] == Val::Int(7)));  // `from: document` still reads the whole file
}

#[test]
fn every_inner_row_counts_against_max_records() {
    let more = DOC.replace(r#""shares": [{"end": "2025-12-31", "val": 5}]"#,
                           r#""shares": [{"end": "2025-12-31", "val": 5}, {"end": "2026-12-31", "val": 6}]"#);
    assert_eq!(read(BASE, &more).unwrap().tables["facts"].len(), 4);
    let over = more.replace(r#"{"end": "2026-12-31", "val": 6}"#, r#"{"end": "2026-12-31", "val": 6}, {"end": "2027-12-31", "val": 7}"#);
    assert_eq!(read(BASE, &over).unwrap_err().code, "limit_exceeded");
}

#[test]
fn a_kept_field_never_overwrites_an_inner_field_and_rows_must_be_objects() {
    let clash = DOC.replace(r#"{"end": "2024-12-31","#, r#"{"unit": "x", "end": "2024-12-31","#);
    assert_eq!(read(BASE, &clash).unwrap_err().code, "nest_field_conflict");
    let missing = BASE.replace("keep: {concept: concept}", "keep: {label: concept}");
    assert_eq!(read(&missing, DOC).unwrap_err().code, "nest_field_missing");
    let scalars = DOC.replace(r#"[{"end": "2025-12-31", "val": 5}]"#, "[5]");
    assert_eq!(read(BASE, &scalars).unwrap_err().code, "nest_row_shape");
}

#[test]
fn nest_arguments_refuse_at_load() {
    for (from, to) in [
        ("keep: {unit: unit}", "keep: {}"),
        ("keep: {unit: unit}", "keep: {unit: a.b}"),
        ("keep: {unit: unit}", "keep: {unit: unit, rows: unit}"),
        ("keep: {unit: unit}", "keep: {unit: unit}\n              extra: 1"),
        ("then: {values: {path: rows}}", "then: {unknown: {}}"),
    ] {
        assert!(Engine::from_yaml(&BASE.replace(from, to), Steps::new()).is_err(), "{to}");
    }
}
