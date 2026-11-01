"""Regression test verifying Stage 7 experiment runners and CSV schema conformance."""

from pathlib import Path
import pytest
from experiments.common import RESULTS_DIR, SCHEMA
from experiments.run_experiments import verify_csv_schema, EXPECTED_FILES, run_all


def test_experiments_execution_and_schema():
    """Verify that all 8 experiments execute cleanly and generate schema-compliant CSVs."""
    run_all()

    for exp_id, filename in EXPECTED_FILES:
        filepath = RESULTS_DIR / filename
        valid, row_count, msg = verify_csv_schema(filepath)
        assert valid is True, f"Experiment {exp_id} CSV failed schema check: {msg}"
        assert row_count > 0, f"Experiment {exp_id} CSV has 0 rows"
