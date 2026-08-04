#!/usr/bin/env python3
"""remotetable host CLI — mock offline; live via --token-file.

Global flags (--backend, --token-file, …) may appear before **or** after the
subcommand.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import (
    BackendIds,
    CsvDirBackend,
    EtherCalcBackend,
    ExcelGraphBackend,
    GoogleSheetsBackend,
    JsonBookBackend,
    LocalBackend,
    MockBackend,
    RemoteTable,
    RowDbBackend,
    ZohoSheetBackend,
)

COMMANDS = (
    "test-connection",
    "list-tabs",
    "read-rows",
    "write-rows",
    "conformance",
    "push",
    "copy",
    "merge",
    "sheets-smoke",
)
# Flags that take a value (global)
GLOBAL_VALUE_FLAGS = {
    "--backend",
    "--token-file",
    "--fixture",
    "--path",
    "--spreadsheet-id",
    "--item-id",
    "--base-url",
    "--room",
    "--config",
}


def normalize_argv(argv: list[str]) -> list[str]:
    """Rewrite argv so global options precede the subcommand for argparse."""
    cmd_idx = None
    for i, a in enumerate(argv):
        if a in COMMANDS:
            cmd_idx = i
            break
    if cmd_idx is None:
        return argv

    before = argv[:cmd_idx]
    cmd = argv[cmd_idx]
    after = argv[cmd_idx + 1 :]

    globals_out: list[str] = []
    other_before: list[str] = []
    sub_args: list[str] = []

    def take_global(seq: list[str], i: int, into: list[str]) -> int:
        a = seq[i]
        if a in GLOBAL_VALUE_FLAGS:
            into.append(a)
            if i + 1 < len(seq) and not seq[i + 1].startswith("-"):
                into.append(seq[i + 1])
                return i + 2
            return i + 1
        if a.startswith("--") and "=" in a and a.split("=", 1)[0] in GLOBAL_VALUE_FLAGS:
            into.append(a)
            return i + 1
        return -1

    i = 0
    while i < len(before):
        n = take_global(before, i, globals_out)
        if n >= 0:
            i = n
            continue
        other_before.append(before[i])
        i += 1

    i = 0
    while i < len(after):
        n = take_global(after, i, globals_out)
        if n >= 0:
            i = n
            continue
        sub_args.append(after[i])
        i += 1

    # Preserve stray pre-command tokens (help argparse surface errors)
    return other_before + globals_out + [cmd] + sub_args


def build_backend_from_spec(spec: dict | None, *, default_path: str | None = None):
    """Build backend from config endpoint object: {backend, path, table, ...}."""
    spec = spec or {}
    bid = (spec.get("backend") or BackendIds.MOCK).strip()
    path = spec.get("path") or default_path
    if bid == BackendIds.MOCK:
        book = spec.get("book") or {"tabs": {}}
        if spec.get("fixture"):
            book = json.loads(Path(spec["fixture"]).read_text(encoding="utf-8"))
        return MockBackend(book)
    if bid in (BackendIds.LOCAL, BackendIds.MEMORY):
        book = spec.get("book") or {"tabs": {}}
        return LocalBackend(book)
    if bid == BackendIds.JSON_BOOK:
        if not path:
            raise SystemExit("json-book requires path")
        return JsonBookBackend(path)
    if bid == BackendIds.CSV_DIR:
        if not path:
            raise SystemExit("csv-dir requires path")
        return CsvDirBackend(path)
    raise SystemExit(f"build_backend_from_spec: unsupported offline backend {bid}")


def build_backend(args: argparse.Namespace):
    bid = args.backend
    if bid == BackendIds.MOCK:
        book = {}
        if args.fixture:
            book = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        return MockBackend(book)
    if bid in (BackendIds.LOCAL, BackendIds.MEMORY):
        book = {}
        if args.fixture:
            book = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        return LocalBackend(book)
    if bid == BackendIds.JSON_BOOK:
        path = getattr(args, "path", None)
        if not path:
            raise SystemExit("json-book requires --path FILE.json")
        return JsonBookBackend(path)
    if bid == BackendIds.CSV_DIR:
        path = getattr(args, "path", None)
        if not path:
            raise SystemExit("csv-dir requires --path DIR")
        return CsvDirBackend(path)
    if bid in BackendIds.ROW_DB:
        if not args.token_file:
            raise SystemExit("--token-file required for row-db backends (JSON with token + tables)")
        return RowDbBackend(bid, "", "", {}, token_file=args.token_file)
    if bid == BackendIds.ZOHO_SHEET:
        if not args.token_file:
            raise SystemExit("--token-file required for zoho-sheet (access_token + workbook_id)")
        return ZohoSheetBackend(token_file=args.token_file)
    if bid in BackendIds.OFFLINE:
        raise SystemExit(f"offline backend {bid} needs --path or --fixture")
    if not args.token_file and bid != BackendIds.ETHERCALC:
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
    if bid in (BackendIds.ONLYOFFICE, BackendIds.COLLABORA):
        raise SystemExit(
            f"backend {bid}: deferred (no headless row API). AAR exposes DeferredBackend for testConnection only."
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
    reader = csv.reader(raw.splitlines())
    all_rows = [list(r) for r in reader]
    if not all_rows:
        return [], []
    return [str(c) for c in all_rows[0]], [[str(c) for c in r] for r in all_rows[1:]]




def cmd_conformance(_args) -> int:
    """Run offline conformance harness (preferred agent test path)."""
    import subprocess
    root = Path(__file__).resolve().parents[2]
    harness = root / "conformance" / "harness.py"
    r = subprocess.run([sys.executable, str(harness)], cwd=str(root))
    return r.returncode


def _endpoint_backend(cfg: dict, unit: dict, side: str):
    """Resolve source/dest or a/b endpoint for offline push/merge."""
    # unit-level endpoint object
    ep = unit.get(side) or {}
    if side == "source":
        ep = unit.get("source") or unit.get("a") or ep
    if side == "dest":
        ep = unit.get("dest") or unit.get("b") or ep
    if side == "a":
        ep = unit.get("a") or unit.get("source") or ep
    if side == "b":
        ep = unit.get("b") or unit.get("dest") or ep
    bid = (ep.get("backend") or "").strip()
    path = ep.get("path")
    if bid in (BackendIds.JSON_BOOK, BackendIds.CSV_DIR) or path:
        return build_backend_from_spec(
            {"backend": bid or BackendIds.JSON_BOOK, "path": path, "fixture": ep.get("fixture")},
        )
    # embedded books
    if side in ("source", "a"):
        book = cfg.get("source_book") or cfg.get("book_a") or cfg.get("a_book") or {"tabs": cfg.get("source_tabs") or cfg.get("a_tabs") or {}}
    else:
        book = cfg.get("dest_book") or cfg.get("book_b") or cfg.get("b_book") or {"tabs": cfg.get("dest_tabs") or cfg.get("b_tabs") or {}}
    return MockBackend(book)


def cmd_push(args) -> int:
    """Directional push from JSON config (mock or file backends; no network)."""
    from .row_ops import push_table

    if not getattr(args, "config", None):
        raise SystemExit("push requires --config path.json")
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    tables = cfg.get("tables") or ([cfg] if cfg.get("keys") else [])
    if not tables:
        raise SystemExit("config needs tables[] or a single table unit")
    results = []
    dest_preview = None
    for unit in tables:
        # force replace-like full write for copy alias when requested
        if getattr(args, "copy_mode", False):
            unit = dict(unit)
            unit.setdefault("direction", "push")
        src_be = _endpoint_backend(cfg, unit, "source")
        dest_be = _endpoint_backend(cfg, unit, "dest")
        # normalize source/dest table keys for push_table
        u = dict(unit)
        if "source" not in u and "a" in u:
            u["source"] = u["a"]
        if "dest" not in u and "b" in u:
            u["dest"] = u["b"]
        results.append(push_table(src_be, dest_be, u))
        tab = (u.get("dest") or {}).get("table") or (u.get("dest") or {}).get("tab") or ""
        if tab:
            dest_preview = dest_be.read_rows(tab)
    print(json.dumps({"ok": True, "results": results, "dest": dest_preview}, indent=2))
    return 0


def cmd_copy(args) -> int:
    """Alias for push (offline copy/convert between endpoints)."""
    args.copy_mode = True
    return cmd_push(args)


def cmd_merge(args) -> int:
    """A↔B merge from JSON config (mock or file backends; no network)."""
    from .row_ops import merge_tables

    if not getattr(args, "config", None):
        raise SystemExit("merge requires --config path.json")
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    tables = cfg.get("tables") or ([cfg] if cfg.get("keys") else [])
    if not tables:
        raise SystemExit("config needs tables[] or a single merge unit")
    results = []
    for unit in tables:
        be_a = _endpoint_backend(cfg, unit, "a")
        be_b = _endpoint_backend(cfg, unit, "b")
        results.append(merge_tables(be_a, be_b, unit))
    print(json.dumps({"ok": True, "results": results}, indent=2))
    return 0


def cmd_sheets_smoke(args) -> int:
    """Optional live google-sheets test-connection (env or flags)."""
    import os
    token = args.token_file or os.environ.get("REMOTETABLE_TOKEN_FILE", "")
    if not token:
        print("SKIP sheets-smoke: set --token-file or REMOTETABLE_TOKEN_FILE")
        return 0
    sid = args.spreadsheet_id or os.environ.get("REMOTETABLE_SPREADSHEET_ID")
    be = GoogleSheetsBackend(token, spreadsheet_id=sid)
    rt = RemoteTable(be)
    print(json.dumps(rt.test_connection(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    argv_n = normalize_argv(raw)

    ap = argparse.ArgumentParser(prog="remotetable", description="remotetable host CLI")
    ap.add_argument(
        "--backend",
        default=BackendIds.MOCK,
        choices=list(BackendIds.ALL),
        help="backend id (before or after subcommand)",
    )
    ap.add_argument("--token-file", default=None, help="JSON token file (live backends)")
    ap.add_argument("--fixture", default=None, help="mock/local book JSON path")
    ap.add_argument("--path", default=None, help="json-book file or csv-dir directory")
    ap.add_argument("--spreadsheet-id", default=None)
    ap.add_argument("--item-id", default=None, help="excel-graph workbook item id")
    ap.add_argument("--base-url", default=None, help="ethercalc base URL")
    ap.add_argument("--room", default=None, help="ethercalc room")
    ap.add_argument("--config", default=None, help="JSON config for push (mock books + tables)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("test-connection")
    sub.add_parser("list-tabs")
    p_read = sub.add_parser("read-rows")
    p_read.add_argument("--tab", required=True)
    p_write = sub.add_parser("write-rows")
    p_write.add_argument("--tab", required=True)
    p_write.add_argument("--mode", choices=["append", "replace"], default="append")
    p_write.add_argument("--format", choices=["json", "csv"], default="json")
    sub.add_parser(
        "conformance",
        help="run offline conformance/harness.py (preferred agent test path)",
    )
    sub.add_parser("push", help="directional push from --config JSON (mock/file backends)")
    sub.add_parser("copy", help="alias of push for offline copy/convert")
    sub.add_parser("merge", help="A↔B merge from --config JSON (mock/file backends)")
    sub.add_parser(
        "sheets-smoke",
        help="optional live google-sheets test-connection (token env/flags)",
    )

    args = ap.parse_args(argv_n)

    # Test-surface commands (no backend factory required for mock push / harness)
    if args.cmd == "conformance":
        return cmd_conformance(args)
    if args.cmd == "push":
        return cmd_push(args)
    if args.cmd == "copy":
        return cmd_copy(args)
    if args.cmd == "merge":
        return cmd_merge(args)
    if args.cmd == "sheets-smoke":
        return cmd_sheets_smoke(args)

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
            headers = []
        out = rt.write_rows(args.tab, headers, rows, mode=args.mode)
        print(json.dumps(out, indent=2))
        return 0
    raise SystemExit(f"unknown cmd {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
