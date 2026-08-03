# TODO — remotetable

Backlog only. Phase 1 (library for VehicleExpenses cutover of first three backends) is driven by engineering log + plans once GitHub exists, not by this list alone.

## Moved from VehicleExpenses

- [ ] **OnlyOffice / Collabora** tabular backends (real implementations).  
  Origin: VehicleExpenses `TODO.md` — catalog + `DeferredTabularBackendStub` existed; product still wanted; spike had API approach NO-GO.  
  **Lives here** going forward. Not required for M1 cutover of Sheets / excel-graph / EtherCalc.

## Phase 2+ (discussed; not M1)

- [ ] CLI tools (`remotetable` / Python) as first-class product
- [ ] Format conversion A→B (files and remotes), including Google Sheets ↔ EtherCalc as conversion demo
- [ ] A↔B merge: row id key + per-row timestamp
- [ ] A↔B sync rules / collision tooling
- [ ] Port remaining VehicleExpenses backends (Baserow, NocoDB, PocketBase, Supabase, Airtable, Firebase, Zoho, CSV-zip parity, stubs cleanup)
- [ ] Packaging: tgz → deb → rpm → OpenWrt → LuCI → Ubuntu PPA (after library stable)
- [ ] OAuth device flow and service-account auth (after token-file JSON)
- [ ] GitHub Actions multi-language conformance (Go + Python; Kotlin via wrapper/emulator if needed)

## VehicleExpenses coordination (not implemented in this repo)

- [ ] VE: rename wire/UI backend id `excel` → **`excel-graph`** (capability unchanged)
- [ ] VE: replace internal tabular API calls with remotetable for the first three backends
- [ ] VE: leave “Other” / remaining backends on in-tree code until ported

# Future work

M2 deferred: packaging/trainer/full format matrix / remaining backends
