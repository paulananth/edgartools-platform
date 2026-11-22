"""The list of final tables that may leave the stores is a destination (where data may be shared), not a rule."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_authorised_data_sharing_list_is_a_destination_not_a_rule():
    assert (ROOT / "destination" / "authorised_data_sharing.yaml").is_file()
    assert not (ROOT / "rules" / "exposure.yaml").exists()
