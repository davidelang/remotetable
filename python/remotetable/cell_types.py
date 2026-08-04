"""Spreadsheet-ish type coerce (CONTRACT schema_version 1)."""

from __future__ import annotations

import re
from typing import List, Mapping, Optional, Sequence


def coerce(value: str, type_name: Optional[str]) -> str:
    t = (type_name or "").strip().lower()
    raw = value if value is not None else ""
    if t in ("", "string"):
        return raw
    if t == "number":
        return coerce_number(raw)
    if t == "timestamp":
        return coerce_timestamp(raw)
    if t == "checkbox":
        return coerce_checkbox(raw)
    return raw


def coerce_number(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    cleaned = re.sub(r"[^\d.\-eE+]", "", s)
    if not cleaned:
        return s
    try:
        f = float(cleaned)
        if f == int(f) and abs(f) < 1e15:
            return str(int(f))
        return str(f)
    except ValueError:
        return s


def coerce_timestamp(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if s.isdigit():
        return s
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) >= 13:
        return digits[:13]
    if len(digits) >= 10:
        return str(int(digits[:10]) * 1000)
    return s


def coerce_checkbox(raw: str) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "false"
    if s in ("true", "1", "yes", "y", "on", "checked"):
        return "true"
    if s in ("false", "0", "no", "n", "off", "unchecked"):
        return "false"
    return "true" if s in ("true", "1", "yes") else "false"


def coerce_row(
    headers: Sequence[str],
    row: Sequence[str],
    columns: Sequence[Mapping],
) -> List[str]:
    type_by = {}
    for c in columns or []:
        if isinstance(c, dict):
            type_by[c.get("name", "")] = c.get("type", "string")
    out = []
    for i, h in enumerate(headers):
        v = row[i] if i < len(row) else ""
        out.append(coerce(str(v), type_by.get(h)))
    return out
