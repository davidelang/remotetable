"""excel-graph backend — Microsoft Graph Excel Online (M1 skeleton)."""

from __future__ import annotations

from typing import Any, List

from .base import Backend


class ExcelGraphBackend(Backend):
    backend_id = "excel-graph"

    def __init__(self, token_file: str, workbook_id: str):
        self.token_file = token_file
        self.workbook_id = workbook_id

    def test_connection(self) -> dict[str, Any]:
        return {
            "ok": False,
            "message": "excel-graph live client not wired; use MockBackend for conformance",
            "code": "unsupported",
        }

    def list_tabs(self) -> List[str]:
        raise NotImplementedError("excel-graph list_tabs")

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        raise NotImplementedError("excel-graph ensure_headers")

    def read_rows(self, tab: str) -> dict[str, Any]:
        raise NotImplementedError("excel-graph read_rows")

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        raise NotImplementedError("excel-graph write_rows")
