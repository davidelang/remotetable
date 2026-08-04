"""local (memory) backend — explicit multi-tab in-memory book (offline L0)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .mock import MockBackend


class LocalBackend(MockBackend):
    """
    Same semantics as mock, backend id ``local`` (or alias ``memory``).
    Optional ``snapshot()`` for export without a path.
    """

    backend_id = "local"

    def __init__(self, book: Optional[Dict[str, Any]] = None):
        super().__init__(book or {"tabs": {}})

    def snapshot(self) -> Dict[str, Any]:
        tabs = {}
        for name in self.list_tabs():
            data = self.read_rows(name)
            tabs[name] = {"headers": data["headers"], "rows": data["rows"]}
        return {"tabs": tabs}

    def test_connection(self) -> dict[str, Any]:
        return {"ok": True, "message": f"local memory tabs={len(self.list_tabs())}"}
