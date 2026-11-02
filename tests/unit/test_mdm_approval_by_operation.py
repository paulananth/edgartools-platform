from edgar_warehouse.bookkeeping.clean.engine import needs_mdm_approval


def _config(*operations):
    return {"steps": [{"name": f"s{i}", "operation": op} for i, op in enumerate(operations)]}


def test_a_target_with_a_merge_step_needs_approval_whatever_it_is_named():
    pipeline = {"kind": "pipeline", "body": {}}
    assert needs_mdm_approval(pipeline, _config("mdm.merge"))


def test_a_target_named_mdm_without_a_merge_step_needs_none():
    pipeline = {"kind": "pipeline", "body": {}}
    assert not needs_mdm_approval(pipeline, _config("artifact.copy"))


def test_a_merge_document_or_an_mdm_section_needs_approval():
    assert needs_mdm_approval({"kind": "merge", "body": {}}, _config("artifact.copy"))
    assert needs_mdm_approval({"kind": "pipeline", "body": {"mdm": {"x": 1}}}, _config("artifact.copy"))
