#!/usr/bin/env python3
"""
PolicySync / MergeSync lww_row scenario suite (agent-runnable soak evidence).

Offline pure (always):
  S1 local newer wins · S2 remote newer · S3 equal prefer A · S4 tombstone · S5 key-only
  S6 vehicle definition overlay (thin remote + thick local) — mirrors VE VehicleDefinitionOverlay
  S7 fuel multi-tab independent LWW

EtherCalc opt-in (REMOTETABLE_ETHERCALC_LOCAL=1 + up.sh):
  S8 write remote grid to EC room, read back, merge with local, assert winners
  Multi-tab fuel: one room per tab

Does **not** flip VE PolicySync defaults. Run:
  python3 conformance/policysync_scenarios.py
  conformance/ethercalc/up.sh
  REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/policysync_scenarios.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from remotetable.backends.ethercalc import EtherCalcBackend  # noqa: E402
from remotetable.row_ops import merge_tab_data  # noqa: E402

# ── minimal header sets (Sync ID + Updated At + payload) ─────────────────────

ACK_H = ["Sync ID", "Kind", "Updated At", "Deleted", "Note"]
EXP_H = ["Sync ID", "Description", "Updated At", "Deleted"]
VEH_H = [
    "Sync ID",
    "Name",
    "Updated At",
    "Deleted",
    "Odo Crop L",
    "Odo Crop T",
    "Odo Crop R",
    "Odo Crop B",
    "Landmark Text Blocks JSON",
]
FUEL_H = ["Sync ID", "Odometer", "Notes", "Updated At", "Deleted"]


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def unit(headers: Sequence[str]) -> Dict[str, Any]:
    cols = []
    for h in headers:
        if h in ("Updated At", "Deleted At", "Created At", "Timestamp"):
            t = "timestamp"
        elif h == "Deleted":
            t = "checkbox"
        elif h in ("Odometer", "Odo Crop L", "Odo Crop T", "Odo Crop R", "Odo Crop B"):
            t = "number"
        else:
            t = "string"
        cols.append({"name": h, "type": t})
    return {
        "keys": ["Sync ID"],
        "timestamp": "Updated At",
        "merge_mode": "lww_row",
        "columns": cols,
        "tombstone": {"column": "Deleted", "true_values": ["true", "1", "yes"]},
    }


def tab(headers: Sequence[str], rows: List[List[str]]) -> Dict[str, Any]:
    return {"headers": list(headers), "rows": rows}


def by_sid(merged: Dict[str, Any], headers: Sequence[str]) -> Dict[str, List[str]]:
    hi = {h: i for i, h in enumerate(merged["headers"])}
    sid_i = hi["Sync ID"]
    out: Dict[str, List[str]] = {}
    for r in merged["rows"]:
        if sid_i < len(r) and str(r[sid_i]).strip():
            out[str(r[sid_i]).strip()] = list(r)
    return out


def cell(row: List[str], headers: Sequence[str], name: str) -> str:
    try:
        i = list(headers).index(name)
    except ValueError:
        return ""
    return str(row[i]) if i < len(row) else ""


def merge_lww(local: Dict[str, Any], remote: Dict[str, Any], headers: Sequence[str]) -> Dict[str, Any]:
    return merge_tab_data(local, remote, unit(headers))


# ── S1–S5 generic entity scenarios ───────────────────────────────────────────

def run_entity_s1_s5(entity: str, headers: Sequence[str], note_col: str) -> None:
    """note_col is a payload column used to detect which side won."""
    h = list(headers)
    note_i = h.index(note_col)
    ts_i = h.index("Updated At")
    del_i = h.index("Deleted")
    sid_i = h.index("Sync ID")

    def row(sid: str, ts: str, note: str, deleted: str = "") -> List[str]:
        r = [""] * len(h)
        r[sid_i] = sid
        r[ts_i] = ts
        r[note_i] = note
        r[del_i] = deleted
        return r

    # S1: local newer
    a = tab(h, [row("k1", "200", "local-new")])
    b = tab(h, [row("k1", "100", "remote-old")])
    m = by_sid(merge_lww(a, b, h), h)
    assert_true(m["k1"][note_i] == "local-new", f"{entity} S1 local newer: {m['k1']}")

    # S2: remote newer
    a = tab(h, [row("k1", "100", "local-old")])
    b = tab(h, [row("k1", "200", "remote-new")])
    m = by_sid(merge_lww(a, b, h), h)
    assert_true(m["k1"][note_i] == "remote-new", f"{entity} S2 remote newer: {m['k1']}")

    # S3: equal ts → prefer A (local)
    a = tab(h, [row("k1", "100", "tie-local")])
    b = tab(h, [row("k1", "100", "tie-remote")])
    m = by_sid(merge_lww(a, b, h), h)
    assert_true(m["k1"][note_i] == "tie-local", f"{entity} S3 tie prefer A: {m['k1']}")

    # S4: newer tombstone wins
    a = tab(h, [row("k1", "100", "live-local", "")])
    b = tab(h, [row("k1", "200", "x", "true")])
    m = by_sid(merge_lww(a, b, h), h)
    assert_true(m["k1"][del_i] == "true", f"{entity} S4 tombstone: {m['k1']}")

    # S5: key only local / only remote
    a = tab(h, [row("only-a", "50", "a-side")])
    b = tab(h, [row("only-b", "60", "b-side")])
    m = by_sid(merge_lww(a, b, h), h)
    assert_true(set(m) == {"only-a", "only-b"}, f"{entity} S5 keys {set(m)}")
    assert_true(m["only-a"][note_i] == "a-side" and m["only-b"][note_i] == "b-side", m)

    print(f"PASS PolicySync scenarios S1–S5 ({entity})")


# ── S6 vehicle definition overlay (port of VehicleDefinitionOverlay.kt) ─────

def _has_complete_odo(row: List[str], headers: Sequence[str]) -> bool:
    for name in ("Odo Crop L", "Odo Crop T", "Odo Crop R", "Odo Crop B"):
        if not cell(row, headers, name).strip():
            return False
    return True


def vehicle_definition_overlay(
    winner: List[str],
    loser: List[str],
    headers: Sequence[str],
) -> List[str]:
    """Mirror VE VehicleDefinitionOverlay.overlay for crops + landmarks (host evidence)."""
    out = list(winner)
    hi = {h: i for i, h in enumerate(headers)}

    def setc(name: str, val: str) -> None:
        i = hi[name]
        while len(out) <= i:
            out.append("")
        out[i] = val

    if not _has_complete_odo(out, headers) and _has_complete_odo(loser, headers):
        for name in ("Odo Crop L", "Odo Crop T", "Odo Crop R", "Odo Crop B"):
            setc(name, cell(loser, headers, name))

    w_lm = cell(out, headers, "Landmark Text Blocks JSON")
    l_lm = cell(loser, headers, "Landmark Text Blocks JSON")
    if not w_lm.strip() and l_lm.strip():
        setc("Landmark Text Blocks JSON", l_lm)
    return out


def loser_of_pair(local: List[str], remote: List[str], headers: Sequence[str]) -> List[str]:
    la = int(cell(local, headers, "Updated At") or "0")
    rb = int(cell(remote, headers, "Updated At") or "0")
    if rb > la:
        return local
    if la > rb:
        return remote
    return remote  # tie prefer local winner → loser remote


def run_s6_vehicle_overlay() -> None:
    h = VEH_H
    # Remote newer but thin (no crops); local older with full odo crops + landmarks
    local = [
        "v1",
        "Car",
        "100",
        "",
        "0.1",
        "0.2",
        "0.3",
        "0.4",
        '[{"t":"x"}]',
    ]
    remote = ["v1", "Car", "200", "", "", "", "", "", ""]
    merged = merge_lww(tab(h, [local]), tab(h, [remote]), h)
    by = by_sid(merged, h)
    winner = by["v1"]
    # Full-row LWW alone: remote wins → crops empty
    assert_true(not _has_complete_odo(winner, h), f"S6 pre-overlay thin winner {winner}")
    loser = loser_of_pair(local, remote, h)
    overlaid = vehicle_definition_overlay(winner, loser, h)
    assert_true(_has_complete_odo(overlaid, h), f"S6 overlay fills crops {overlaid}")
    assert_true(
        cell(overlaid, h, "Landmark Text Blocks JSON").strip().startswith("["),
        f"S6 landmarks {overlaid}",
    )
    assert_true(cell(overlaid, h, "Updated At") == "200", "S6 keeps remote ts")
    print("PASS PolicySync scenario S6 (vehicle definition overlay)")


# ── S7 fuel multi-tab independent ────────────────────────────────────────────

def run_s7_fuel_multi_tab() -> None:
    h = FUEL_H
    # Tab Honda: local wins k1
    a1 = tab(h, [["k1", "1000", "honda-local", "300", ""]])
    b1 = tab(h, [["k1", "1000", "honda-remote", "100", ""]])
    m1 = by_sid(merge_lww(a1, b1, h), h)
    assert_true(m1["k1"][2] == "honda-local", m1)

    # Tab Ford: remote wins k2 (independent)
    a2 = tab(h, [["k2", "2000", "ford-local", "50", ""]])
    b2 = tab(h, [["k2", "2000", "ford-remote", "90", ""]])
    m2 = by_sid(merge_lww(a2, b2, h), h)
    assert_true(m2["k2"][2] == "ford-remote", m2)
    # Cross-contamination check
    assert_true("k1" not in m2 and "k2" not in m1, "S7 tabs independent")
    print("PASS PolicySync scenario S7 (fuel multi-tab independent LWW)")


def run_pure_all() -> None:
    run_entity_s1_s5("merge-acks", ACK_H, "Note")
    run_entity_s1_s5("expenses", EXP_H, "Description")
    run_entity_s1_s5("vehicles", VEH_H, "Name")
    run_entity_s1_s5("fuel", FUEL_H, "Notes")
    run_s6_vehicle_overlay()
    run_s7_fuel_multi_tab()
    print("PASS PolicySync pure scenario suite (S1–S7 offline)")


# ── S8 EtherCalc as remote side ──────────────────────────────────────────────

def _ec_env_on() -> bool:
    return os.environ.get("REMOTETABLE_ETHERCALC_LOCAL", "").strip() in ("1", "true", "yes")


def run_s8_ethercalc() -> int:
    if not _ec_env_on():
        print("SKIP PolicySync S8 EtherCalc scenarios (set REMOTETABLE_ETHERCALC_LOCAL=1)")
        return 0

    base = os.environ.get("REMOTETABLE_ETHERCALC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    run_id = f"{os.getpid()}-{int(time.time()) % 100000}"
    probe = EtherCalcBackend(base_url=base, room=f"ve-ps-probe-{run_id}")
    conn = probe.test_connection()
    if not conn.get("ok"):
        print(f"SKIP PolicySync S8 EtherCalc (server down): {conn}")
        return 0

    entities = [
        ("acks", ACK_H, "Note"),
        ("expenses", EXP_H, "Description"),
        ("vehicles", VEH_H, "Name"),
        ("fuel", FUEL_H, "Notes"),
    ]
    for name, headers, note_col in entities:
        h = list(headers)
        note_i = h.index(note_col)
        ts_i = h.index("Updated At")
        sid_i = h.index("Sync ID")
        del_i = h.index("Deleted")

        def make_row(sid: str, ts: str, note: str, _h=h, _si=sid_i, _ti=ts_i, _ni=note_i, _di=del_i) -> List[str]:
            r = [""] * len(_h)
            r[_si], r[_ti], r[_ni], r[_di] = sid, ts, note, ""
            return r

        local = tab(h, [make_row("k1", "100", "local-old"), make_row("only-local", "50", "L")])
        remote_rows = [make_row("k1", "200", "remote-new"), make_row("only-remote", "60", "R")]

        room = f"ve-ps-{name}-{run_id}"
        be = EtherCalcBackend(base_url=base, room=room)
        be.write_rows(room, h, remote_rows, mode="replace")
        back = be.read_rows(room)
        rh = list(back.get("headers") or h)
        ridx = {col: i for i, col in enumerate(rh)}
        remote_norm = tab(h, [])
        for rr in back.get("rows") or []:
            if not any(str(c).strip() for c in rr):
                continue
            mapped = [""] * len(h)
            for j, col in enumerate(h):
                if col in ridx and ridx[col] < len(rr):
                    mapped[j] = str(rr[ridx[col]])
            if mapped[sid_i].strip():
                remote_norm["rows"].append(mapped)

        m = by_sid(merge_lww(local, remote_norm, h), h)
        assert_true(m["k1"][note_i] == "remote-new", f"S8 {name} remote wins: {m.get('k1')}")
        assert_true("only-local" in m and "only-remote" in m, f"S8 {name} keys {set(m)}")
        print(f"  PASS S8 EtherCalc remote merge ({name}) room={room}")

    # Multi-tab fuel: two rooms, independent
    h = FUEL_H
    note_i = h.index("Notes")
    for tab_name, local_note, remote_ts, expect in (
        ("honda", "honda-L", "50", "honda-L"),  # local newer
        ("ford", "ford-L", "300", "ford-R"),  # remote newer
    ):
        room = f"ve-ps-fuel-{tab_name}-{run_id}"
        local_ts = "200" if tab_name == "honda" else "100"
        remote_note = "ford-R" if tab_name == "ford" else "honda-R"
        local = tab(
            h,
            [["fx", "1", local_note, local_ts, ""]],
        )
        remote_rows = [["fx", "1", remote_note, remote_ts, ""]]
        be = EtherCalcBackend(base_url=base, room=room)
        be.write_rows(room, h, remote_rows, mode="replace")
        back = be.read_rows(room)
        ridx = {n: i for i, n in enumerate(back["headers"])}
        mapped_rows = []
        for rr in back["rows"]:
            mapped = [str(rr[ridx[c]]) if c in ridx and ridx[c] < len(rr) else "" for c in h]
            if mapped[0].strip():
                mapped_rows.append(mapped)
        m = by_sid(merge_lww(local, tab(h, mapped_rows), h), h)
        assert_true(m["fx"][note_i] == expect, f"S8 multi fuel {tab_name}: {m.get('fx')}")
        print(f"  PASS S8 multi-tab fuel ({tab_name}) room={room} expect={expect}")

    print(f"PASS PolicySync S8 EtherCalc scenarios base={base}")
    return 0


def main() -> int:
    run_pure_all()
    return run_s8_ethercalc()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL policysync_scenarios:", e, file=sys.stderr)
        raise SystemExit(1)
