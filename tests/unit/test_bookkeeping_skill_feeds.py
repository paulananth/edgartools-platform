"""Skill selections use source descriptors, never a source-specific alias map."""
from pathlib import Path
from runpy import run_path
import subprocess
import sys

import pytest

from edgar_warehouse.rules.files import dumps, load
from edgar_warehouse.bookkeeping.clean.config import digest

ROOT = Path(__file__).resolve().parents[2] / "rules"
resolve_feed = run_path(str(ROOT.parent / "skills/bookkeeping/scripts/resolve_feed.py"))["resolve_feed"]
PAIRS = [
    ("sec.submissions.company", "submissions", "sec.submissions.company.v1"),
]


@pytest.mark.parametrize("source,feed,code", PAIRS)
def test_existing_feed_and_dataset_resolve_same_scope(source, feed, code):
    selected = resolve_feed(ROOT, source, feed)
    assert [dataset["code"] for dataset in selected["datasets"]] == [code]
    assert selected["rules_digest"] == digest(load(ROOT / "sources" / source / "source.yaml"))
    assert resolve_feed(ROOT, source, code)["datasets"] == selected["datasets"]


def test_only_declared_company_acquisition_resolves():
    assert resolve_feed(ROOT, "SEC", "submissions")["source"] == "sec.submissions.company"
    with pytest.raises(ValueError):
        resolve_feed(ROOT, "GLEIF", "level1")


@pytest.mark.parametrize("source,feed", [("", "level1"), ("gleif", ""), ("unknown", "level1"),
                                         ("gleif", "capture"), ("gleif", "submissions"),
                                         ("sec.submissions.company", "level1"),
                                         ("sec.adv", "adv_bulk"), ("sec.filings", "filing_artifact"),
                                         ("sec.company-facts", "company_facts")])
def test_missing_unknown_or_cross_source_selections_fail(source, feed):
    with pytest.raises(ValueError):
        resolve_feed(ROOT, source, feed)


def test_unseen_mdm_source_is_not_an_acquisition_feed(tmp_path):
    for name in ["new-feed", "second-feed"]:
        path = tmp_path / "sources" / name / "source.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(dumps({"source": name, "bronze": {"family": "new-family"},
                              "mdm": {f"{name}.v1": {"contract": {"provider": "NewProvider",
                              "family": "new-family", "adapter": {"native_member": "new-member"}}}}}))
    with pytest.raises(ValueError):
        resolve_feed(tmp_path, "new-feed", "new-member")
    with pytest.raises(ValueError, match="exactly one"):
        resolve_feed(tmp_path, "NewProvider", "new-family")


@pytest.mark.parametrize("arguments", [[], ["--source", "gleif"], ["--feed", "level1"],
                                       ["--source", "gleif", "--feed", "submissions"]])
def test_helper_cli_rejects_missing_or_incompatible_pair_from_any_checkout(tmp_path, arguments):
    script = ROOT.parent / "skills/bookkeeping/scripts/resolve_feed.py"
    result = subprocess.run([sys.executable, str(script), *arguments], cwd=tmp_path,
                            text=True, capture_output=True, check=False)
    assert result.returncode == 2
    assert not result.stdout
    assert "error:" in result.stderr
