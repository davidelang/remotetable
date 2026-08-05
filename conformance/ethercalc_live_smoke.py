#!/usr/bin/env python3
"""
Opt-in EtherCalc live smoke against a *local* (or any) server.

  REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/ethercalc_live_smoke.py

SKIP (exit 0) when env unset or server unreachable — same spirit as sheets live smoke.

Note: audreyt/ethercalc POST /_/{room} *appends* paste blocks. Smoke uses a **fresh
room name per run** so write+read is clean. Replace is verified on a second fresh room.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from remotetable.backends.ethercalc import EtherCalcBackend  # noqa: E402


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    if os.environ.get("REMOTETABLE_ETHERCALC_LOCAL", "").strip() not in ("1", "true", "yes"):
        print("SKIP ethercalc local smoke (set REMOTETABLE_ETHERCALC_LOCAL=1)")
        return 0

    base = os.environ.get("REMOTETABLE_ETHERCALC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    room_prefix = os.environ.get("REMOTETABLE_ETHERCALC_ROOM", "ve-smoke")
    # Unique room so append-only EtherCalc does not stack prior smoke runs
    room = f"{room_prefix}-{os.getpid()}-{int(time.time()) % 100000}"
    be = EtherCalcBackend(base_url=base, room=room)

    conn = be.test_connection()
    if not conn.get("ok"):
        print(f"SKIP ethercalc local smoke (server down): {conn}")
        return 0

    headers = ["Sync ID", "Name", "Updated At"]
    ens = be.ensure_headers(room, headers)
    assert_true(ens.get("ok") is True, str(ens))
    assert_true("Sync ID" in ens.get("headers", []), ens)

    written = be.write_rows(
        room,
        headers,
        [["v-1", "Car A", "1000"], ["v-2", "Car B", "2000"]],
        mode="replace",
    )
    assert_true(written.get("written") == 2, str(written))

    data = be.read_rows(room)
    assert_true("Sync ID" in data["headers"], data["headers"])
    # rows may include a leading blank line stripped by backend; find our keys
    ids = {r[0] for r in data["rows"] if r}
    assert_true("v-1" in ids and "v-2" in ids, f"ids={ids} rows={data['rows']}")

    # Replace semantics: use a *new* empty room (EtherCalc POST is append-oriented)
    room2 = f"{room}-r2"
    be2 = EtherCalcBackend(base_url=base, room=room2)
    be2.write_rows(room2, headers, [["only", "one", "9"]], mode="replace")
    data2 = be2.read_rows(room2)
    ids2 = {r[0] for r in data2["rows"] if r}
    assert_true("only" in ids2, data2)
    assert_true("v-1" not in ids2, "fresh room must not contain prior smoke data")

    print(f"PASS ethercalc local smoke base={base} room={room}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL ethercalc local smoke:", e, file=sys.stderr)
        raise SystemExit(1)
