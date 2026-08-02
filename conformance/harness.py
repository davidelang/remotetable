#!/usr/bin/env python3
"""
M1 conformance harness — mock backend (no network).
Run: python3 conformance/harness.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from remotetable import RemoteTable, MockBackend  # noqa: E402


def main() -> int:
    fixture = ROOT / "conformance" / "fixtures" / "mock_book.json"
    book = json.loads(fixture.read_text())
    backend = MockBackend(book)
    rt = RemoteTable(backend)

    conn = rt.test_connection()
    assert conn["ok"] is True, conn

    tabs = rt.list_tabs()
    assert "Vehicles" in tabs["tabs"], tabs
    assert "Fuel - Unassigned" in tabs["tabs"], tabs

    veh = rt.read_rows("Vehicles")
    assert veh["headers"][0] == "Sync ID"
    assert len(veh["rows"]) == 2
    assert veh["rows"][0][1] == "Car A"

    fuel = rt.read_rows("Fuel - Unassigned")
    assert fuel["rows"][0][1] == "10.00"

    # ensure headers (idempotent)
    h = ["Sync ID", "Name", "Updated At", "Notes"]
    ens = rt.ensure_headers("Vehicles", h)
    assert ens["ok"] is True
    assert "Notes" in ens["headers"]

    # append a row
    w = rt.write_rows(
        "Vehicles",
        ens["headers"],
        [["v-3", "Car C", "3000", ""]],
        mode="append",
    )
    assert w["written"] == 1
    veh2 = rt.read_rows("Vehicles")
    assert len(veh2["rows"]) == 3

    print("PASS conformance mock:", fixture.name)
    print("backends_required: google-sheets, excel-graph, ethercalc (live tests optional)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL:", e, file=sys.stderr)
        raise SystemExit(1)
