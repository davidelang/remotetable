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
