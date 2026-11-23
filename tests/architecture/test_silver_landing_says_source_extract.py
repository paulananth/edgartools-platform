"""CONTEXT.md avoids "Reading": silver's landing worker speaks of a Source Extract and the context defines Silver Landing."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_context_defines_silver_landing_beside_the_source_extract():
    context = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    assert "**Silver Landing**:" in context
    assert context.index("**Source Extract**:") < context.index("**Silver Landing**:")


def test_the_landing_worker_names_no_reading_apart_from_its_module_import():
    text = (ROOT / "edgar_warehouse" / "workers" / "silver_land.py").read_text(encoding="utf-8")
    prose = text.replace("source_readings", "")
    assert "reading" not in prose.lower(), "a Source Extract, never a reading (CONTEXT.md)"
