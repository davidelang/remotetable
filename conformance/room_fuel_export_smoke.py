#!/usr/bin/env python3
"""
Room Fuel multi-tab export → json-book (always) → optional multi-room EtherCalc push.

Validates multi-tab fuel pilot without Google Sheets / coordinator rewrite:

  Offline (default harness):
    fixture has ≥2 ``Fuel - *`` tabs, each with Sync ID header + ≥1 row.

  EtherCalc (opt-in):
    REMOTETABLE_ETHERCALC_LOCAL=1 → for **each** fuel tab, push to a unique room
    (slug of tab name + run id), read-back Sync IDs. One room ≈ one grid.

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
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

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


def slug_tab(tab: str) -> str:
    """Room-safe slug from fuel tab name (EtherCalc one room ≈ one grid)."""
    # "Fuel - Car A" → car-a (room prefix already carries "fuel")
    s = tab.strip()
    if s.lower().startswith("fuel"):
        s = re.sub(r"(?i)^fuel\s*-\s*", "", s)
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "tab"
    return s[:48]


def sync_ids_from_grid(headers: list[str], rows: list[list[str]]) -> set[str]:
    if "Sync ID" not in headers:
        return set()
    sid_i = headers.index("Sync ID")
    return {
        str(r[sid_i]).strip()
        for r in rows
        if r and sid_i < len(r) and str(r[sid_i]).strip()
    }


def run_offline_jsonbook() -> dict[str, Any]:
    """Return full fuel book payload for multi-tab EtherCalc."""
    src = load_book_path()
    raw = json.loads(src.read_text(encoding="utf-8"))
    tabs = raw.get("tabs") or {}
    fuel_tabs = sorted(t for t in tabs if str(t).startswith(FUEL_PREFIX))
    assert_true(len(fuel_tabs) >= 2, f"need ≥2 fuel tabs, got {fuel_tabs}")

    counts: dict[str, int] = {}
    book_tabs: dict[str, dict] = {}
    for t in fuel_tabs:
        rows = assert_fuel_tab(t, tabs[t])
        counts[t] = len(rows)
        book_tabs[t] = {
            "headers": list(tabs[t]["headers"]),
            "rows": [list(r) for r in tabs[t]["rows"]],
        }

    with tempfile.TemporaryDirectory(prefix="room-fuel-") as td:
        path = Path(td) / "fuel_book.json"
        path.write_text(
            json.dumps({"tabs": book_tabs}, indent=2) + "\n",
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
    return {"tabs": book_tabs, "fuel_tabs": fuel_tabs, "counts": counts}


def run_ethercalc_all_tabs(book: dict[str, Any]) -> int:
    """
    Push **every** fuel tab to its own EtherCalc room; read-back Sync IDs.
    SKIP (0) if env unset or server down.
    """
    if os.environ.get("REMOTETABLE_ETHERCALC_LOCAL", "").strip() not in ("1", "true", "yes"):
        print("SKIP room-fuel→ethercalc multi-tab (set REMOTETABLE_ETHERCALC_LOCAL=1)")
        return 0

    base = os.environ.get("REMOTETABLE_ETHERCALC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    room_prefix = os.environ.get("REMOTETABLE_ETHERCALC_ROOM", "ve-fuel")
    run_id = f"{os.getpid()}-{int(time.time()) % 100000}"

    # Health check on a throwaway room
    probe = EtherCalcBackend(base_url=base, room=f"{room_prefix}-probe-{run_id}")
    conn = probe.test_connection()
    if not conn.get("ok"):
        print(f"SKIP room-fuel→ethercalc multi-tab (server down): {conn}")
        return 0

    fuel_tabs: list[str] = list(book["fuel_tabs"])
    tabs: dict[str, dict] = book["tabs"]
    rooms_ok: list[str] = []

    for tab in fuel_tabs:
        grid = tabs[tab]
        headers = list(grid["headers"])
        rows = [list(r) for r in grid["rows"]]
        room = f"{room_prefix}-{slug_tab(tab)}-{run_id}"
        be = EtherCalcBackend(base_url=base, room=room)

        be.ensure_headers(room, headers)
        written = be.write_rows(room, headers, rows, mode="replace")
        assert_true(int(written.get("written", 0)) >= 1, f"{tab}: {written}")

        back = be.read_rows(room)
        bh = list(back.get("headers") or [])
        assert_true("Sync ID" in bh, f"{tab} read headers: {bh}")
        expect = sync_ids_from_grid(headers, rows)
        got = sync_ids_from_grid(bh, [list(r) for r in back.get("rows") or []])
        missing = expect - got
        assert_true(
            not missing,
            f"{tab}: missing Sync IDs on EtherCalc: {missing}; got={got} room={room}",
        )
        rooms_ok.append(f"{tab}→{room}({len(expect)} ids)")
        print(f"  PASS tab={tab!r} room={room} ids={sorted(expect)}")

    print(
        f"PASS room-fuel→ethercalc multi-tab e2e base={base} "
        f"tabs={len(fuel_tabs)} rooms={rooms_ok}"
    )
    return 0


def main() -> int:
    book = run_offline_jsonbook()
    return run_ethercalc_all_tabs(book)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL room_fuel_export_smoke:", e, file=sys.stderr)
        raise SystemExit(1)
