"""Every primitive the rules reference names is one the source engine's expression evaluator reads.

File-only: the names come from the reference's tables, the evaluator is the Rust source."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "docs" / "engine-rules-reference.md"
EVALUATOR = ROOT / "crates" / "source-contract" / "src" / "lib.rs"


def _named_primitives(text):
    return re.findall(r"^\| `([a-z_]+)` \|", text, flags=re.MULTILINE)


def test_every_primitive_the_reference_names_is_in_the_evaluator():
    names = _named_primitives(REFERENCE.read_text())
    evaluator = EVALUATOR.read_text()
    assert names
    assert [name for name in names if f'"{name}"' not in evaluator] == []
