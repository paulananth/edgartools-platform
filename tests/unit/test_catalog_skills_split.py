"""The catalog skill holds the business meaning and routes to a catalog's own skill; a catalog's mechanics live in that
catalog's skill, so more than one catalog can be supported."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = (ROOT / "skills/data-catalog/SKILL.md").read_text()
OPENMETADATA = (ROOT / "skills/openmetadata/SKILL.md").read_text()


def test_the_catalog_skill_routes_each_destination_to_the_skill_that_owns_its_mechanics():
    assert "## Choose the catalog's own skill" in CATALOG
    assert "[openmetadata](../openmetadata/SKILL.md)" in CATALOG
    assert "references/PORTABILITY.md" in CATALOG
    assert "sibling skill" in CATALOG  # how another catalog is added


def test_the_catalog_skill_is_not_the_home_of_openmetadata_mechanics():
    mechanics = re.findall(r"/api/v1|rules catalog (?:plan|publish|check)\b|OPENMETADATA_TOKEN|execution boundary|Context Center", CATALOG)
    assert mechanics == [], mechanics  # those live in the openmetadata skill


def test_the_openmetadata_skill_says_it_holds_only_that_catalogs_mechanics():
    description = re.search(r"^description: (.*)$", OPENMETADATA, re.M).group(1)
    assert "data-catalog" in description and "OpenMetadata" in description


def test_the_catalog_skills_description_names_no_single_catalog_as_its_scope():
    description = re.search(r"^description: (.*)$", CATALOG, re.M).group(1)
    assert "any destination" in description and "Use for OpenMetadata catalog work" not in description


def test_the_local_server_doc_names_one_local_instance_not_a_second_one_to_protect():
    doc = (ROOT / "skills/openmetadata/LOCAL-SERVER.md").read_text()
    assert "It is the one local instance" in doc
    assert "must not stop it or remove its volumes" not in doc


def test_a_second_catalogs_skill_is_laid_out_like_the_first_and_the_publisher_commands_live_in_its_own_skill():
    assert "laid out like [openmetadata](../openmetadata/SKILL.md)" in CATALOG
    assert "rules catalog" in OPENMETADATA  # the OpenMetadata publisher's commands are documented where they belong
