"""excel-graph — Microsoft Graph Excel Online workbook API (token file)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, List

from .base import Backend


class ExcelGraphBackend(Backend):
    """
    Token file JSON (v1):
      {
        "access_token": "...",
        "drive_id": "optional",
        "item_id": "workbook driveItem id",
        "workbook_path": "optional path alternative"
      }
    Uses Graph: /me/drive/items/{id}/workbook/worksheets
    """

    backend_id = "excel-graph"
    GRAPH = "https://graph.microsoft.com/v1.0"

    def __init__(self, token_file: str, item_id: str | None = None):
        cfg = json.loads(open(token_file, encoding="utf-8").read())
        self.access_token = cfg.get("access_token") or cfg.get("token") or ""
        self.item_id = item_id or cfg.get("item_id") or ""
        self.drive_id = cfg.get("drive_id")

    def _root(self) -> str:
        if self.drive_id:
            return f"{self.GRAPH}/drives/{self.drive_id}/items/{self.item_id}/workbook"
        return f"{self.GRAPH}/me/drive/items/{self.item_id}/workbook"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _req(self, method: str, url: str, body: dict | None = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"excel-graph HTTP {e.code}: {err}") from e

    def test_connection(self) -> dict[str, Any]:
        if not self.access_token or not self.item_id:
            return {"ok": False, "message": "missing access_token or item_id", "code": "auth"}
        try:
            data = self._req("GET", f"{self._root()}/worksheets")
            n = len(data.get("value") or [])
            return {"ok": True, "message": f"workbook ok sheets={n}"}
        except Exception as e:
            return {"ok": False, "message": str(e)[:200], "code": "network"}

    def list_tabs(self) -> List[str]:
        data = self._req("GET", f"{self._root()}/worksheets")
        return [s.get("name", "") for s in (data.get("value") or []) if s.get("name")]

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        cur = self.read_rows(tab)
        if not cur["headers"]:
            self._write_range(tab, "A1", [list(headers)])
            return {"ok": True, "headers": list(headers)}
        new_h = list(cur["headers"])
        for h in headers:
            if h not in new_h:
                new_h.append(h)
        if new_h != cur["headers"]:
            self._write_range(tab, "A1", [new_h])
        return {"ok": True, "headers": new_h}

    def read_rows(self, tab: str) -> dict[str, Any]:
        # usedRange values
        name = urllib.parse.quote(tab)
        data = self._req("GET", f"{self._root()}/worksheets('{name}')/usedRange")
        values = data.get("values") or []
        if not values:
            return {"headers": [], "rows": []}
        headers = [str(x) for x in values[0]]
        rows = []
        for r in values[1:]:
            row = [str(c) for c in r]
            while len(row) < len(headers):
                row.append("")
            rows.append(row)
        return {"headers": headers, "rows": rows}

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        if mode == "replace":
            body = [list(headers)] + [list(r) for r in rows]
            self._write_range(tab, "A1", body)
            return {"written": len(rows)}
        existing = self.read_rows(tab)
        if not existing["headers"]:
            self._write_range(tab, "A1", [list(headers)] + [list(r) for r in rows])
            return {"written": len(rows)}
        start = len(existing["rows"]) + 2
        self._write_range(tab, f"A{start}", [list(r) for r in rows])
        return {"written": len(rows)}

    def _write_range(self, tab: str, a1: str, values: List[List[str]]) -> None:
        name = urllib.parse.quote(tab)
        # address like Sheet1!A1
        addr = urllib.parse.quote(f"{tab}!{a1}")
        url = f"{self._root()}/worksheets('{name}')/range(address='{a1}')"
        self._req("PATCH", url, {"values": values})
