from edgar_warehouse.bookkeeping.clean.engine import needs_mdm_approval


def test_a_merge_document_or_an_mdm_section_needs_approval():
    assert needs_mdm_approval({"kind": "merge", "body": {}})
    assert needs_mdm_approval({"kind": "source", "body": {"mdm": {"sec.company.v1": {}}}})


def test_the_name_of_a_target_decides_nothing():
    # `mdm` was once a target name that needed approval; a document without an mdm section
    # needs none whatever its targets are called.
    body = {"bookkeeping": {"targets": {"mdm": {"steps": [{"operation": "mdm.merge"}]}}}}
    assert not needs_mdm_approval({"kind": "pipeline", "body": body})


def test_a_rules_test_version_without_an_mdm_section_runs_its_mastering_target_unapproved():
    body = {"bookkeeping": {"targets": {"mastering": {"steps": [{"operation": "mdm.merge"}]}}}}
    assert not needs_mdm_approval({"kind": "source", "body": body})
