"""Zoho Sheet API v2 grid backend."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, List

from .base import Backend


class ZohoSheetBackend(Backend):
    backend_id = "zoho-sheet"

    def __init__(
        self,
        access_token: str | None = None,
        workbook_id: str | None = None,
        api_domain: str = "https://sheet.zoho.com",
        sheets: dict[str, str] | None = None,
        token_file: str | None = None,
    ):
        cfg: dict[str, Any] = {}
        if token_file:
            cfg = json.loads(open(token_file, encoding="utf-8").read())
        self.access_token = access_token or cfg.get("access_token") or cfg.get("token") or ""
        self.workbook_id = workbook_id or cfg.get("workbook_id") or cfg.get("item_id") or ""
        self.api_domain = (api_domain or cfg.get("api_domain") or "https://sheet.zoho.com").rstrip("/")
        self.sheets = sheets or cfg.get("sheets") or cfg.get("tables") or {}

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Zoho-oauthtoken {self.access_token}"}

    def _enc(self, name: str) -> str:
        return urllib.parse.quote(name, safe="")

    def _api(self, path: str = "") -> str:
        return f"{self.api_domain}/api/v2/{self.workbook_id}{path}"

    def _ws(self, tab: str) -> str:
        return (self.sheets.get(tab) or tab).strip() or tab

    def _http(self, method: str, url: str, body: str | None = None) -> str:
        data = body.encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self._auth())
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {text[:200]}") from e

    def test_connection(self) -> dict[str, Any]:
        if not self.access_token or not self.workbook_id:
            return {"ok": False, "message": "missing token or workbook_id", "code": "auth"}
        try:
            self.list_tabs()
            return {"ok": True, "message": "zoho workbook ok"}
        except Exception as e:
            return {"ok": False, "message": str(e)[:200], "code": "network"}

    def list_tabs(self) -> List[str]:
        if self.sheets:
            return sorted(self.sheets.keys())
        text = self._http("GET", self._api("/worksheets"))
        data = json.loads(text)
        worksheets = data.get("worksheets") or []
        out = []
        for item in worksheets:
            name = (item.get("worksheet_name") or item.get("name") or "").strip()
            if name:
                out.append(name)
        return out

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        name = self._ws(tab)
        existing = self.list_tabs()
        if name not in existing and name not in (self.sheets or {}).values():
            self._http(
                "POST",
                self._api("/worksheets"),
                json.dumps({"worksheet_name": name}),
            )
        data = self.read_rows(tab)
        if not data["headers"]:
            self._write_grid(name, [headers])
            return {"ok": True, "headers": list(headers)}
        merged = list(data["headers"])
        for h in headers:
            if h not in merged:
                merged.append(h)
        if merged != data["headers"]:
            rows = [list(r) + [""] * (len(merged) - len(r)) for r in data["rows"]]
            self._write_grid(name, [merged] + rows)
        return {"ok": True, "headers": merged}

    def read_rows(self, tab: str) -> dict[str, Any]:
        name = self._ws(tab)
        text = self._http("GET", self._api(f"/worksheets/{self._enc(name)}/cells"))
        grid = self._parse_cells(text)
        if not grid:
            return {"headers": [], "rows": []}
        return {"headers": grid[0], "rows": grid[1:]}

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        self.ensure_headers(tab, headers)
        name = self._ws(tab)
        cur = self.read_rows(tab)
        h = cur["headers"] or list(headers)
        body_rows = rows if mode == "replace" else cur["rows"] + list(rows)
        self._write_grid(name, [h] + body_rows)
        return {"written": len(rows), "mode": mode}

    def _write_grid(self, worksheet: str, grid: list[list[str]]) -> None:
        cells = []
        for r_i, row in enumerate(grid):
            for c_i, val in enumerate(row):
                cells.append({"row": r_i + 1, "column": c_i + 1, "value": val})
        self._http(
            "POST",
            self._api(f"/worksheets/{self._enc(worksheet)}/cells"),
            json.dumps({"cells": cells}),
        )

    def _parse_cells(self, body: str) -> list[list[str]]:
        if not body.strip():
            return []
        data = json.loads(body)
        cells = data.get("cells") or data.get("range_details") or []
        sparse: dict[tuple[int, int], str] = {}
        max_r = max_c = 0
        for cell in cells:
            r = int(cell.get("row") or cell.get("row_index") or 0)
            c = int(cell.get("column") or cell.get("column_index") or 0)
            if r <= 0 or c <= 0:
                continue
            sparse[(r, c)] = str(cell.get("value") or cell.get("display_value") or "")
            max_r = max(max_r, r)
            max_c = max(max_c, c)
        if not max_r or not max_c:
            return []
        return [[sparse.get((r, c), "") for c in range(1, max_c + 1)] for r in range(1, max_r + 1)]
