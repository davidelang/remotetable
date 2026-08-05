#!/usr/bin/env python3
"""
Room Fuel multi-tab export → json-book (always) → optional local EtherCalc push.

Validates multi-tab fuel pilot without Google Sheets / coordinator rewrite:

  Offline (default harness):
    fixture has ≥2 ``Fuel - *`` tabs, each with Sync ID header + ≥1 row.

  EtherCalc (opt-in):
    REMOTETABLE_ETHERCALC_LOCAL=1 → push **one** fuel tab to a unique room,
    read-back Sync IDs.

VE producer: RoomFuelBackend.exportJsonBook (app).
Host fixture: conformance/fixtures/room_fuel_export.json

Usage:
  python3 conformance/room_fuel_export_smoke.py
  REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/room_fuel_export_smoke.py
  ROOM_FUEL_JSONBOOK=/path/to/book.json python3 conformance/room_fuel_export_smoke.py
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

FUEL_PREFIX = "Fuel - "
FIXTURE = ROOT / "conformance" / "fixtures" / "room_fuel_export.json"


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def load_book_path() -> Path:
    override = os.environ.get("ROOM_FUEL_JSONBOOK", "").strip()
    if override:
        p = Path(override)
        assert_true(p.is_file(), f"ROOM_FUEL_JSONBOOK not a file: {p}")
        return p
    assert_true(FIXTURE.is_file(), f"missing fixture {FIXTURE}")
    return FIXTURE


def assert_fuel_tab(tab: str, data: dict) -> list[list[str]]:
    assert_true(tab.startswith(FUEL_PREFIX), f"fuel tab name: {tab}")
    headers = list(data.get("headers") or [])
    rows = [list(r) for r in (data.get("rows") or [])]
    assert_true(len(headers) > 0, f"{tab}: empty headers")
    assert_true("Sync ID" in headers, f"{tab}: need Sync ID in {headers[:8]}")
    # Notes + Sync ID regression (FUEL_HEADERS human-first order)
    assert_true("Notes" in headers, f"{tab}: need Notes column")
    sid_i = headers.index("Sync ID")
    ids = [str(r[sid_i]).strip() for r in rows if sid_i < len(r) and str(r[sid_i]).strip()]
    assert_true(len(ids) >= 1, f"{tab}: need ≥1 Sync ID row; n={len(rows)}")
    return rows


def run_offline_jsonbook() -> dict:
    src = load_book_path()
    raw = json.loads(src.read_text(encoding="utf-8"))
    tabs = raw.get("tabs") or {}
    fuel_tabs = sorted(t for t in tabs if str(t).startswith(FUEL_PREFIX))
    assert_true(len(fuel_tabs) >= 2, f"need ≥2 fuel tabs, got {fuel_tabs}")

    counts: dict[str, int] = {}
    for t in fuel_tabs:
        rows = assert_fuel_tab(t, tabs[t])
        counts[t] = len(rows)

    with tempfile.TemporaryDirectory(prefix="room-fuel-") as td:
        path = Path(td) / "fuel_book.json"
        # strip non-tab meta keys
        path.write_text(
            json.dumps({"tabs": {t: tabs[t] for t in fuel_tabs}}, indent=2) + "\n",
            encoding="utf-8",
        )
        be = JsonBookBackend(path)
        assert_true(be.test_connection().get("ok") is True, "json-book conn")
        names = list(be.list_tabs())
        for t in fuel_tabs:
            assert_true(t in names, f"missing tab {t} in {names}")
            data = be.read_rows(t)
            got = assert_fuel_tab(t, data)
            assert_true(len(got) == counts[t], f"{t} row count {len(got)}!={counts[t]}")

    print(f"PASS room-fuel→json-book offline tabs={len(fuel_tabs)} counts={counts} src={src.name}")
    # first fuel tab for optional EtherCalc push
    first = fuel_tabs[0]
    return {"tab": first, "headers": tabs[first]["headers"], "rows": tabs[first]["rows"]}


def run_ethercalc_one_tab(grid: dict) -> int:
    if os.environ.get("REMOTETABLE_ETHERCALC_LOCAL", "").strip() not in ("1", "true", "yes"):
        print("SKIP room-fuel→ethercalc (set REMOTETABLE_ETHERCALC_LOCAL=1)")
        return 0

    base = os.environ.get("REMOTETABLE_ETHERCALC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    room_prefix = os.environ.get("REMOTETABLE_ETHERCALC_ROOM", "ve-room-fuel")
    room = f"{room_prefix}-{os.getpid()}-{int(time.time()) % 100000}"
    be = EtherCalcBackend(base_url=base, room=room)
    conn = be.test_connection()
    if not conn.get("ok"):
        print(f"SKIP room-fuel→ethercalc (server down): {conn}")
        return 0

    headers = list(grid["headers"])
    rows = [list(r) for r in grid["rows"]]
    be.ensure_headers(room, headers)
    written = be.write_rows(room, headers, rows, mode="replace")
    assert_true(int(written.get("written", 0)) >= 1, str(written))

    back = be.read_rows(room)
    bh = back.get("headers") or []
    assert_true("Sync ID" in bh, bh)
    sid_i = bh.index("Sync ID")
    src_i = headers.index("Sync ID") if "Sync ID" in headers else 0
    expect = {str(r[src_i]).strip() for r in rows if r and src_i < len(r) and str(r[src_i]).strip()}
    got = {
        str(r[sid_i]).strip()
        for r in back.get("rows") or []
        if r and sid_i < len(r) and str(r[sid_i]).strip()
    }
    missing = expect - got
    assert_true(not missing, f"missing Sync IDs: {missing}; got={got} room={room}")
    print(
        f"PASS room-fuel→ethercalc e2e tab={grid.get('tab')} "
        f"base={base} room={room} ids={sorted(expect)}"
    )
    return 0


def main() -> int:
    grid = run_offline_jsonbook()
    return run_ethercalc_one_tab(grid)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL room_fuel_export_smoke:", e, file=sys.stderr)
        raise SystemExit(1)
