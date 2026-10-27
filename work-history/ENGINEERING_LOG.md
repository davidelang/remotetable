# ENGINEERING_LOG — remotetable

Append-only activity log for this subproject.

## 2026-08-01 — Staging scaffold

- Created sandbox staging tree under VehicleExpenses `dev-ai-interaction/subprojects/remotetable/`
- MIT license; README; TODO (OnlyOffice/Collabora moved here; phase 2+ listed)
- Working name **remotetable**; excel backend id **excel-graph**
- M1: library for VE (Sheets + excel-graph + EtherCalc + conformance); CLI later
- Awaiting GitHub repo URL under owner user; formal VE plans deferred until then
- Dual eng-log: also note high-level milestones in VehicleExpenses `ENGINEERING_LOG.md` until work splits to dedicated agents

## 2026-08-02 — third_party live; plans retargeted

- VE branch has third_party/remotetable with lock.yaml (sha TBD until first pin)
- Host: ~/git/remotetable — GitHub davidelang/remotetable
- Formal plans under dev-ai-interaction/plans/*-20260802-0348-plan.md
- Continue email/tabular work via library host + VE pin bumps only

## 2026-08-02 - M1 product: mock conformance + live backends + AAR

- Python RemoteTable, MockBackend, google-sheets/excel-graph/ethercalc HTTP clients
- conformance harness PASS; android AAR build (Kotlin API)
- Branch email-connection


## 2026-08-02 - M1 product commit (after object perms fix)

- Python RemoteTable + MockBackend + live google-sheets/excel-graph/ethercalc
- conformance PASS; Android AAR recipe; branch email-connection


## 2026-08-02 - M1 product commit after object perms fix

- Python RemoteTable + MockBackend + live google-sheets/excel-graph/ethercalc
- conformance PASS; Android AAR recipe; branch email-connection


## 2026-08-02 - M2 tests CLI live AAR backends

- Expanded mock harness (replace, multi-tab, pad, empty book) + opt-in live smoke
- Host CLI scripts/remotetable + python -m remotetable
- Android AAR: GoogleSheetsBackend, ExcelGraphBackend, EtherCalcBackend + Backends factory

## 2026-08-02 - M2.5 CLI flag order + live smoke docs

- normalize_argv: --backend/--fixture before or after subcommand
- conformance/cli_flag_order_smoke.sh; conformance/README live copy-paste

## 2026-08-03 - PR prepared: sandbox/PRs/PR-email-connection.md (rebase onto master; tests OK)
