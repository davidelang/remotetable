"""ethercalc backend — socialcalc CSV over HTTP."""

from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.request
from typing import Any, List

from .base import Backend


class EtherCalcBackend(Backend):
    """
    Token file JSON optional:
      { "base_url": "https://ethercalc.example", "room": "mysheet", "auth": "optional" }
    Or pass base_url/room in constructor.
    """

    backend_id = "ethercalc"

    def __init__(
        self,
        base_url: str | None = None,
        room: str | None = None,
        token_file: str | None = None,
    ):
        cfg: dict[str, Any] = {}
        if token_file:
            cfg = json.loads(open(token_file, encoding="utf-8").read())
        self.base_url = (base_url or cfg.get("base_url") or "").rstrip("/")
        self.room = room or cfg.get("room") or "sheet"
        self.auth = cfg.get("auth") or cfg.get("access_token") or ""

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "text/csv"}
        if self.auth:
            h["Authorization"] = f"Bearer {self.auth}"
        return h

    def _url(self, path: str = "") -> str:
        return f"{self.base_url}/{self.room}{path}"

    def _get(self, path: str = ".csv") -> str:
        req = urllib.request.Request(self._url(path), headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _put_csv(self, text: str) -> None:
        # EtherCalc: POST /_/{room} with CSV body appends; PUT replaces in some deployments
        data = text.encode("utf-8")
        req = urllib.request.Request(
            self._url(),
            data=data,
            headers=self._headers(),
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
        except urllib.error.HTTPError:
            # fallback append POST
            req2 = urllib.request.Request(
                f"{self.base_url}/_/{self.room}",
                data=data,
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=60) as resp:
                resp.read()

    def test_connection(self) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "message": "missing base_url", "code": "auth"}
        try:
            self._get(".csv")
            return {"ok": True, "message": f"ethercalc room={self.room}"}
        except Exception as e:
            return {"ok": False, "message": str(e)[:200], "code": "network"}

    def list_tabs(self) -> List[str]:
        # One room ≈ one tab
        return [self.room]

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        data = self.read_rows(tab)
        if not data["headers"]:
            self.write_rows(tab, headers, [], mode="replace")
            return {"ok": True, "headers": list(headers)}
        new_h = list(data["headers"])
        for h in headers:
            if h not in new_h:
                new_h.append(h)
        if new_h != data["headers"]:
            self.write_rows(tab, new_h, data["rows"], mode="replace")
        return {"ok": True, "headers": new_h}

    def read_rows(self, tab: str) -> dict[str, Any]:
        text = self._get(".csv")
        reader = csv.reader(io.StringIO(text))
        rows = [list(r) for r in reader]
        # EtherCalc sometimes prefixes a blank/comma-only line before headers.
        while rows and all(not str(c).strip() for c in rows[0]):
            rows = rows[1:]
        if not rows:
            return {"headers": [], "rows": []}
        headers = [str(c) for c in rows[0]]
        body = []
        for r in rows[1:]:
            row = [str(c) for c in r]
            while len(row) < len(headers):
                row.append("")
            body.append(row)
        return {"headers": headers, "rows": body}

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        if mode == "replace":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(headers)
            for r in rows:
                w.writerow(r)
            self._put_csv(buf.getvalue())
            return {"written": len(rows)}
        existing = self.read_rows(tab)
        all_rows = existing["rows"] + [list(r) for r in rows]
        hdr = existing["headers"] or list(headers)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(hdr)
        for r in all_rows:
            w.writerow(r)
        self._put_csv(buf.getvalue())
        return {"written": len(rows)}
