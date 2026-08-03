"""Row-database backends: Baserow, NocoDB, PocketBase, Supabase, Airtable.

Config via token-file JSON:
  {
    "backend": "baserow",
    "base_url": "https://…",
    "token": "…",
    "base_id": ""  # airtable,
    "tables": { "Vehicles": "tableId", "Expenses": "…", "Fuel - Unassigned": "…" }
  }

Tabs are the keys of tables map. Sync ID field used for upsert on write.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, List, Sequence

from .base import Backend

SYNC_ID = "Sync ID"


def _http(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout: int = 60,
) -> tuple[int, str]:
    data = body.encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None and "Content-Type" not in (headers or {}):
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, text


def _pad(row: Sequence[str], n: int) -> list[str]:
    out = list(row[:n])
    while len(out) < n:
        out.append("")
    return out


class RowDbBackend(Backend):
    """Generic field-map table backend with Sync-ID upsert."""

    backend_id = "rowdb"

    def __init__(
        self,
        backend_id: str,
        base_url: str,
        token: str,
        tables: dict[str, str],
        *,
        base_id: str = "",
        token_file: str | None = None,
    ):
        if token_file:
            cfg = json.loads(open(token_file, encoding="utf-8").read())
            backend_id = cfg.get("backend") or cfg.get("backendType") or backend_id
            base_url = cfg.get("base_url") or cfg.get("baseUrl") or base_url
            token = cfg.get("token") or cfg.get("access_token") or token
            base_id = cfg.get("base_id") or cfg.get("baseId") or base_id
            tables = cfg.get("tables") or tables
        self.backend_id = backend_id
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.base_id = base_id or ""
        self.tables = {str(k): str(v) for k, v in (tables or {}).items()}
        self._driver = _driver_for(backend_id)

    def _table_id(self, tab: str) -> str:
        tid = self.tables.get(tab, "").strip()
        if not tid:
            raise RuntimeError(f"no table id mapped for tab {tab!r}")
        return tid

    def test_connection(self) -> dict[str, Any]:
        if not self.token:
            return {"ok": False, "message": "missing token", "code": "auth"}
        if not self.tables:
            return {"ok": False, "message": "no tables mapped", "code": "config"}
        try:
            tab = next(iter(self.tables))
            self._driver.list_field_maps(self, self._table_id(tab))
            return {"ok": True, "message": f"{self.backend_id} ok"}
        except Exception as e:
            return {"ok": False, "message": str(e)[:200], "code": "network"}

    def list_tabs(self) -> List[str]:
        return sorted(self.tables.keys())

    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        # v1: tables/fields pre-created remotely; probe list only
        self._driver.list_field_maps(self, self._table_id(tab))
        return {"ok": True, "headers": list(headers)}

    def read_rows(self, tab: str) -> dict[str, Any]:
        remote = self._driver.list_field_maps(self, self._table_id(tab))
        if not remote:
            return {"headers": [], "rows": []}
        # union keys preserve order: Sync ID first if present
        keys: list[str] = []
        seen: set[str] = set()
        for _, fields in remote:
            for k in fields:
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        if SYNC_ID in keys:
            keys = [SYNC_ID] + [k for k in keys if k != SYNC_ID]
        rows = [[fields.get(k, "") for k in keys] for _, fields in remote]
        return {"headers": keys, "rows": rows}

    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        table_id = self._table_id(tab)
        remote = self._driver.list_field_maps(self, table_id)
        by_sync = {
            fields.get(SYNC_ID, "").strip(): rid
            for rid, fields in remote
            if fields.get(SYNC_ID, "").strip()
        }
        sync_idx = headers.index(SYNC_ID) if SYNC_ID in headers else -1
        written = 0
        keep_sync: set[str] = set()
        for row in rows:
            row = _pad(row, len(headers))
            sync = row[sync_idx].strip() if sync_idx >= 0 else ""
            if sync:
                keep_sync.add(sync)
            if sync and sync in by_sync:
                self._driver.update_row(self, table_id, by_sync[sync], headers, row)
            else:
                rid = self._driver.create_row(self, table_id, headers, row)
                if sync:
                    by_sync[sync] = rid
            written += 1
        if mode == "replace":
            for rid, fields in remote:
                sid = fields.get(SYNC_ID, "").strip()
                if sid and sid not in keep_sync:
                    self._driver.delete_row(self, table_id, rid)
        return {"written": written, "mode": mode}


class _Driver:
    def list_field_maps(self, be: RowDbBackend, table_id: str) -> list[tuple[str, dict[str, str]]]:
        raise NotImplementedError

    def create_row(
        self, be: RowDbBackend, table_id: str, headers: list[str], row: list[str]
    ) -> str:
        raise NotImplementedError

    def update_row(
        self,
        be: RowDbBackend,
        table_id: str,
        row_id: str,
        headers: list[str],
        row: list[str],
    ) -> None:
        raise NotImplementedError

    def delete_row(self, be: RowDbBackend, table_id: str, row_id: str) -> None:
        raise NotImplementedError


class _Baserow(_Driver):
    def _auth(self, be: RowDbBackend) -> dict[str, str]:
        return {"Authorization": f"Token {be.token}"}

    def _url(self, be: RowDbBackend, table_id: str, row_id: str | None = None) -> str:
        base = f"{be.base_url}/api/database/rows/table/{table_id}/"
        if row_id:
            return f"{base.rstrip('/')}/{row_id}/?user_field_names=true"
        return f"{base}?user_field_names=true"

    def list_field_maps(self, be: RowDbBackend, table_id: str):
        out: list[tuple[str, dict[str, str]]] = []
        page = 1
        while True:
            url = f"{self._url(be, table_id)}&page={page}&size=200"
            code, body = _http("GET", url, self._auth(be))
            if code not in range(200, 300):
                raise RuntimeError(f"Baserow list HTTP {code}: {body[:200]}")
            data = json.loads(body)
            results = data.get("results") or []
            if not results:
                break
            for row in results:
                rid = str(row.get("id", ""))
                if not rid:
                    continue
                fields = {
                    k: "" if v is None else str(v)
                    for k, v in row.items()
                    if k not in ("id", "order")
                }
                out.append((rid, fields))
            if not data.get("next"):
                break
            page += 1
        return out

    def create_row(self, be, table_id, headers, row):
        body = json.dumps({h: row[i] if i < len(row) else "" for i, h in enumerate(headers)})
        code, text = _http("POST", self._url(be, table_id), self._auth(be), body)
        if code not in range(200, 300):
            raise RuntimeError(f"Baserow create HTTP {code}: {text[:200]}")
        return str(json.loads(text).get("id", ""))

    def update_row(self, be, table_id, row_id, headers, row):
        body = json.dumps({h: row[i] if i < len(row) else "" for i, h in enumerate(headers)})
        code, text = _http("PATCH", self._url(be, table_id, row_id), self._auth(be), body)
        if code not in range(200, 300):
            raise RuntimeError(f"Baserow update HTTP {code}: {text[:200]}")

    def delete_row(self, be, table_id, row_id):
        code, text = _http("DELETE", self._url(be, table_id, row_id), self._auth(be))
        if code not in range(200, 300) and code != 204:
            raise RuntimeError(f"Baserow delete HTTP {code}: {text[:200]}")


class _NocoDB(_Driver):
    def _auth(self, be: RowDbBackend) -> dict[str, str]:
        return {"xc-token": be.token}

    def _url(self, be: RowDbBackend, table_id: str) -> str:
        return f"{be.base_url}/api/v2/tables/{table_id}/records"

    def list_field_maps(self, be, table_id):
        out: list[tuple[str, dict[str, str]]] = []
        offset = 0
        limit = 200
        while True:
            url = f"{self._url(be, table_id)}?offset={offset}&limit={limit}"
            code, body = _http("GET", url, self._auth(be))
            if code not in range(200, 300):
                raise RuntimeError(f"NocoDB list HTTP {code}: {body[:200]}")
            data = json.loads(body)
            results = data.get("list") or []
            if not results:
                break
            for row in results:
                rid = str(row.get("Id") or row.get("id") or "")
                if not rid:
                    continue
                fields = {
                    k: "" if v is None else str(v)
                    for k, v in row.items()
                    if k.lower() != "id"
                }
                out.append((rid, fields))
            page = data.get("pageInfo") or {}
            if page.get("isLastPage", True):
                break
            offset += limit
        return out

    def create_row(self, be, table_id, headers, row):
        body = json.dumps({h: row[i] if i < len(row) else "" for i, h in enumerate(headers)})
        code, text = _http("POST", self._url(be, table_id), self._auth(be), body)
        if code not in range(200, 300):
            raise RuntimeError(f"NocoDB create HTTP {code}: {text[:200]}")
        data = json.loads(text)
        return str(data.get("Id") or data.get("id") or "")

    def update_row(self, be, table_id, row_id, headers, row):
        payload = {"Id": int(row_id) if str(row_id).isdigit() else row_id}
        for i, h in enumerate(headers):
            payload[h] = row[i] if i < len(row) else ""
        code, text = _http("PATCH", self._url(be, table_id), self._auth(be), json.dumps(payload))
        if code not in range(200, 300):
            raise RuntimeError(f"NocoDB update HTTP {code}: {text[:200]}")

    def delete_row(self, be, table_id, row_id):
        id_value = int(row_id) if str(row_id).isdigit() else row_id
        body = json.dumps([{"Id": id_value}])
        code, text = _http("DELETE", self._url(be, table_id), self._auth(be), body)
        if code not in range(200, 300) and code != 204:
            raise RuntimeError(f"NocoDB delete HTTP {code}: {text[:200]}")


class _PocketBase(_Driver):
    def _auth(self, be: RowDbBackend) -> dict[str, str]:
        return {"Authorization": f"Bearer {be.token}"}

    def _url(self, be: RowDbBackend, table_id: str, row_id: str | None = None) -> str:
        base = f"{be.base_url}/api/collections/{table_id}/records"
        return f"{base}/{row_id}" if row_id else base

    def list_field_maps(self, be, table_id):
        out: list[tuple[str, dict[str, str]]] = []
        page = 1
        while True:
            url = f"{self._url(be, table_id)}?page={page}&perPage=200"
            code, body = _http("GET", url, self._auth(be))
            if code not in range(200, 300):
                raise RuntimeError(f"PocketBase list HTTP {code}: {body[:200]}")
            data = json.loads(body)
            items = data.get("items") or []
            if not items:
                break
            skip = {"id", "collectionId", "collectionName", "created", "updated"}
            for row in items:
                rid = str(row.get("id", ""))
                if not rid:
                    continue
                fields = {
                    k: "" if v is None else str(v) for k, v in row.items() if k not in skip
                }
                out.append((rid, fields))
            if page >= int(data.get("totalPages") or 1):
                break
            page += 1
        return out

    def create_row(self, be, table_id, headers, row):
        body = json.dumps({h: row[i] if i < len(row) else "" for i, h in enumerate(headers)})
        code, text = _http("POST", self._url(be, table_id), self._auth(be), body)
        if code not in range(200, 300):
            raise RuntimeError(f"PocketBase create HTTP {code}: {text[:200]}")
        return str(json.loads(text).get("id", ""))

    def update_row(self, be, table_id, row_id, headers, row):
        body = json.dumps({h: row[i] if i < len(row) else "" for i, h in enumerate(headers)})
        code, text = _http("PATCH", self._url(be, table_id, row_id), self._auth(be), body)
        if code not in range(200, 300):
            raise RuntimeError(f"PocketBase update HTTP {code}: {text[:200]}")

    def delete_row(self, be, table_id, row_id):
        code, text = _http("DELETE", self._url(be, table_id, row_id), self._auth(be))
        if code not in range(200, 300) and code != 204:
            raise RuntimeError(f"PocketBase delete HTTP {code}: {text[:200]}")


class _Supabase(_Driver):
    def _auth(self, be: RowDbBackend) -> dict[str, str]:
        return {
            "apikey": be.token,
            "Authorization": f"Bearer {be.token}",
            "Prefer": "return=representation",
        }

    def _url(self, be: RowDbBackend, table_id: str, query: str = "") -> str:
        base = f"{be.base_url}/rest/v1/{table_id}"
        return f"{base}?{query}" if query else base

    def list_field_maps(self, be, table_id):
        code, body = _http("GET", self._url(be, table_id, "select=*"), self._auth(be))
        if code not in range(200, 300):
            raise RuntimeError(f"Supabase list HTTP {code}: {body[:200]}")
        arr = json.loads(body)
        out: list[tuple[str, dict[str, str]]] = []
        for row in arr:
            rid = str(row.get("id", ""))
            if not rid:
                continue
            fields = {k: "" if v is None else str(v) for k, v in row.items() if k != "id"}
            out.append((rid, fields))
        return out

    def create_row(self, be, table_id, headers, row):
        body = json.dumps({h: row[i] if i < len(row) else "" for i, h in enumerate(headers)})
        code, text = _http("POST", self._url(be, table_id), self._auth(be), body)
        if code not in range(200, 300):
            raise RuntimeError(f"Supabase create HTTP {code}: {text[:200]}")
        data = json.loads(text)
        if isinstance(data, list) and data:
            return str(data[0].get("id", ""))
        if isinstance(data, dict):
            return str(data.get("id", ""))
        return ""

    def update_row(self, be, table_id, row_id, headers, row):
        body = json.dumps({h: row[i] if i < len(row) else "" for i, h in enumerate(headers)})
        code, text = _http(
            "PATCH",
            self._url(be, table_id, f"id=eq.{urllib.parse.quote(str(row_id))}"),
            self._auth(be),
            body,
        )
        if code not in range(200, 300):
            raise RuntimeError(f"Supabase update HTTP {code}: {text[:200]}")

    def delete_row(self, be, table_id, row_id):
        code, text = _http(
            "DELETE",
            self._url(be, table_id, f"id=eq.{urllib.parse.quote(str(row_id))}"),
            self._auth(be),
        )
        if code not in range(200, 300) and code != 204:
            raise RuntimeError(f"Supabase delete HTTP {code}: {text[:200]}")


class _Airtable(_Driver):
    def _auth(self, be: RowDbBackend) -> dict[str, str]:
        return {"Authorization": f"Bearer {be.token}"}

    def _url(self, be: RowDbBackend, table_id: str, row_id: str | None = None) -> str:
        base = f"https://api.airtable.com/v0/{be.base_id}/{urllib.parse.quote(table_id, safe='')}"
        return f"{base}/{row_id}" if row_id else base

    def list_field_maps(self, be, table_id):
        out: list[tuple[str, dict[str, str]]] = []
        offset = None
        while True:
            url = self._url(be, table_id)
            if offset:
                url += f"?offset={urllib.parse.quote(offset)}"
            code, body = _http("GET", url, self._auth(be))
            if code not in range(200, 300):
                raise RuntimeError(f"Airtable list HTTP {code}: {body[:200]}")
            data = json.loads(body)
            for rec in data.get("records") or []:
                rid = rec.get("id", "")
                fields_raw = rec.get("fields") or {}
                fields = {k: "" if v is None else str(v) for k, v in fields_raw.items()}
                out.append((rid, fields))
            offset = data.get("offset")
            if not offset:
                break
        return out

    def create_row(self, be, table_id, headers, row):
        fields = {h: row[i] if i < len(row) else "" for i, h in enumerate(headers)}
        body = json.dumps({"fields": fields})
        code, text = _http("POST", self._url(be, table_id), self._auth(be), body)
        if code not in range(200, 300):
            raise RuntimeError(f"Airtable create HTTP {code}: {text[:200]}")
        return str(json.loads(text).get("id", ""))

    def update_row(self, be, table_id, row_id, headers, row):
        fields = {h: row[i] if i < len(row) else "" for i, h in enumerate(headers)}
        body = json.dumps({"fields": fields})
        code, text = _http("PATCH", self._url(be, table_id, row_id), self._auth(be), body)
        if code not in range(200, 300):
            raise RuntimeError(f"Airtable update HTTP {code}: {text[:200]}")

    def delete_row(self, be, table_id, row_id):
        code, text = _http("DELETE", self._url(be, table_id, row_id), self._auth(be))
        if code not in range(200, 300) and code != 204:
            raise RuntimeError(f"Airtable delete HTTP {code}: {text[:200]}")


_DRIVERS: dict[str, Callable[[], _Driver]] = {
    "baserow": _Baserow,
    "nocodb": _NocoDB,
    "pocketbase": _PocketBase,
    "supabase": _Supabase,
    "airtable": _Airtable,
}


def _driver_for(backend_id: str) -> _Driver:
    key = backend_id.lower().replace("_", "")
    # normalize
    aliases = {
        "baserow": "baserow",
        "nocodb": "nocodb",
        "pocketbase": "pocketbase",
        "supabase": "supabase",
        "airtable": "airtable",
    }
    norm = aliases.get(key) or aliases.get(backend_id.lower())
    if not norm or norm not in _DRIVERS:
        raise ValueError(f"unknown rowdb backend: {backend_id}")
    return _DRIVERS[norm]()
