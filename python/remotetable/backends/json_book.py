"""json-book backend — durable multi-tab JSON file (offline L0)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import Backend
from .mock import MockBackend


class JsonBookBackend(Backend):
    """
    File-backed multi-tab book.

    On-disk shape (same as harness fixtures)::

        { "tabs": { "TabName": { "headers": [...], "rows": [[...], ...] } } }

    **Persistence:** each successful ``write_rows`` (and structural tab ops)
    flushes the whole book to ``path`` immediately (simple durable offline use).
    """

    backend_id = "json-book"

    def __init__(self, path: str | Path, book: Optional[Dict[str, Any]] = None):
        self.path = Path(path)
        if book is not None:
            initial = book
        elif self.path.is_file():
            initial = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            initial = {"tabs": {}}
        self._mem = MockBackend(initial)
        # re-id for identity
        self._mem.backend_id = self.backend_id  # type: ignore[attr-defined]

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # rebuild book from mock internal
        tabs = {}
        for name in self._mem.list_tabs():
            data = self._mem.read_rows(name)
            tabs[name] = {"headers": data["headers"], "rows": data["rows"]}
        payload = {"tabs": tabs}
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_connection(self) -> dict[str, Any]:
        try:
            parent = self.path.parent
            parent.mkdir(parents=True, exist_ok=True)
            return {
                "ok": True,
                "message": f"json-book path={self.path} exists={self.path.is_file()} tabs={len(self.list_tabs())}",
            }
        except Exception as e:
            return {"ok": False, "message": str(e)[:200], "code": "io"}

    def list_tabs(self) -> List[str]:
        return self._mem.list_tabs()

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        out = self._mem.ensure_headers(tab, headers)
        self._flush()
        return out

    def read_rows(self, tab: str) -> dict[str, Any]:
        return self._mem.read_rows(tab)

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        out = self._mem.write_rows(tab, headers, rows, mode=mode)
        self._flush()
        return out

    def read_many(self, tabs):
        return self._mem.read_many(tabs)

    def write_many(self, updates, mode="replace"):
        out = self._mem.write_many(updates, mode=mode)
        self._flush()
        return out

    def update_where(self, tab, filt, set_fields):
        out = self._mem.update_where(tab, filt, set_fields)
        if out.get("updated"):
            self._flush()
        return out

    def soft_delete_where(self, tab, filt, tombstone_column, true_value="true"):
        out = self._mem.soft_delete_where(tab, filt, tombstone_column, true_value)
        if out.get("updated"):
            self._flush()
        return out

    def expunge_where(self, tab, filt):
        out = self._mem.expunge_where(tab, filt)
        if out.get("removed"):
            self._flush()
        return out
