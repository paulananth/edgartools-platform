"""The exposure manifest is the exposure list resolved against the stores, and refuses what the list does not prove.
Every table, column and name here is invented."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts/exposure"))

from exposure_manifest import MANIFEST_VERSION, build_manifest, config_sha256, validate_manifest  # noqa: E402

CONFIG = {
    "version": "invented-exposure",
    "approval": {"date": "2026-01-01", "words": ["Invented approval"]},
    "target": {"database": "INVENTED_MIRROR", "verified": False},
    "layers": {
        "silver": {
            "connection": "INVENTED_SILVER_URL",
            "source_schema": "silver",
            "target_schema": "SILVER",
            "authority": "silver",
        },
        "mdm": {
            "connection": "INVENTED_MDM_URL",
            "source_schema": "public",
            "target_schema": "MDM",
            "authority": "mdm",
        },
    },
    "tables": [
        {
            "layer": "silver",
            "table": "widget_sale",
            "scope": "history",
            "grain": "one row per sale",
            "requirement": "rules/invented/silver-sale.yaml",
            "lineage": ["mdm.golden"],
        },
        {
            "layer": "mdm",
            "table": "golden",
            "scope": "current",
            "grain": "one row per MDM id",
            "requirement": "rules/invented/definitions.yaml",
            "definition": "One invented golden record.",
            "columns": {"entity_id": "The invented MDM id."},
        },
    ],
}
STORES = {
    "silver": {
        "widget_sale": {
            "comment": "One invented sale.",
            "columns": [
                {"name": "sale_id", "data_type": "text", "nullable": False, "comment": "The sale's id."},
                {"name": "buyer_mdm_id", "data_type": "text", "nullable": True, "comment": "The buyer's MDM id."},
            ],
        },
        "widget_draft": {
            "comment": "Not listed.",
            "columns": [{"name": "draft_id", "data_type": "text", "nullable": False, "comment": "A draft."}],
        },
    },
    "mdm": {
        "golden": {
            "comment": None,
            "columns": [{"name": "entity_id", "data_type": "character(36)", "nullable": False, "comment": None}],
        }
    },
}


def build(config=CONFIG, stores=STORES):
    return build_manifest(copy.deepcopy(config), copy.deepcopy(stores), config_digest="a" * 64)


def test_each_listed_table_keeps_its_store_identity_its_snowflake_identity_and_its_meaning_apart():
    manifest = build()
    assert manifest["manifest_version"] == MANIFEST_VERSION
    sale = next(t for t in manifest["tables"] if t["source"]["table"] == "widget_sale")
    assert sale["source"] == {"connection": "INVENTED_SILVER_URL", "schema": "silver", "table": "widget_sale"}
    assert sale["physical"] == {
        "database": "INVENTED_MIRROR",
        "schema": "SILVER",
        "table": "WIDGET_SALE",
        "verified": False,
    }
    assert sale["business"] == {
        "description": "One invented sale.",
        "grain": "one row per sale",
        "authority": "silver",
        "scope": "history",
    }
    assert [c["name"] for c in sale["columns"]] == ["sale_id", "buyer_mdm_id"]
    assert sale["lineage"] == [{"database": "INVENTED_MIRROR", "schema": "MDM", "table": "GOLDEN"}]


def test_a_table_the_list_does_not_name_is_absent_even_when_its_store_holds_it():
    assert {t["source"]["table"] for t in build()["tables"]} == {"widget_sale", "golden"}


def test_a_store_without_comments_takes_the_lists_definitions():
    golden = next(t for t in build()["tables"] if t["layer"] == "mdm")
    assert golden["business"]["description"] == "One invented golden record."
    assert golden["columns"] == [
        {"name": "entity_id", "data_type": "character(36)", "nullable": False, "description": "The invented MDM id."}
    ]


def test_the_manifest_is_the_same_whatever_order_the_list_names_its_tables():
    reordered = {**CONFIG, "tables": list(reversed(CONFIG["tables"]))}
    assert build(reordered) == build()


@pytest.mark.parametrize(
    "change, refusal",
    [
        (lambda c, s: s["silver"].pop("widget_sale"), "is not in its store"),
        (lambda c, s: c["tables"][1]["columns"].update({"ghost": "Invented."}), "does not have"),
        (lambda c, s: c["tables"][1].pop("columns"), "definition"),
        (lambda c, s: c["tables"][0].update({"table": "silver.widget_sale"}), "one plain name"),
        (lambda c, s: c["tables"][0].update({"lineage": ["mdm.unlisted"]}), "does not expose"),
        (lambda c, s: c["tables"][0].update({"layer": "gold"}), "undeclared layer"),
        (lambda c, s: c["tables"][0].update({"scope": "forever"}), "scope"),
        (lambda c, s: c["approval"].update({"words": []}), "operator's words"),
        (lambda c, s: c["target"].update({"verified": "no"}), "true or false"),
        (lambda c, s: c["tables"].append(dict(c["tables"][0])), "listed twice"),
        (lambda c, s: c["tables"][0].update({"surprise": 1}), "a table entry"),
    ],
)
def test_the_list_is_refused_when_it_does_not_prove_a_table(change, refusal):
    config, stores = copy.deepcopy(CONFIG), copy.deepcopy(STORES)
    change(config, stores)
    with pytest.raises(ValueError, match=refusal):
        build(config, stores)


def test_two_tables_the_mirror_would_give_one_name_are_refused():
    config, stores = copy.deepcopy(CONFIG), copy.deepcopy(STORES)
    config["layers"]["mdm"]["target_schema"] = "SILVER"
    config["tables"][1]["table"] = "widget_sale"
    config["tables"][1]["columns"] = {"sale_id": "Invented.", "buyer_mdm_id": "Invented."}
    config["tables"][0]["lineage"] = []
    stores["mdm"] = {"widget_sale": stores["silver"]["widget_sale"]}
    with pytest.raises(ValueError, match="one Snowflake identity"):
        build(config, stores)


def test_a_changed_or_reshaped_manifest_is_refused():
    manifest = build()
    validate_manifest(manifest)
    with pytest.raises(ValueError, match="version"):
        validate_manifest({**manifest, "manifest_version": MANIFEST_VERSION + 1})
    with pytest.raises(ValueError, match="digest"):
        validate_manifest({**manifest, "version": "another"})
    with pytest.raises(ValueError, match="must hold"):
        validate_manifest({**manifest, "extra": True})


def test_a_manifest_its_list_no_longer_makes_is_stale(tmp_path):
    path = tmp_path / "exposure.yaml"
    path.write_text("version: invented\n")
    manifest = build_manifest(copy.deepcopy(CONFIG), copy.deepcopy(STORES), config_digest=config_sha256(path))
    validate_manifest(manifest, config=path)
    path.write_text("version: invented-and-changed\n")
    with pytest.raises(ValueError, match="stale"):
        validate_manifest(manifest, config=path)
