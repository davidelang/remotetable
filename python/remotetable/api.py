from __future__ import annotations

from typing import Any, List, Sequence

from .backends.base import Backend


class RemoteTable:
    """Thin facade over a Backend implementation."""

    def __init__(self, backend: Backend):
        self.backend = backend

    def test_connection(self) -> dict[str, Any]:
        return self.backend.test_connection()

    def list_tabs(self) -> dict[str, Any]:
        return {"tabs": self.backend.list_tabs()}

    def ensure_headers(self, tab: str, headers: Sequence[str]) -> dict[str, Any]:
        return self.backend.ensure_headers(tab, list(headers))

    def read_rows(self, tab: str) -> dict[str, Any]:
        return self.backend.read_rows(tab)

    def write_rows(
        self,
        tab: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        return self.backend.write_rows(tab, list(headers), [list(r) for r in rows], mode=mode)

    def read_many(self, tabs):
        if hasattr(self.backend, "read_many"):
            return self.backend.read_many(tabs)
        return {t: self.read_rows(t) for t in tabs}

    def write_many(self, updates, mode="replace"):
        if hasattr(self.backend, "write_many"):
            return self.backend.write_many(updates, mode=mode)
        n = 0
        for tab, payload in updates.items():
            n += self.write_rows(tab, payload.get("headers") or [], payload.get("rows") or [], mode=mode)["written"]
        return {"written": n}

    def update_where(self, tab, filt, set_fields):
        return self.backend.update_where(tab, filt, set_fields)

    def soft_delete_where(self, tab, filt, tombstone_column, true_value="true"):
        return self.backend.soft_delete_where(tab, filt, tombstone_column, true_value)

    def expunge_where(self, tab, filt):
        return self.backend.expunge_where(tab, filt)

