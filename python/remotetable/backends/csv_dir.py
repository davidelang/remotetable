"""csv-dir backend — one UTF-8 CSV file per tab under a directory (offline L0)."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List

from .base import Backend

_SAFE_TAB = re.compile(r"[^\w.\- ]+", re.UNICODE)


def _stem_to_tab(name: str) -> str:
    return name


def _tab_to_filename(tab: str) -> str:
    # Preserve readable names; strip path separators only
    safe = tab.replace("/", "_").replace("\\", "_").strip() or "sheet"
    if not safe.lower().endswith(".csv"):
        safe = f"{safe}.csv"
    return safe


class CsvDirBackend(Backend):
    """
    Directory of ``*.csv`` files; **tab name** = file stem (filename without ``.csv``).

    Read/write UTF-8 with standard CSV quoting (commas, quotes, newlines).
    Each ``write_rows`` rewrites that tab's file. Missing file → empty tab.
    """

    backend_id = "csv-dir"

    def __init__(self, path: str | Path):
        self.dir = Path(path)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _file_for(self, tab: str) -> Path:
        return self.dir / _tab_to_filename(tab)

    def test_connection(self) -> dict[str, Any]:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            return {"ok": True, "message": f"csv-dir path={self.dir} tabs={len(self.list_tabs())}"}
        except Exception as e:
            return {"ok": False, "message": str(e)[:200], "code": "io"}

    def list_tabs(self) -> List[str]:
        if not self.dir.is_dir():
            return []
        out = []
        for p in sorted(self.dir.glob("*.csv")):
            out.append(p.stem)
        return out

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        data = self.read_rows(tab)
        cur = list(data["headers"] or [])
        if not cur:
            self.write_rows(tab, list(headers), [], mode="replace")
            return {"ok": True, "headers": list(headers)}
        new_h = list(cur)
        for h in headers:
            if h not in new_h:
                new_h.append(h)
        if new_h != cur:
            rows = [list(r) for r in data["rows"]]
            for r in rows:
                while len(r) < len(new_h):
                    r.append("")
            self.write_rows(tab, new_h, rows, mode="replace")
        return {"ok": True, "headers": new_h}

    def read_rows(self, tab: str) -> dict[str, Any]:
        f = self._file_for(tab)
        if not f.is_file():
            return {"headers": [], "rows": []}
        with f.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            all_rows = [list(r) for r in reader]
        if not all_rows:
            return {"headers": [], "rows": []}
        headers = [str(c) for c in all_rows[0]]
        rows = []
        for r in all_rows[1:]:
            row = [str(c) for c in r]
            while len(row) < len(headers):
                row.append("")
            rows.append(row[: len(headers)] if len(row) > len(headers) else row)
        return {"headers": headers, "rows": rows}

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        if mode == "replace":
            hdr = list(headers)
            body = [list(r) for r in rows]
        else:
            existing = self.read_rows(tab)
            hdr = list(existing["headers"] or headers)
            body = [list(r) for r in existing["rows"]]
            for r in rows:
                row = list(r)
                while len(row) < len(hdr):
                    row.append("")
                body.append(row[: len(hdr)])
        if not hdr and body:
            # invent ColN if only rows (rare)
            width = max(len(r) for r in body)
            hdr = [f"Col{i}" for i in range(width)]
        f = self._file_for(tab)
        with f.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            if hdr:
                w.writerow(hdr)
            for r in body:
                row = list(r)
                while len(row) < len(hdr):
                    row.append("")
                w.writerow(row[: len(hdr)])
        return {"written": len(rows)}
