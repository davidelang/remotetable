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

## 2026-08-05 - filter language v1.1 CODE LANDED

- Plan (VE sandbox): remotetable-richer-filters-in-isempty-20260805-0033-plan.md
- RowOps/matchesFilter: in: / empty: / is_empty: / not_empty:; equality unchanged
- Python parity + harness PASS offline; CONTRACT Filter language v1.1
- Commit 3a83e57; AAR promote for VE pin


## 2026-08-05 - room→ethercalc e2e validation CODE LANDED

- room_export_to_ethercalc_smoke.py + fixtures/room_vehicles_export.json
- Offline json-book PASS; EtherCalc e2e PASS with up.sh
- Harness wires offline half always; EtherCalc SKIP without env


## 2026-08-05 - room-fuel multi-tab pilot smoke CODE LANDED

- room_fuel_export_smoke.py + fixtures/room_fuel_export.json
- Offline multi-tab PASS; EtherCalc one-tab PASS with up.sh


## 2026-08-05 - room-fuel multi-tab multi-room EtherCalc CODE LANDED

- room_fuel_export_smoke: each fuel tab → unique EC room; offline PASS; e2e PASS with up.sh


## 2026-08-05 - PolicySync scenario suite CODE LANDED

- policysync_scenarios.py S1–S7 offline PASS; S8 EtherCalc PASS with up.sh
- Harness wires pure suite always


## 2026-08-05 - local PR-fix-syncing prepared (STAGE 1 remotetable)

- History: rebased onto origin/master a2657dc; 16→11 logical commits (eng-log fixups); backup-fix-syncing @ ad97c08; cleaned HEAD 8f7b67b; TREE_MATCHES_BACKUP YES
- PR: /home/dlang/git/remotetable/sandbox/PRs/PR-fix-syncing.md
- Two-stage: merge this library PR first; then VE pin to merged master tip (Stage 2)
- Pre-rebase tip (old VE pin) 188b328 kept as backup-fix-syncing-pre-rebase

## 2026-08-05 - merge: fix-syncing into master (Stage 1)

- PR: sandbox/PRs/PR-fix-syncing.md
- Source tip: e11b0aa (11 product + eng-log prep); base a2657dc
- Path: FF index-first via merge-branch-into-master.sh; special-file protocol
- Delivered: CONTRACT schema_v1, L0–L3, offline backends, filter v1.1, EtherCalc harness, PolicySync S1–S8
- Verify: python3 conformance/harness.py PASS offline; rowdb unit + cli_flag_order PASS
- TODO: closed A↔B merge + A↔B sync rules backlog items; project-facts verify entrypoint set
- Next (Stage 2 VE): pin third_party/remotetable + rebuild AAR to this master tip after commit
