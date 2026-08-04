# remotetable contract (schema_version 1)

**Status:** Normative for library implementers and multi-consumer apps (VE, CLI, others).  
**Version:** `schema_version: 1`  
**Date:** 2026-08-04

This document is the shared product contract. Implementation languages (Kotlin AAR, Python, Go) must honor the same semantics. VE domain rules (fuel field-merge, trip types, product meaning of “Sync ID”) stay **out** of this library.

---

## Layers (normative)

| Layer | Name | Responsibility |
|-------|------|----------------|
| **L0** | Transport | Per-backend HTTP/SQL/file I/O; **baked-in rate limit** (config expected rates + 429/retry); efficient provider ops |
| **L1** | Grid / table | Tabs ≈ tables; headers; rows as **named** columns; create-time **column order**; types coerce |
| **L2** | Row ops | Filter (AND equality) → set fields; soft-delete flag; **expunge**; **readMany / writeMany** |
| **L3** | Policy / sync | Directional push/pull; keys + timestamp; column_map; **A↔B merge** (`union` / `lww_row` / `field_fill`) |
| **L4** | App / CLI | Which endpoints, product-only steps, UI, scheduling |

Field **meaning** stays out of the library; **mechanics** (key column names, timestamp column, tombstone column names) are config.

---

## Column maps

| Concept | Role |
|---------|------|
| **`columns`** (ordered) | Canonical **logical** fields for this table sync unit: `name` + optional `type`. **Order matters when the destination has no headers yet** (create / ensure schema). |
| **`column_map`** | Object: **source name → destination name**. If omitted or identity, names match 1:1. Library **must not** assume the two ends share column **order** or identical spellings. |
| **Physical layout** | On read/write, resolve by **name** via map; never by index alone. |

Direction convention: for a given table unit, map is always **source → dest** for the configured `direction` (`push` = source→dest; `pull` = reverse endpoints or invert map — one convention per config, not both).

---

## Soft delete vs expunge

### Soft delete (default: flag only — do not clear other fields)

- If **source** row is tombstoned (tombstone column matches configured true values) **and** **destination** has a row with **matching keys** → set destination tombstone (propagate soft delete). Other dest fields unchanged unless config later adds redaction.
- If dest has **no** matching key → **no change** on dest (do not create a row solely to tombstone).
- Keys: default **union of configured key columns**; may be restricted via config.

This allows: soft-delete → propagate to many stores → **expunge each store independently later**.

### Expunge (explicit, never implied by normal sync)

- Product meaning: key should be **absent** after expunge.
- Provider mechanics may differ (Sheets row delete vs SQL DELETE); semantic is shared.
- Soft-delete data retained until expunge so later matching/audit still works.

---

## Rate limits

- **Baked into library** for every backend that can fail under load.
- **Defaults** per backend (Sheets: proactive pace aligned with ~60/min read and write caps; default **~1.3s gap / ~45/min** unless config overrides).
- **JSON `rate_limits`** (optional): expected read/write per minute, `min_gap_ms` — **pace before hit**, not only after 429.
- Always **detect rate-limit errors + backoff + retry same logical call**; optional progress callback for apps/CLI.

Sheets defaults (schema_version 1):

| Key | Default |
|-----|---------|
| `read_per_minute` | 45 |
| `write_per_minute` | 45 |
| `min_gap_ms` | 1300 |
| max attempts per logical call | 8 |
| backoff after 429 | first 60–120s, then 90–180s (cap 180s) |

---

## Types (spreadsheet-ish)

Wire/logical types: `string` | `number` | `timestamp` | `checkbox` (boolean).

- Coerce on boundaries.
- Timestamp wire form: prefer **epoch millis** in JSON config values; ISO-8601 accepted on read where practical.

---

## Filter language (v1)

AND of field **equalities** only. `IN` / `is_empty` later.

---

## Batch APIs (first-class)

**`readMany`** / **`writeMany`** (and batch point updates) are **required** for performance and rate-limit hygiene—not optional polish.

| Op | Intent |
|----|--------|
| `readMany(tabs[])` | Bulk read multiple tables; Sheets uses `values.batchGet` (chunked) |
| `writeMany` | Multi-tab replace/append without one full rewrite loop per unrelated row |
| `updateRange` / point update | Contiguous range write without full-tab replace |
| `updateWhere(filter, set)` | AND-equality filter → set named fields |
| `softDeleteWhere` | Flag-only tombstone on matching rows |
| `expungeWhere` | Remove rows so keys are absent |

---

## JSON config sketch (`schema_version` 1)

```json
{
  "schema_version": 1,
  "rate_limits": {
    "google-sheets": {
      "read_per_minute": 45,
      "write_per_minute": 45,
      "min_gap_ms": 1300
    }
  },
  "tables": [
    {
      "id": "example-fuel",
      "direction": "push",
      "source": { "backend": "mock", "table": "FuelLocal" },
      "dest": { "backend": "google-sheets", "spreadsheet_id": "…", "tab": "Fuel - Car" },
      "columns": [
        { "name": "Sync ID", "type": "string" },
        { "name": "Updated At", "type": "timestamp" },
        { "name": "Deleted", "type": "checkbox" }
      ],
      "column_map": {
        "syncId": "Sync ID",
        "updatedAt": "Updated At",
        "deleted": "Deleted"
      },
      "keys": ["Sync ID"],
      "timestamp": "Updated At",
      "tombstone": {
        "column": "Deleted",
        "true_values": [true, "true", "1", "yes"]
      }
    }
  ]
}
```

**Soft-delete push rule:** source tombstoned + dest has key match → dest tombstone; no dest row → no-op.

**Directional push (L3 MVP):** for each source row, map columns; match dest by keys; if no dest row → append; if dest exists and source timestamp does not lose to dest → write mapped fields (do not clobber newer dest); soft-delete rule as above.

---

## Explicit non-goals (this contract layer)

- Room / internal DB backend as L0 endpoint (later)
- VE fuel domain field-merge or trip-type product rules (app L4)
- Field-level timestamps (row ts only for fill conflicts)
- Automatic expunge during merge
- Device green (e.g. emulator multi-tab 429 recovery) as definition of L0/L1 success — that is a later integrate gate

---

## Materialize / promote (coders)

From a VehicleExpenses worktree:

```bash
./third_party/fetch-deps rw remotetable   # sources at third_party/remotetable/src/
# edit under src/; commit in that git
./third_party/fetch-deps build remotetable
# promote: bump third_party/remotetable/libpin.toml git_sha + artifact/remotetable.aar
```

See repo `README.md`, consumer `SOURCE.md`, and VE `docs/reference/THIRD_PARTY_PIN_BUILDS.md`.

---

## Related docs

| Doc | Role |
|-----|------|
| `spec/OPS.md` | M1 connection/tab/row ops |
| `spec/OVERVIEW.md` | Milestone overview |
| `conformance/README.md` | Harness + live smoke |
| This file | Layers, policy, rate limits, batch, soft-delete/expunge |

---

## Types coerce (boundaries)

On PolicySync push (and any documented map/write boundary), cell values are coerced using `columns[].type`:

| type | Wire cell form |
|------|----------------|
| `string` | as-is (default / unknown type) |
| `number` | strip currency/junk; numeric string |
| `timestamp` | prefer epoch millis digits; ISO digits best-effort |
| `checkbox` | canonical `true` / `false` |

---

## Rate limits (all HTTP backends)

Every Kotlin HTTP backend that performs network I/O uses a non-null `RateLimiter` (defaults in `RateLimitRegistry` for `google-sheets`, `excel-graph`, `ethercalc`, `zoho-sheet`, and all row-db ids). **`min_gap_ms` is the primary throttle**; read/write per-minute fields document expectations (independent dual buckets not required in foundation).

---



---

## L3 A↔B merge (`direction: "merge"`)

Config names two endpoints **`a`** and **`b`** (not source/dest only). Result schema is ordered **`columns`** (logical names). Optional `column_map_a` / `column_map_b` map each side’s physical names → logical (`source → logical`). Empty map = identity.

| `merge_mode` | Behavior |
|--------------|----------|
| **`union`** | Result keys = A ∪ B. For each key, pick **one full row** (no field-level mix). Winner by timestamp if configured; **equal ts or missing ts → prefer a**. |
| **`lww_row`** | Per key: full row from side with **newer** row timestamp; missing ts → other side wins if it has a row; equal ts → **prefer a**. |
| **`field_fill`** | Start from `lww_row` winner; for each field, if winner cell empty and loser non-empty → take loser; if both non-empty → keep winner (row-ts side). |

### Soft-delete + LWW

- Tombstone is **flag only** (no expunge).
- If the **winning** row (by ts / tie-break) is tombstoned → result row is tombstoned.
- **Newer tombstone wins over older live** (do not resurrect older live over newer tombstone).
- Merge never creates expunge; never invents a tombstone-only row for a key that exists only as soft-delete on one side without including that key in the union (union **does** include keys present only on one side, including tombstoned-only keys).

### `write_target`

| Value | Effect |
|-------|--------|
| `"a"` | Write merged grid to endpoint **a**’s table (replace) |
| `"b"` | Write to **b** (CLI default when writing) |
| `"none"` | Compute only (tests / dry-run); return structure without write |

### JSON sketch

```json
{
  "schema_version": 1,
  "tables": [{
    "id": "example-merge",
    "direction": "merge",
    "merge_mode": "field_fill",
    "write_target": "b",
    "a": { "table": "FuelA" },
    "b": { "table": "FuelB" },
    "columns": [
      { "name": "Sync ID", "type": "string" },
      { "name": "Updated At", "type": "timestamp" },
      { "name": "Notes", "type": "string" },
      { "name": "Deleted", "type": "checkbox" }
    ],
    "column_map_a": {},
    "column_map_b": {},
    "keys": ["Sync ID"],
    "timestamp": "Updated At",
    "tombstone": { "column": "Deleted", "true_values": ["true", "1", "yes"] }
  }]
}
```

Push (`direction: "push"`) remains unchanged and additive.

### Materialize (coders)

Edit under existing `third_party/remotetable/src/` when present. Re-run `./third_party/fetch-deps rw remotetable` **only if** `src/` is missing, wrong pin, or read-only.

### Testing merge

```bash
python3 conformance/harness.py
scripts/remotetable merge --config conformance/fixtures/merge_mock_config.json
```


## Testing (CLI / harness)

**Preferred agent/dev test path** (no VE device required):

```bash
# from materialized third_party/remotetable/src (or library clone root)
python3 conformance/harness.py
# or CLI:
scripts/remotetable conformance
# mock directional push:
scripts/remotetable push --config path/to/push-config.json
scripts/remotetable merge --config path/to/merge-config.json
```

Optional live smoke: `scripts/remotetable sheets-smoke --token-file …` (or `REMOTETABLE_TOKEN_FILE`).

CLI/harness is the preferred verification before VE pin promote or emulator tests.
