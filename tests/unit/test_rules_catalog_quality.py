"""Business catalog metadata preserves engine meaning and native API encoding."""
import pytest
from edgar_warehouse.rules import catalog

@pytest.mark.parametrize("expected, actual, matches", [
    ("a `field`", "a &#96;field&#96;", True),
    ("literal &#96;", "literal &amp;#96;", True),
    ("literal &#96;", "literal &#96;", False),
    ("a & b", "a &amp; b", True),
    ("original", "changed", False),
])
def test_markdown_comparison_decodes_only_the_native_transport_layer(expected, actual, matches):
    assert catalog._description_equal(expected, actual) == matches
