"""google-sheets backend — Sheets API v4 with plain JSON token file."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, List

from .base import Backend


class GoogleSheetsBackend(Backend):
    """
    Token file JSON (v1):
      {
        "access_token": "...",
        "spreadsheet_id": "..."
      }
    Optional: "token_type" (default Bearer).
    """

    backend_id = "google-sheets"
    API = "https://sheets.googleapis.com/v4/spreadsheets"

    def __init__(self, token_file: str, spreadsheet_id: str | None = None):
        self.token_file = token_file
        cfg = json.loads(open(token_file, encoding="utf-8").read())
        self.access_token = cfg.get("access_token") or cfg.get("token") or ""
        self.spreadsheet_id = spreadsheet_id or cfg.get("spreadsheet_id") or ""
        self.token_type = cfg.get("token_type") or "Bearer"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"{self.token_type} {self.access_token}",
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
            raise RuntimeError(f"google-sheets HTTP {e.code}: {err}") from e

    def test_connection(self) -> dict[str, Any]:
        if not self.access_token or not self.spreadsheet_id:
            return {"ok": False, "message": "missing access_token or spreadsheet_id", "code": "auth"}
        try:
            url = f"{self.API}/{self.spreadsheet_id}?fields=properties.title"
            meta = self._req("GET", url)
            title = (meta.get("properties") or {}).get("title", "")
            return {"ok": True, "message": f"spreadsheet ok: {title}"}
        except Exception as e:
            return {"ok": False, "message": str(e)[:200], "code": "network"}

    def list_tabs(self) -> List[str]:
        url = f"{self.API}/{self.spreadsheet_id}?fields=sheets.properties.title"
        meta = self._req("GET", url)
        out: List[str] = []
        for s in meta.get("sheets") or []:
            t = (s.get("properties") or {}).get("title")
            if t:
                out.append(t)
        return out

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        data = self.read_rows(tab)
        cur = data["headers"]
        if not cur:
            self.write_rows(tab, headers, [], mode="replace")
            # write header row
            self._update_range(tab, "A1", [headers])
            return {"ok": True, "headers": list(headers)}
        # append missing header columns by rewriting header line
        new_h = list(cur)
        for h in headers:
            if h not in new_h:
                new_h.append(h)
        if new_h != cur:
            self._update_range(tab, "A1", [new_h])
        return {"ok": True, "headers": new_h}

    def read_rows(self, tab: str) -> dict[str, Any]:
        rng = urllib.parse.quote(f"{tab}")
        url = f"{self.API}/{self.spreadsheet_id}/values/{rng}"
        data = self._req("GET", url)
        values = data.get("values") or []
        if not values:
            return {"headers": [], "rows": []}
        headers = [str(x) for x in values[0]]
        rows = [[str(c) for c in r] + [""] * max(0, len(headers) - len(r)) for r in values[1:]]
        for r in rows:
            while len(r) < len(headers):
                r.append("")
        return {"headers": headers, "rows": rows}

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        if mode == "replace":
            # clear sheet then write headers+rows
            self._clear_tab(tab)
            body = [list(headers)] + [list(r) for r in rows]
            self._update_range(tab, "A1", body)
            return {"written": len(rows)}
        # append
        existing = self.read_rows(tab)
        if not existing["headers"]:
            self._update_range(tab, "A1", [list(headers)] + [list(r) for r in rows])
            return {"written": len(rows)}
        # map to existing header order
        idx = {h: i for i, h in enumerate(existing["headers"])}
        mapped = []
        for r in rows:
            row = [""] * len(existing["headers"])
            for i, h in enumerate(headers):
                if h in idx and i < len(r):
                    row[idx[h]] = r[i]
            mapped.append(row)
        start = len(existing["rows"]) + 2  # 1-based + header
        self._update_range(tab, f"A{start}", mapped)
        return {"written": len(mapped)}

    def _update_range(self, tab: str, a1: str, values: List[List[str]]) -> None:
        rng = urllib.parse.quote(f"{tab}!{a1}")
        url = f"{self.API}/{self.spreadsheet_id}/values/{rng}?valueInputOption=RAW"
        self._req("PUT", url, {"values": values})

    def _clear_tab(self, tab: str) -> None:
        url = f"{self.API}/{self.spreadsheet_id}/values/{urllib.parse.quote(tab)}:clear"
        self._req("POST", url, {})
