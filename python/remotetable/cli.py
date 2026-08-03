#!/usr/bin/env python3
"""remotetable host CLI — mock offline; live via --token-file."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import (
    BackendIds,
    EtherCalcBackend,
    ExcelGraphBackend,
    GoogleSheetsBackend,
    MockBackend,
    RemoteTable,
)


def build_backend(args: argparse.Namespace):
    bid = args.backend
    if bid == BackendIds.MOCK:
        book = {}
        if args.fixture:
            book = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        return MockBackend(book)
    if not args.token_file and bid != BackendIds.ETHERCALC:
        # ethercalc may pass base/room without token file
        if not (args.base_url and args.room):
            raise SystemExit("--token-file required for live backends (or ethercalc --base-url/--room)")
    if bid == BackendIds.GOOGLE_SHEETS:
        return GoogleSheetsBackend(args.token_file, spreadsheet_id=args.spreadsheet_id)
    if bid == BackendIds.EXCEL_GRAPH:
        return ExcelGraphBackend(args.token_file, item_id=args.item_id)
    if bid == BackendIds.ETHERCALC:
        return EtherCalcBackend(
            base_url=args.base_url,
            room=args.room,
            token_file=args.token_file,
        )
    raise SystemExit(f"unknown backend: {bid}")


def load_rows_stdin(fmt: str) -> tuple[list[str], list[list[str]]]:
    raw = sys.stdin.read()
    if not raw.strip():
        return [], []
    if fmt == "json":
        data = json.loads(raw)
        if isinstance(data, dict):
            headers = list(data.get("headers") or [])
            rows = [list(r) for r in (data.get("rows") or [])]
            return headers, rows
        if isinstance(data, list) and data and isinstance(data[0], list):
            headers = [str(c) for c in data[0]]
            rows = [[str(c) for c in r] for r in data[1:]]
            return headers, rows
        raise SystemExit("JSON must be {headers,rows} or [[header],...rows]")
    # csv
    reader = csv.reader(raw.splitlines())
    all_rows = [list(r) for r in reader]
    if not all_rows:
        return [], []
    return [str(c) for c in all_rows[0]], [[str(c) for c in r] for r in all_rows[1:]]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="remotetable", description="remotetable host CLI")
    ap.add_argument(
        "--backend",
        default=BackendIds.MOCK,
        choices=list(BackendIds.ALL),
        help="backend id",
    )
    ap.add_argument("--token-file", default=None, help="JSON token file (live backends)")
    ap.add_argument("--fixture", default=None, help="mock book JSON path")
    ap.add_argument("--spreadsheet-id", default=None)
    ap.add_argument("--item-id", default=None, help="excel-graph workbook item id")
    ap.add_argument("--base-url", default=None, help="ethercalc base URL")
    ap.add_argument("--room", default=None, help="ethercalc room")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("test-connection")
    sub.add_parser("list-tabs")
    p_read = sub.add_parser("read-rows")
    p_read.add_argument("--tab", required=True)
    p_write = sub.add_parser("write-rows")
    p_write.add_argument("--tab", required=True)
    p_write.add_argument("--mode", choices=["append", "replace"], default="append")
    p_write.add_argument("--format", choices=["json", "csv"], default="json")

    args = ap.parse_args(argv)
    be = build_backend(args)
    rt = RemoteTable(be)

    if args.cmd == "test-connection":
        print(json.dumps(rt.test_connection(), indent=2))
        return 0
    if args.cmd == "list-tabs":
        print(json.dumps(rt.list_tabs(), indent=2))
        return 0
    if args.cmd == "read-rows":
        print(json.dumps(rt.read_rows(args.tab), indent=2))
        return 0
    if args.cmd == "write-rows":
        headers, rows = load_rows_stdin(args.format)
        if not headers and rows:
            raise SystemExit("write-rows needs headers")
        if not headers:
            # allow empty replace with no stdin
            headers = []
        out = rt.write_rows(args.tab, headers, rows, mode=args.mode)
        print(json.dumps(out, indent=2))
        return 0
    raise SystemExit(f"unknown cmd {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
