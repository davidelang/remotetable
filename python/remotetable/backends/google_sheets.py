"""google-sheets backend — M1 skeleton (token-file auth; live ops TBD)."""

from __future__ import annotations

from typing import Any, List

from .base import Backend


class GoogleSheetsBackend(Backend):
    backend_id = "google-sheets"

    def __init__(self, token_file: str, spreadsheet_id: str):
        self.token_file = token_file
        self.spreadsheet_id = spreadsheet_id

    def test_connection(self) -> dict[str, Any]:
        # Live OAuth/Sheets not implemented in mock-first M1 skeleton.
        return {
            "ok": False,
            "message": "google-sheets live client not wired; use MockBackend for conformance",
            "code": "unsupported",
        }

    def list_tabs(self) -> List[str]:
        raise NotImplementedError("google-sheets list_tabs")

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        raise NotImplementedError("google-sheets ensure_headers")

    def read_rows(self, tab: str) -> dict[str, Any]:
        raise NotImplementedError("google-sheets read_rows")

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        raise NotImplementedError("google-sheets write_rows")
