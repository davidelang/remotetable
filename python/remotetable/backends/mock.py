from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from .base import Backend


class MockBackend(Backend):
    """In-memory multi-tab store for conformance (no network)."""

    backend_id = "mock"

    def __init__(self, book: Dict[str, Any]):
        # book: { "tabs": { name: { headers, rows } } }
        self._tabs: Dict[str, Dict[str, Any]] = deepcopy(book.get("tabs") or {})

    def test_connection(self) -> dict[str, Any]:
        return {"ok": True, "message": "mock"}

    def list_tabs(self) -> List[str]:
        return sorted(self._tabs.keys())

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        if tab not in self._tabs:
            self._tabs[tab] = {"headers": list(headers), "rows": []}
            return {"ok": True, "headers": list(headers)}
        cur = list(self._tabs[tab].get("headers") or [])
        for h in headers:
            if h not in cur:
                cur.append(h)
                # pad existing rows
                for row in self._tabs[tab]["rows"]:
                    while len(row) < len(cur):
                        row.append("")
        self._tabs[tab]["headers"] = cur
        return {"ok": True, "headers": cur}

    def read_rows(self, tab: str) -> dict[str, Any]:
        t = self._tabs.get(tab)
        if not t:
            return {"headers": [], "rows": []}
        return {"headers": list(t["headers"]), "rows": [list(r) for r in t["rows"]]}

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        self.ensure_headers(tab, headers)
        if mode == "replace":
            self._tabs[tab]["rows"] = [list(r) for r in rows]
            return {"written": len(rows)}
        # append
        for r in rows:
            row = list(r)
            while len(row) < len(self._tabs[tab]["headers"]):
                row.append("")
            self._tabs[tab]["rows"].append(row)
        return {"written": len(rows)}

    def read_many(self, tabs):
        return {t: self.read_rows(t) for t in tabs}

    def write_many(self, updates, mode="replace"):
        n = 0
        for tab, payload in updates.items():
            headers = payload.get("headers") or []
            rows = payload.get("rows") or []
            n += self.write_rows(tab, headers, rows, mode=mode)["written"]
        return {"written": n}

    def update_where(self, tab, filt, set_fields):
        from remotetable.row_ops import apply_set, header_index, matches_filter
        data = self.read_rows(tab)
        headers = data["headers"]
        if not headers:
            return {"updated": 0}
        idx = header_index(headers)
        n = 0
        new_rows = []
        for row in data["rows"]:
            if matches_filter(row, idx, filt):
                n += 1
                new_rows.append(apply_set(row, headers, set_fields))
            else:
                new_rows.append(list(row))
        if n:
            self.write_rows(tab, headers, new_rows, mode="replace")
        return {"updated": n}

    def soft_delete_where(self, tab, filt, tombstone_column, true_value="true"):
        return self.update_where(tab, filt, {tombstone_column: true_value})

    def expunge_where(self, tab, filt):
        from remotetable.row_ops import header_index, matches_filter
        data = self.read_rows(tab)
        headers = data["headers"]
        if not headers:
            return {"removed": 0}
        idx = header_index(headers)
        kept = [list(r) for r in data["rows"] if not matches_filter(r, idx, filt)]
        removed = len(data["rows"]) - len(kept)
        if removed:
            self.write_rows(tab, headers, kept, mode="replace")
        return {"removed": removed}

