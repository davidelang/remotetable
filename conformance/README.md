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
