"""ethercalc backend — M1 skeleton."""

from __future__ import annotations

from typing import Any, List

from .base import Backend


class EtherCalcBackend(Backend):
    backend_id = "ethercalc"

    def __init__(self, base_url: str, room: str, token_file: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.room = room
        self.token_file = token_file

    def test_connection(self) -> dict[str, Any]:
        return {
            "ok": False,
            "message": "ethercalc live client not wired; use MockBackend for conformance",
            "code": "unsupported",
        }

    def list_tabs(self) -> List[str]:
        # EtherCalc is often one sheet per room; expose as single tab name.
        return [self.room]

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        raise NotImplementedError("ethercalc ensure_headers")

    def read_rows(self, tab: str) -> dict[str, Any]:
        raise NotImplementedError("ethercalc read_rows")

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        raise NotImplementedError("ethercalc write_rows")
