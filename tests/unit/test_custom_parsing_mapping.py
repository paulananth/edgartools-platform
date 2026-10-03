from edgar_warehouse.rules import mapdoc


def test_mapping_workbook_includes_nested_custom_steps_and_their_exact_paths(tmp_path):
    body = {"read": {"tables": {"release": {"columns": {"sequence": {"custom": {
        "step": "epoch_microseconds@1", "inputs": {"value": {"custom": {
            "step": "other@1", "inputs": {"value": {"text": {"path": "time"}}}}}}}}}}}}}
    sheets = mapdoc._source_sheets("fixture.release", body, {}, tmp_path)
    path = tmp_path / "MAPPING.xlsx"
    mapdoc.write(path, sheets)
    rows = mapdoc.read(path)["Custom Parsing"]
    assert [row[0] for row in rows[1:]] == ["epoch_microseconds@1", "other@1"]
    assert rows[2][1] == "read.tables.release.columns.sequence.custom.inputs.value.custom"
    assert "Custom Parsing" not in mapdoc._source_sheets("fixture", {}, {}, tmp_path)
