#!/usr/bin/env python3
"""
Room Vehicles export → json-book (always) → optional local EtherCalc push.

Validates the multi-backend pilot path without Google Sheets:

  Phase offline (default harness):
    fixture/json-book has Vehicles tab with Sync ID + expected row count.

  Phase EtherCalc (opt-in):
    REMOTETABLE_ETHERCALC_LOCAL=1 + server up → write Vehicles grid to a
    unique room, read-back Sync IDs.

VE producer: RoomVehiclesBackend.exportJsonBook (app).
Host fixture: conformance/fixtures/room_vehicles_export.json (same shape).

Usage:
  python3 conformance/room_export_to_ethercalc_smoke.py
  REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/room_export_to_ethercalc_smoke.py

  # optional: app-exported book instead of fixture
  ROOM_EXPORT_JSONBOOK=/path/to/book.json python3 conformance/room_export_to_ethercalc_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from remotetable.backends.ethercalc import EtherCalcBackend  # noqa: E402
from remotetable.backends.json_book import JsonBookBackend  # noqa: E402

TAB = "Vehicles"
FIXTURE = ROOT / "conformance" / "fixtures" / "room_vehicles_export.json"


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def load_book_path() -> Path:
    override = os.environ.get("ROOM_EXPORT_JSONBOOK", "").strip()
    if override:
        p = Path(override)
        assert_true(p.is_file(), f"ROOM_EXPORT_JSONBOOK not a file: {p}")
        return p
    assert_true(FIXTURE.is_file(), f"missing fixture {FIXTURE}")
    return FIXTURE


def assert_vehicles_book(data: dict) -> list[list[str]]:
    """Assert Room-export shape; return data rows."""
    headers = list(data.get("headers") or [])
    rows = [list(r) for r in (data.get("rows") or [])]
    assert_true(len(headers) > 0, "empty headers")
    assert_true(headers[0] == "Sync ID" or "Sync ID" in headers, f"need Sync ID: {headers[:5]}")
    sid_i = headers.index("Sync ID")
    ids = [r[sid_i].strip() for r in rows if sid_i < len(r) and str(r[sid_i]).strip()]
    assert_true(len(ids) >= 1, f"need ≥1 Sync ID row; rows={rows}")
    assert_true(all(i for i in ids), f"blank Sync ID: {ids}")
    return rows


def run_offline_jsonbook() -> dict:
    """Load fixture (or override), round-trip via JsonBookBackend, assert Sync ID."""
    src = load_book_path()
    raw = json.loads(src.read_text(encoding="utf-8"))
    tabs = raw.get("tabs") or {}
    assert_true(TAB in tabs, f"expected tab {TAB} in {list(tabs)}")
    rows = assert_vehicles_book(tabs[TAB])
    expected_n = len(rows)

    with tempfile.TemporaryDirectory(prefix="room-export-") as td:
        path = Path(td) / "vehicles_book.json"
        path.write_text(json.dumps({"tabs": {TAB: tabs[TAB]}}, indent=2) + "\n", encoding="utf-8")
        be = JsonBookBackend(path)
        conn = be.test_connection()
        assert_true(conn.get("ok") is True, str(conn))
        data = be.read_rows(TAB)
        got_rows = assert_vehicles_book(data)
        assert_true(len(got_rows) == expected_n, f"row count {len(got_rows)} != {expected_n}")
        # ensureHeaders does not wipe Sync ID
        ens = be.ensure_headers(TAB, data["headers"])
        assert_true("Sync ID" in ens.get("headers", data["headers"]), ens)

    print(f"PASS room→json-book offline rows={expected_n} src={src.name}")
    return {"headers": tabs[TAB]["headers"], "rows": rows, "path": str(src)}


def run_ethercalc_push(grid: dict) -> int:
    """
    Push Vehicles grid to local EtherCalc; read-back Sync IDs.
    SKIP (0) if env unset or server down.
    """
    if os.environ.get("REMOTETABLE_ETHERCALC_LOCAL", "").strip() not in ("1", "true", "yes"):
        print("SKIP room→ethercalc (set REMOTETABLE_ETHERCALC_LOCAL=1)")
        return 0

    base = os.environ.get("REMOTETABLE_ETHERCALC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    room_prefix = os.environ.get("REMOTETABLE_ETHERCALC_ROOM", "ve-room-export")
    room = f"{room_prefix}-{os.getpid()}-{int(time.time()) % 100000}"
    be = EtherCalcBackend(base_url=base, room=room)

    conn = be.test_connection()
    if not conn.get("ok"):
        print(f"SKIP room→ethercalc (server down): {conn}")
        return 0

    headers = list(grid["headers"])
    rows = [list(r) for r in grid["rows"]]
    # EtherCalc room ≈ one grid; use room name as tab key
    ens = be.ensure_headers(room, headers)
    assert_true(ens.get("ok") is True or "Sync ID" in ens.get("headers", headers), ens)

    written = be.write_rows(room, headers, rows, mode="replace")
    assert_true(int(written.get("written", 0)) >= 1, str(written))

    back = be.read_rows(room)
    assert_true("Sync ID" in back.get("headers", []) or back.get("headers", [""])[0] == "Sync ID", back)
    # locate Sync ID column
    bh = back["headers"]
    try:
        sid_i = bh.index("Sync ID")
    except ValueError:
        sid_i = 0
    expect = {str(r[0]).strip() for r in rows if r and str(r[0]).strip()}
    # Source fixture has Sync ID in col 0
    got = {str(r[sid_i]).strip() for r in back.get("rows") or [] if r and sid_i < len(r) and str(r[sid_i]).strip()}
    missing = expect - got
    assert_true(not missing, f"missing Sync IDs on EtherCalc: {missing}; got={got} room={room}")

    print(f"PASS room→ethercalc e2e base={base} room={room} ids={sorted(expect)}")
    return 0


def main() -> int:
    grid = run_offline_jsonbook()
    return run_ethercalc_push(grid)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL room_export_to_ethercalc_smoke:", e, file=sys.stderr)
        raise SystemExit(1)
