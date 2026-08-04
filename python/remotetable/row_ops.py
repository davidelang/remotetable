"""L1/L2 named-column helpers + soft-delete propagate (CONTRACT.md)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from .cell_types import coerce_row

DEFAULT_TRUE_VALUES = ("true", "1", "yes", "TRUE", "True")


def header_index(headers: Sequence[str]) -> Dict[str, int]:
    return {h: i for i, h in enumerate(headers)}


def cell(row: Sequence[str], idx: Mapping[str, int], name: str) -> str:
    i = idx.get(name)
    if i is None or i >= len(row):
        return ""
    return str(row[i])


def matches_filter(row: Sequence[str], idx: Mapping[str, int], filt: Mapping[str, str]) -> bool:
    if not filt:
        return False
    for k, v in filt.items():
        if cell(row, idx, k) != v:
            return False
    return True


def apply_set(
    row: Sequence[str], headers: Sequence[str], set_fields: Mapping[str, str]
) -> List[str]:
    out = list(row)
    while len(out) < len(headers):
        out.append("")
    idx = header_index(headers)
    for name, value in set_fields.items():
        i = idx.get(name)
        if i is not None:
            out[i] = value
    return out


def is_truthy_tombstone(value: str, true_values: Sequence[str] = DEFAULT_TRUE_VALUES) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    lower = v.lower()
    return any(t.lower() == lower or t == v for t in true_values)


def propagate_soft_deletes(
    source: Mapping[str, Any],
    dest: Mapping[str, Any],
    keys: Sequence[str],
    tombstone_column: str,
    true_values: Sequence[str] = DEFAULT_TRUE_VALUES,
    column_map: Mapping[str, str] | None = None,
) -> Tuple[Dict[str, Any], int]:
    column_map = column_map or {}
    src_h = list(source.get("headers") or [])
    src_rows = [list(r) for r in (source.get("rows") or [])]
    dest_h = list(dest.get("headers") or [])
    dest_rows = [list(r) for r in (dest.get("rows") or [])]
    if not src_h or not keys:
        return {"headers": dest_h, "rows": dest_rows}, 0

    def map_name(src: str) -> str:
        return column_map.get(src, src)

    src_idx = header_index(src_h)
    dest_keys = [map_name(k) for k in keys]
    dest_tomb = map_name(tombstone_column)
    dest_idx = header_index(dest_h)
    if any(k not in dest_idx for k in dest_keys) or dest_tomb not in dest_idx:
        return {"headers": dest_h, "rows": dest_rows}, 0

    by_key: Dict[str, int] = {}
    for i, row in enumerate(dest_rows):
        key = "\x01".join(cell(row, dest_idx, k) for k in dest_keys)
        if key and key not in by_key:
            by_key[key] = i

    updated = 0
    for srow in src_rows:
        if not is_truthy_tombstone(cell(srow, src_idx, tombstone_column), true_values):
            continue
        key = "\x01".join(cell(srow, src_idx, k) for k in keys)
        if not key or key not in by_key:
            continue  # no dest match → no-op
        di = by_key[key]
        ti = dest_idx[dest_tomb]
        while len(dest_rows[di]) < len(dest_h):
            dest_rows[di].append("")
        if not is_truthy_tombstone(dest_rows[di][ti], true_values):
            dest_rows[di][ti] = "true"
            updated += 1
    return {"headers": dest_h, "rows": dest_rows}, updated


def map_row(
    source_headers: Sequence[str],
    source_row: Sequence[str],
    dest_headers: Sequence[str],
    column_map: Mapping[str, str],
) -> List[str]:
    src_idx = header_index(source_headers)
    dest_idx = header_index(dest_headers)
    out = [""] * len(dest_headers)
    if not column_map:
        for h in source_headers:
            j = dest_idx.get(h)
            if j is not None:
                out[j] = cell(source_row, src_idx, h)
        return out
    for src_name, dest_name in column_map.items():
        j = dest_idx.get(dest_name)
        if j is not None:
            out[j] = cell(source_row, src_idx, src_name)
    return out


def push_table(
    source_backend: Any,
    dest_backend: Any,
    unit: Mapping[str, Any],
) -> Dict[str, int]:
    """Directional push MVP for mock backends (Python harness)."""
    src_tab = (unit.get("source") or {}).get("table") or (unit.get("source") or {}).get("tab")
    dest_tab = (unit.get("dest") or {}).get("table") or (unit.get("dest") or {}).get("tab")
    keys = list(unit.get("keys") or [])
    column_map = dict(unit.get("column_map") or {})
    columns = unit.get("columns") or []
    tomb = unit.get("tombstone") or {}
    timestamp = unit.get("timestamp")

    src = source_backend.read_rows(src_tab)
    dest_headers = [c["name"] if isinstance(c, dict) else str(c) for c in columns]
    if not dest_headers:
        dest_headers = [column_map.get(h, h) for h in src["headers"]]
    dest_backend.ensure_headers(dest_tab, dest_headers)
    dest = dest_backend.read_rows(dest_tab)

    soft_deleted = 0
    if tomb.get("column"):
        true_values = [str(x) for x in (tomb.get("true_values") or DEFAULT_TRUE_VALUES)]
        dest, soft_deleted = propagate_soft_deletes(
            src,
            dest,
            keys,
            tomb["column"],
            true_values=true_values,
            column_map=column_map,
        )
        if soft_deleted:
            dest_backend.write_rows(dest_tab, dest["headers"], dest["rows"], mode="replace")
            dest = dest_backend.read_rows(dest_tab)

    dest_idx = header_index(dest["headers"])
    src_idx = header_index(src["headers"])
    d_keys = [column_map.get(k, k) for k in keys]
    by_key: Dict[str, int] = {}
    rows = [list(r) for r in dest["rows"]]
    for i, row in enumerate(rows):
        key = "\x01".join(cell(row, dest_idx, k) for k in d_keys)
        if key and key not in by_key:
            by_key[key] = i

    written = 0
    skipped_older = 0
    headers = dest["headers"] or dest_headers

    def parse_ts(raw: str) -> int:
        t = (raw or "").strip()
        if not t:
            return 0
        if t.isdigit():
            return int(t)
        digits = "".join(c for c in t if c.isdigit())[:13]
        return int(digits) if digits else 0

    for srow in src["rows"]:
        sk = "\x01".join(cell(srow, src_idx, k) for k in keys)
        if not sk:
            continue
        if tomb.get("column") and is_truthy_tombstone(
            cell(srow, src_idx, tomb["column"]),
            [str(x) for x in (tomb.get("true_values") or DEFAULT_TRUE_VALUES)],
        ):
            if sk not in by_key:
                continue
        mapped = coerce_row(
            headers,
            map_row(src["headers"], srow, headers, column_map),
            columns if isinstance(columns, list) else [],
        )
        di = by_key.get(sk)
        if di is None:
            rows.append(mapped)
            by_key[sk] = len(rows) - 1
            written += 1
        else:
            if timestamp:
                ts_dest = column_map.get(timestamp, timestamp)
                s_ts = parse_ts(cell(srow, src_idx, timestamp))
                d_ts = parse_ts(cell(rows[di], dest_idx, ts_dest))
                if s_ts < d_ts:
                    skipped_older += 1
                    continue
            while len(rows[di]) < len(headers):
                rows[di].append("")
            for i, v in enumerate(mapped):
                if i < len(rows[di]) and v:
                    rows[di][i] = v
            written += 1

    dest_backend.write_rows(dest_tab, headers, rows, mode="replace")
    return {"written": written, "soft_deleted": soft_deleted, "skipped_older": skipped_older}


def parse_ts(raw: str) -> int:
    t = (raw or "").strip()
    if not t:
        return 0
    if t.isdigit():
        return int(t)
    digits = "".join(c for c in t if c.isdigit())[:13]
    return int(digits) if digits else 0


def _compare_ts(row_a: Sequence[str], row_b: Sequence[str], logical: Sequence[str], timestamp: str | None) -> int:
    """>0 a newer, <0 b newer, 0 equal (prefer a)."""
    if not timestamp:
        return 0
    idx = header_index(logical)
    ta = parse_ts(cell(row_a, idx, timestamp))
    tb = parse_ts(cell(row_b, idx, timestamp))
    if ta == 0 and tb == 0:
        return 0
    if ta == 0:
        return -1
    if tb == 0:
        return 1
    if ta > tb:
        return 1
    if ta < tb:
        return -1
    return 0


def _index_logical(
    data: Mapping[str, Any],
    logical: Sequence[str],
    column_map: Mapping[str, str],
    columns: Sequence,
    keys: Sequence[str],
) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    headers = list(data.get("headers") or [])
    idx = header_index(logical)
    for row in data.get("rows") or []:
        mapped = coerce_row(
            logical,
            map_row(headers, row, logical, column_map or {}),
            list(columns) if columns else [],
        )
        key = "\x01".join(cell(mapped, idx, k) for k in keys)
        if not key or key in out:
            continue
        out[key] = mapped
    return out


def _pick_full(
    row_a: List[str] | None,
    row_b: List[str] | None,
    logical: Sequence[str],
    timestamp: str | None,
) -> List[str]:
    if row_a is None and row_b is None:
        return [""] * len(logical)
    if row_a is None:
        return list(row_b or [])
    if row_b is None:
        return list(row_a)
    return list(row_a if _compare_ts(row_a, row_b, logical, timestamp) >= 0 else row_b)


def _field_fill(
    row_a: List[str] | None,
    row_b: List[str] | None,
    logical: Sequence[str],
    timestamp: str | None,
) -> List[str]:
    if row_a is None and row_b is None:
        return [""] * len(logical)
    if row_a is None:
        return list(row_b or [])
    if row_b is None:
        return list(row_a)
    winner_a = _compare_ts(row_a, row_b, logical, timestamp) >= 0
    winner = list(row_a if winner_a else row_b)
    loser = list(row_b if winner_a else row_a)
    while len(winner) < len(logical):
        winner.append("")
    for i in range(len(logical)):
        w = winner[i] if i < len(winner) else ""
        l = loser[i] if i < len(loser) else ""
        if not str(w).strip() and str(l).strip():
            winner[i] = l
    return winner


def merge_tab_data(
    a: Mapping[str, Any],
    b: Mapping[str, Any],
    unit: Mapping[str, Any],
) -> Dict[str, Any]:
    """Pure A↔B merge: union | lww_row | field_fill (CONTRACT)."""
    keys = list(unit.get("keys") or [])
    if not keys:
        raise ValueError("keys required")
    columns = unit.get("columns") or []
    logical = [c["name"] if isinstance(c, dict) else str(c) for c in columns]
    map_a = dict(unit.get("column_map_a") or unit.get("column_map") or {})
    map_b = dict(unit.get("column_map_b") or {})
    if not logical:
        ha = [map_a.get(h, h) for h in (a.get("headers") or [])]
        hb = [map_b.get(h, h) for h in (b.get("headers") or [])]
        logical = list(dict.fromkeys(ha + hb))
    timestamp = unit.get("timestamp")
    mode = (unit.get("merge_mode") or "lww_row").strip().lower().replace("-", "_")
    if mode in ("lww",):
        mode = "lww_row"
    if mode in ("fill",):
        mode = "field_fill"

    idx_a = _index_logical(a, logical, map_a, columns, keys)
    idx_b = _index_logical(b, logical, map_b, columns, keys)
    all_keys = list(dict.fromkeys(list(idx_a.keys()) + list(idx_b.keys())))
    rows: List[List[str]] = []
    for key in all_keys:
        ra, rb = idx_a.get(key), idx_b.get(key)
        if mode == "field_fill":
            merged = _field_fill(ra, rb, logical, timestamp)
        else:
            # union and lww_row: full-row pick
            merged = _pick_full(ra, rb, logical, timestamp)
        rows.append(coerce_row(logical, merged, columns if isinstance(columns, list) else []))
    return {"headers": list(logical), "rows": rows}


def merge_tables(
    backend_a: Any,
    backend_b: Any,
    unit: Mapping[str, Any],
) -> Dict[str, Any]:
    """Read a/b, merge, optional write_target a|b|none."""
    tab_a = (unit.get("a") or {}).get("table") or (unit.get("a") or {}).get("tab")
    tab_b = (unit.get("b") or {}).get("table") or (unit.get("b") or {}).get("tab")
    if not tab_a or not tab_b:
        # legacy
        tab_a = tab_a or (unit.get("source") or {}).get("table")
        tab_b = tab_b or (unit.get("dest") or {}).get("table")
    data_a = backend_a.read_rows(tab_a)
    data_b = backend_b.read_rows(tab_b)
    merged = merge_tab_data(data_a, data_b, unit)
    write_target = (unit.get("write_target") or "none").strip().lower()
    written = False
    if write_target == "a":
        backend_a.ensure_headers(tab_a, merged["headers"])
        backend_a.write_rows(tab_a, merged["headers"], merged["rows"], mode="replace")
        written = True
    elif write_target == "b":
        backend_b.ensure_headers(tab_b, merged["headers"])
        backend_b.write_rows(tab_b, merged["headers"], merged["rows"], mode="replace")
        written = True
    return {
        "id": unit.get("id", "merge"),
        "mode": unit.get("merge_mode", "lww_row"),
        "row_count": len(merged["rows"]),
        "written": written,
        "merged": merged,
    }
