# Conformance

**Contract:** see `../spec/CONTRACT.md` (schema_version 1) for layers, rate limits, soft-delete/expunge, and batch APIs. This harness validates mock ops and optional live smoke against that contract.

Offline (required)

```bash
python3 conformance/harness.py
bash conformance/cli_flag_order_smoke.sh
```

Covers mock: connection, multi-tab, ensure_headers padding, append, replace.
CLI accepts `--backend` / `--fixture` **before or after** the subcommand.

## CLI examples (mock)

```bash
scripts/remotetable --backend mock --fixture conformance/fixtures/mock_book.json test-connection
scripts/remotetable test-connection --backend mock --fixture conformance/fixtures/mock_book.json
scripts/remotetable list-tabs --backend mock --fixture conformance/fixtures/mock_book.json
scripts/remotetable read-rows --tab Vehicles --backend mock --fixture conformance/fixtures/mock_book.json
```

## Live smoke (opt-in — no CI secrets)

Offline harness always exits 0 when live env is unset (`SKIP live smoke`).

### google-sheets

Token JSON:
```json
{ "access_token": "…", "spreadsheet_id": "optional-if-flag" }
```

```bash
export REMOTETABLE_TOKEN_FILE=/path/to/sheets-token.json
export REMOTETABLE_BACKEND=google-sheets
export REMOTETABLE_SPREADSHEET_ID=yourSpreadsheetId   # if not in JSON
python3 conformance/harness.py

# or CLI
scripts/remotetable test-connection --backend google-sheets \
  --token-file /path/to/sheets-token.json --spreadsheet-id ID
```

### excel-graph

Token JSON:
```json
{ "access_token": "…", "item_id": "workbook-driveItem-id", "drive_id": "optional" }
```

```bash
export REMOTETABLE_TOKEN_FILE=/path/to/graph-token.json
export REMOTETABLE_BACKEND=excel-graph
python3 conformance/harness.py

scripts/remotetable test-connection --backend excel-graph --token-file /path/to/graph-token.json
```

### ethercalc

Token JSON or flags:
```json
{ "base_url": "https://ethercalc.example", "room": "mysheet" }
```

```bash
export REMOTETABLE_TOKEN_FILE=/path/to/ethercalc.json
export REMOTETABLE_BACKEND=ethercalc
python3 conformance/harness.py

scripts/remotetable test-connection --backend ethercalc \
  --base-url https://ethercalc.example --room mysheet
```

## Local EtherCalc validation (opt-in)

One **room** ≈ one CSV tab (smoke). Spin-up:

```bash
# from third_party/remotetable/src
conformance/ethercalc/up.sh     # docker: audreyt/ethercalc → http://127.0.0.1:8000
REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/ethercalc_live_smoke.py
conformance/ethercalc/down.sh
```

Default offline `python3 conformance/harness.py` does **not** require docker (smoke SKIP).
See `conformance/ethercalc/README.md`.

## PolicySync / MergeSync scenario suite (default-on soak evidence)

Agent-runnable LWW scenarios (does **not** flip VE PolicySync defaults):

| Suite | When | Scenarios |
|-------|------|-----------|
| Pure offline | Always (harness) | S1–S5 per entity (acks/expenses/vehicles/fuel), S6 vehicle overlay, S7 multi-tab fuel |
| EtherCalc remote | `REMOTETABLE_ETHERCALC_LOCAL=1` | S8 HTTP remote grid merge; multi-tab fuel rooms |

```bash
# offline always
python3 conformance/policysync_scenarios.py
# or full harness
python3 conformance/harness.py

# with local EtherCalc
conformance/ethercalc/up.sh
REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/policysync_scenarios.py
conformance/ethercalc/down.sh
```

VE soak doc: `docs/reference/POLICY_SYNC_PILOT_SOAK.md` (points here for automated evidence).

## Room Vehicles → json-book → EtherCalc (e2e pilot)

Validates the multi-backend story **without Google Sheets**:

| Step | Source | Offline? |
|------|--------|----------|
| Golden export shape | `fixtures/room_vehicles_export.json` (= VE `RoomVehiclesBackend.exportJsonBook`) | Always |
| json-book round-trip | `JsonBookBackend` | Always (harness) |
| Push + read-back | local EtherCalc room | Opt-in |

```bash
# offline only (part of harness.py)
python3 conformance/room_export_to_ethercalc_smoke.py

# with local EtherCalc
conformance/ethercalc/up.sh
REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/room_export_to_ethercalc_smoke.py
# or full harness
REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/harness.py
conformance/ethercalc/down.sh

# optional: app-exported book
ROOM_EXPORT_JSONBOOK=/path/to/vehicles.json \
  REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/room_export_to_ethercalc_smoke.py
```

VE producer: `app/.../RoomVehiclesBackend.exportJsonBook`. Production Sheets path untouched.

## Room Fuel multi-tab → json-book → EtherCalc (pilot)

| Step | Source | Offline? |
|------|--------|----------|
| Golden multi-tab fuel | `fixtures/room_fuel_export.json` (= VE `RoomFuelBackend.exportJsonBook`) | Always |
| json-book round-trip | ≥2 `Fuel - *` tabs, Sync ID + Notes | Always |
| Multi-room EtherCalc push | **each** fuel tab → unique room (`ve-fuel-{slug}-{run}`) | Opt-in |

EtherCalc model: **one room ≈ one grid**. Multi-tab export maps each `Fuel - {name}` to its own room.

```bash
# offline only (also in harness.py)
python3 conformance/room_fuel_export_smoke.py

# multi-tab EtherCalc (all fuel tabs in fixture)
conformance/ethercalc/up.sh
REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/room_fuel_export_smoke.py
conformance/ethercalc/down.sh

# optional app-exported book
ROOM_FUEL_JSONBOOK=/path/to/fuel_book.json \
  REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/room_fuel_export_smoke.py
```

VE: `app/.../RoomFuelBackend.kt` (read-only default; not registered as Sheets dest).
Thin pointer: `scripts/room-fuel-export-smoke.sh`.
