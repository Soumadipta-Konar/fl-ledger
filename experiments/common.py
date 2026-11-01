"""Common utilities, schema definitions, and helpers for Stage 7 experiments."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SCHEMA = [
    "exp",
    "run_id",
    "seed",
    "config_hash",
    "K",
    "m",
    "d",
    "s",
    "round",
    "method",
    "scenario",
    "metric_name",
    "metric_value",
    "unit",
    "notes",
]


def compute_config_hash(config: dict[str, Any]) -> str:
    """Compute deterministic 10-char hex hash from config dictionary."""
    serialized = json.dumps(config, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:10]


def init_csv(csv_path: Path) -> None:
    """Initialize CSV file with header if it does not exist."""
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(SCHEMA)


def append_csv_rows(csv_path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Append rows adhering strictly to the 15-column schema."""
    init_csv(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for r in rows:
            # Ensure every column is populated
            row_vals = [
                str(r.get(col, "")) for col in SCHEMA
            ]
            writer.writerow(row_vals)
