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




def run_rate_limit_helpers() -> None:
    from remotetable.rate_limit import is_rate_limit_error
    assert_true(is_rate_limit_error("HTTP 429: quota exceeded"), "429 detect")
    assert_true(is_rate_limit_error("RateLimitExceeded"), "RateLimitExceeded")
    assert_true(is_rate_limit_error("read requests per minute"), "read rpm")
    assert_true(not is_rate_limit_error("not found"), "non-429")
    print("PASS rate_limit helpers")


def run_l2_and_policy() -> None:
    from remotetable.row_ops import push_table, propagate_soft_deletes

    be = MockBackend(
        {
            "tabs": {
                "Src": {
                    "headers": ["Sync ID", "Name", "Updated At", "Deleted"],
                    "rows": [
                        ["a", "A", "100", ""],
                        ["b", "B", "50", "true"],
                        ["c", "C-new", "200", ""],
                    ],
                },
                "Dst": {
                    "headers": ["Sync ID", "Name", "Updated At", "Deleted"],
                    "rows": [
                        ["a", "A-old", "150", ""],
                        ["b", "B", "50", ""],
                    ],
                },
            }
        }
    )
    rt = RemoteTable(be)

    many = rt.read_many(["Src", "Dst"])
    assert_true("Src" in many and "Dst" in many, "read_many keys")
    assert_true(len(many["Src"]["rows"]) == 3, "read_many src")

    u = rt.update_where("Dst", {"Sync ID": "a"}, {"Name": "A-set"})
    assert_true(u["updated"] == 1, str(u))
    assert_true(rt.read_rows("Dst")["rows"][0][1] == "A-set", "update_where")

    sd = rt.soft_delete_where("Dst", {"Sync ID": "a"}, "Deleted")
    assert_true(sd["updated"] == 1, str(sd))
    assert_true(rt.read_rows("Dst")["rows"][0][3] == "true", "soft_delete")

    # soft-delete propagate: source b tombstoned + dest has b → dest tombstone
    src = {"headers": ["Sync ID", "Deleted"], "rows": [["b", "true"], ["z", "true"]]}
    dst = {"headers": ["Sync ID", "Deleted"], "rows": [["b", ""], ["y", ""]]}
    new_dst, n = propagate_soft_deletes(src, dst, ["Sync ID"], "Deleted")
    assert_true(n == 1, f"propagate count {n}")
    assert_true(new_dst["rows"][0][1] == "true", "b tombstoned")
    assert_true(new_dst["rows"][1][1] == "", "y untouched; z no dest row")

    # expunge removes key
    be2 = MockBackend(
        {"tabs": {"T": {"headers": ["Sync ID", "X"], "rows": [["1", "a"], ["2", "b"]]}}}
    )
    rt2 = RemoteTable(be2)
    r = rt2.expunge_where("T", {"Sync ID": "1"})
    assert_true(r["removed"] == 1, str(r))
    assert_true(len(rt2.read_rows("T")["rows"]) == 1, "expunge size")
    assert_true(rt2.read_rows("T")["rows"][0][0] == "2", "expunge remaining")

    # push policy
    src_be = MockBackend(
        {
            "tabs": {
                "Local": {
                    "headers": ["syncId", "updatedAt", "deleted", "name"],
                    "rows": [
                        ["k1", "100", "", "one"],
                        ["k2", "200", "true", "two"],
                        ["k3", "300", "", "three"],
                    ],
                }
            }
        }
    )
    dst_be = MockBackend(
        {
            "tabs": {
                "Remote": {
                    "headers": ["Sync ID", "Updated At", "Deleted", "Name"],
                    "rows": [
                        ["k1", "150", "", "one-old"],
                        ["k2", "10", "", "two-old"],
                    ],
                }
            }
        }
    )
    unit = {
        "id": "ex",
        "direction": "push",
        "source": {"table": "Local"},
        "dest": {"table": "Remote"},
        "columns": [
            {"name": "Sync ID", "type": "string"},
            {"name": "Updated At", "type": "timestamp"},
            {"name": "Deleted", "type": "checkbox"},
            {"name": "Name", "type": "string"},
        ],
        "column_map": {
            "syncId": "Sync ID",
            "updatedAt": "Updated At",
            "deleted": "Deleted",
            "name": "Name",
        },
        "keys": ["syncId"],
        "timestamp": "updatedAt",
        "tombstone": {"column": "deleted", "true_values": ["true", "1", "yes"]},
    }
    result = push_table(src_be, dst_be, unit)
    remote = dst_be.read_rows("Remote")
    by = {r[0]: r for r in remote["rows"]}
    assert_true("k1" in by, "k1 present")
    # k1 source older than dest → keep dest name (skipped)
    assert_true(by["k1"][3] == "one-old", f"k1 not clobbered: {by['k1']}")
    assert_true(by["k2"][2] == "true", f"k2 soft-deleted: {by['k2']}")
    assert_true("k3" in by and by["k3"][3] == "three", f"k3 inserted: {by.get('k3')}")
    print("PASS L2 + soft-delete + push policy", result)




def run_type_coerce() -> None:
    from remotetable.cell_types import coerce, coerce_row
    from remotetable.row_ops import push_table

    assert_true(coerce("$12.50", "number") in ("12.5", "12.50") or coerce("$12.50", "number").startswith("12"), "number")
    assert_true(coerce("yes", "checkbox") == "true", "checkbox yes")
    assert_true(coerce("0", "checkbox") == "false", "checkbox 0")
    assert_true(coerce("1700000000", "timestamp") == "1700000000", "ts epoch")

    src = MockBackend({
        "tabs": {
            "L": {
                "headers": ["id", "amt", "flag", "ts"],
                "rows": [["k1", "$10.00", "YES", "1700000000000"]],
            }
        }
    })
    dst = MockBackend({"tabs": {"R": {"headers": ["ID", "Amount", "Flag", "Ts"], "rows": []}}})
    unit = {
        "id": "coerce",
        "direction": "push",
        "source": {"table": "L"},
        "dest": {"table": "R"},
        "columns": [
            {"name": "ID", "type": "string"},
            {"name": "Amount", "type": "number"},
            {"name": "Flag", "type": "checkbox"},
            {"name": "Ts", "type": "timestamp"},
        ],
        "column_map": {"id": "ID", "amt": "Amount", "flag": "Flag", "ts": "Ts"},
        "keys": ["id"],
    }
    push_table(src, dst, unit)
    row = dst.read_rows("R")["rows"][0]
    assert_true(row[0] == "k1", row)
    assert_true(row[1] in ("10", "10.0"), f"amt {row[1]}")
    assert_true(row[2] == "true", f"flag {row[2]}")
    assert_true(row[3] == "1700000000000", f"ts {row[3]}")
    print("PASS type coerce on push")


def run_merge_suite() -> None:
    from remotetable.row_ops import merge_tab_data, merge_tables

    headers = ["Sync ID", "Updated At", "Notes", "Deleted"]
    a = {
        "headers": headers,
        "rows": [
            ["k1", "100", "from-a", ""],
            ["k2", "200", "a-only", ""],
            ["k3", "50", "old-a", ""],
            ["k4", "300", "live-a", ""],
            ["k6", "100", "tie-a", ""],
        ],
    }
    b = {
        "headers": headers,
        "rows": [
            ["k1", "150", "from-b", ""],
            ["k3", "80", "", ""],
            ["k4", "400", "x", "true"],
            ["k5", "10", "b-only", ""],
            ["k6", "100", "tie-b", ""],
        ],
    }
    base_unit = {
        "keys": ["Sync ID"],
        "timestamp": "Updated At",
        "columns": [
            {"name": "Sync ID", "type": "string"},
            {"name": "Updated At", "type": "timestamp"},
            {"name": "Notes", "type": "string"},
            {"name": "Deleted", "type": "checkbox"},
        ],
        "tombstone": {"column": "Deleted", "true_values": ["true", "1", "yes"]},
    }

    for mode in ("union", "lww_row"):
        unit = {**base_unit, "merge_mode": mode}
        m = merge_tab_data(a, b, unit)
        by = {r[0]: r for r in m["rows"]}
        assert_true(set(by) == {"k1", "k2", "k3", "k4", "k5", "k6"}, f"{mode} keys {set(by)}")
        assert_true(by["k1"][2] == "from-b", f"{mode} k1 lww notes {by['k1']}")
        assert_true(by["k2"][2] == "a-only", f"{mode} k2")
        assert_true(by["k5"][2] == "b-only", f"{mode} k5")
        assert_true(by["k6"][2] == "tie-a", f"{mode} tie prefer a {by['k6']}")
        assert_true(by["k4"][3] == "true", f"{mode} k4 tombstone {by['k4']}")

    unit_ff = {**base_unit, "merge_mode": "field_fill"}
    m = merge_tab_data(a, b, unit_ff)
    by = {r[0]: r for r in m["rows"]}
    assert_true(by["k3"][2] == "old-a", f"field_fill k3 notes {by['k3']}")
    assert_true(by["k1"][2] == "from-b", f"field_fill k1 winner notes {by['k1']}")
    assert_true(by["k4"][3] == "true", f"field_fill k4 tomb {by['k4']}")

    be_a = MockBackend({"tabs": {"A": a}})
    be_b = MockBackend({"tabs": {"B": b}})
    res = merge_tables(
        be_a,
        be_b,
        {
            **base_unit,
            "merge_mode": "lww_row",
            "write_target": "b",
            "a": {"table": "A"},
            "b": {"table": "B"},
        },
    )
    assert_true(res["written"] is True, str(res))
    assert_true(len(be_b.read_rows("B")["rows"]) == 6, "write b count")
    print("PASS merge suite (union/lww_row/field_fill/tombstone/tie/write)")


def run_offline_file_backends() -> None:
    """json-book + csv-dir push/merge without network."""
    import tempfile
    from pathlib import Path

    from remotetable.backends.csv_dir import CsvDirBackend
    from remotetable.backends.json_book import JsonBookBackend
    from remotetable.row_ops import merge_tables, push_table

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src_path = td / "src.json"
        dst_path = td / "dst.json"
        src = JsonBookBackend(src_path)
        dst = JsonBookBackend(dst_path)
        src.write_rows(
            "T",
            ["Sync ID", "Name", "Updated At"],
            [["a", "Alpha", "100"], ["b", "Beta", "50"]],
            mode="replace",
        )
        # round-trip read
        reloaded = JsonBookBackend(src_path)
        assert_true(reloaded.read_rows("T")["rows"][0][1] == "Alpha", "json-book round-trip")
        unit = {
            "direction": "push",
            "source": {"table": "T"},
            "dest": {"table": "T"},
            "keys": ["Sync ID"],
            "timestamp": "Updated At",
            "columns": [
                {"name": "Sync ID", "type": "string"},
                {"name": "Name", "type": "string"},
                {"name": "Updated At", "type": "timestamp"},
            ],
            "column_map": {},
        }
        push_table(src, dst, unit)
        assert_true(len(JsonBookBackend(dst_path).read_rows("T")["rows"]) == 2, "push to json-book")

        # csv-dir with comma/quote
        cdir = td / "csvs"
        csv_be = CsvDirBackend(cdir)
        csv_be.write_rows(
            "Sheet One",
            ["A", "B"],
            [["1", "hello, world"], ["2", 'say "hi"']],
            mode="replace",
        )
        back = CsvDirBackend(cdir).read_rows("Sheet One")
        assert_true(back["rows"][0][1] == "hello, world", f"csv quote {back}")
        assert_true("Sheet One" in csv_be.list_tabs() or "Sheet One" in CsvDirBackend(cdir).list_tabs(), "csv tabs")

        # merge two json-books
        a_path, b_path = td / "ma.json", td / "mb.json"
        ja = JsonBookBackend(a_path)
        jb = JsonBookBackend(b_path)
        ja.write_rows(
            "M",
            ["Sync ID", "Updated At", "Notes"],
            [["k1", "100", "from-a"], ["k2", "10", "only-a"]],
            mode="replace",
        )
        jb.write_rows(
            "M",
            ["Sync ID", "Updated At", "Notes"],
            [["k1", "200", "from-b"]],
            mode="replace",
        )
        res = merge_tables(
            ja,
            jb,
            {
                "merge_mode": "lww_row",
                "write_target": "b",
                "a": {"table": "M"},
                "b": {"table": "M"},
                "keys": ["Sync ID"],
                "timestamp": "Updated At",
                "columns": [
                    {"name": "Sync ID", "type": "string"},
                    {"name": "Updated At", "type": "timestamp"},
                    {"name": "Notes", "type": "string"},
                ],
            },
        )
        assert_true(res["written"] is True, str(res))
        by = {r[0]: r for r in JsonBookBackend(b_path).read_rows("M")["rows"]}
        assert_true(by["k1"][2] == "from-b", by)
        assert_true("k2" in by, by)
    print("PASS offline file backends (json-book push/merge + csv-dir)")


def main() -> int:
    run_mock()
    run_rate_limit_helpers()
    run_l2_and_policy()
    run_type_coerce()
    run_merge_suite()
    run_offline_file_backends()
    run_live_optional()
    print("backends_required:", ", ".join(BackendIds.LIVE))
    print("backends_offline:", ", ".join(BackendIds.OFFLINE))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL:", e, file=sys.stderr)
        raise SystemExit(1)
