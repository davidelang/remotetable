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
