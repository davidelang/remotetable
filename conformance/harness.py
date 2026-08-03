#!/usr/bin/env python3
"""
Conformance harness — mock offline (always) + optional live smoke.

Run: python3 conformance/harness.py
Live (opt-in): REMOTETABLE_TOKEN_FILE=/path/to.json REMOTETABLE_BACKEND=google-sheets \\
               REMOTETABLE_SPREADSHEET_ID=... python3 conformance/harness.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from remotetable import (  # noqa: E402
    BackendIds,
    EtherCalcBackend,
    ExcelGraphBackend,
    GoogleSheetsBackend,
    MockBackend,
    RemoteTable,
)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def run_mock() -> None:
    fixture = ROOT / "conformance" / "fixtures" / "mock_book.json"
    book = json.loads(fixture.read_text())
    backend = MockBackend(book)
    rt = RemoteTable(backend)

    conn = rt.test_connection()
    assert_true(conn["ok"] is True, str(conn))

    tabs = rt.list_tabs()
    assert_true("Vehicles" in tabs["tabs"], str(tabs))
    assert_true("Fuel - Unassigned" in tabs["tabs"], str(tabs))

    veh = rt.read_rows("Vehicles")
    assert_true(veh["headers"][0] == "Sync ID", str(veh["headers"]))
    assert_true(len(veh["rows"]) == 2, str(veh["rows"]))
    assert_true(veh["rows"][0][1] == "Car A", str(veh["rows"][0]))

    fuel = rt.read_rows("Fuel - Unassigned")
    assert_true(fuel["rows"][0][1] == "10.00", str(fuel["rows"][0]))

    # ensure headers (idempotent + pad)
    h = ["Sync ID", "Name", "Updated At", "Notes"]
    ens = rt.ensure_headers("Vehicles", h)
    assert_true(ens["ok"] is True, str(ens))
    assert_true("Notes" in ens["headers"], str(ens))
    veh_padded = rt.read_rows("Vehicles")
    assert_true(len(veh_padded["rows"][0]) == len(ens["headers"]), "header pad")
    assert_true(veh_padded["rows"][0][-1] == "", "pad empty")

    # append
    w = rt.write_rows(
        "Vehicles",
        ens["headers"],
        [["v-3", "Car C", "3000", "n"]],
        mode="append",
    )
    assert_true(w["written"] == 1, str(w))
    assert_true(len(rt.read_rows("Vehicles")["rows"]) == 3, "append count")

    # replace mode
    w2 = rt.write_rows(
        "Vehicles",
        ["Sync ID", "Name"],
        [["only", "one"]],
        mode="replace",
    )
    assert_true(w2["written"] == 1, str(w2))
    rep = rt.read_rows("Vehicles")
    assert_true(len(rep["rows"]) == 1, "replace count")
    assert_true(rep["rows"][0][0] == "only", str(rep))

    # multi-tab isolation
    rt.write_rows("Fuel - Unassigned", ["Sync ID", "Cost"], [["x", "1"]], mode="append")
    assert_true(len(rt.read_rows("Fuel - Unassigned")["rows"]) == 2, "fuel append")
    assert_true(len(rt.read_rows("Vehicles")["rows"]) == 1, "vehicles untouched")

    # empty book
    empty = RemoteTable(MockBackend({}))
    assert_true(empty.list_tabs()["tabs"] == [], "empty tabs")
    empty.write_rows("T1", ["A", "B"], [["1", "2"]], mode="replace")
    assert_true(empty.read_rows("T1")["headers"] == ["A", "B"], "empty create")

    print("PASS conformance mock:", fixture.name)


def run_live_optional() -> None:
    token = os.environ.get("REMOTETABLE_TOKEN_FILE", "").strip()
    backend_id = os.environ.get("REMOTETABLE_BACKEND", "").strip()
    if not token or not backend_id:
        print("SKIP live smoke (set REMOTETABLE_TOKEN_FILE + REMOTETABLE_BACKEND)")
        return
    if not Path(token).is_file():
        raise AssertionError(f"token file missing: {token}")

    if backend_id == BackendIds.GOOGLE_SHEETS:
        sid = os.environ.get("REMOTETABLE_SPREADSHEET_ID")
        be = GoogleSheetsBackend(token, spreadsheet_id=sid)
    elif backend_id == BackendIds.EXCEL_GRAPH:
        be = ExcelGraphBackend(token)
    elif backend_id == BackendIds.ETHERCALC:
        be = EtherCalcBackend(token_file=token)
    else:
        raise AssertionError(f"unknown backend: {backend_id}")

    rt = RemoteTable(be)
    conn = rt.test_connection()
    assert_true(conn.get("ok") is True, f"live test_connection: {conn}")
    tabs = rt.list_tabs()
    assert_true(isinstance(tabs.get("tabs"), list), str(tabs))
    print("PASS live smoke:", backend_id, "tabs=", len(tabs["tabs"]))


def main() -> int:
    run_mock()
    run_live_optional()
    print("backends_required:", ", ".join(BackendIds.LIVE))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL:", e, file=sys.stderr)
        raise SystemExit(1)
