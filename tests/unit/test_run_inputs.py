"""The run inputs lister reads names and comments from a source's rules, nothing from the data."""
import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "skills/data-onboarding/scripts/run_inputs.py"
spec = importlib.util.spec_from_file_location("run_inputs", PATH)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

DESCRIBED = """# The month the file covers comes in as the run fact `month` (an ISO instant).
bookkeeping:
  targets:
    # Loads the invented feed; the run gives the month and a scope file.
    load:
      run:
        facts: [month]
        files: [scope]
      steps: []
    plain:
      steps: []
"""

UNDESCRIBED = """bookkeeping:
  targets:
    load:
      run:
        facts: [period]
      steps: []
"""


def test_a_target_with_run_inputs_lists_them_with_the_comment_above_it():
    assert tool.describe("invented", DESCRIBED) == [
        "invented / load", "  facts: month", "  files: scope",
        "  | Loads the invented feed; the run gives the month and a scope file."]


def test_without_a_comment_above_the_target_the_comment_lines_naming_each_input_are_shown():
    text = DESCRIBED.replace("    # Loads the invented feed; the run gives the month and a scope file.\n", "")
    assert tool.describe("invented", text) == [
        "invented / load", "  facts: month", "  files: scope",
        "  | month: The month the file covers comes in as the run fact `month` (an ISO instant).",
        "  | scope: (no comment in the rules says how it is produced)"]


def test_an_input_nobody_describes_says_so_and_a_target_without_inputs_is_not_listed():
    assert tool.describe("invented", UNDESCRIBED) == [
        "invented / load", "  facts: period", "  files: none",
        "  | period: (no comment in the rules says how it is produced)"]
    assert tool.describe("invented", "bookkeeping:\n  targets:\n    plain:\n      steps: []\n") == []
