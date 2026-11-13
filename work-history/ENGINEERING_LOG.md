# ENGINEERING_LOG — remotetable

Append-only activity log for this subproject.

## 2026-08-01 — Staging scaffold

- Created sandbox staging tree under VehicleExpenses `dev-ai-interaction/subprojects/remotetable/`
- MIT license; README; TODO (OnlyOffice/Collabora moved here; phase 2+ listed)
- Working name **remotetable**; excel backend id **excel-graph**
- M1: library for VE (Sheets + excel-graph + EtherCalc + conformance); CLI later
- Awaiting GitHub repo URL under owner user; formal VE plans deferred until then
- Dual eng-log: also note high-level milestones in VehicleExpenses `ENGINEERING_LOG.md` until work splits to dedicated agents

## 2026-08-02 — Plans retargeted to host + third_party

- Policy: VehicleExpenses docs/reference/FIRST_PARTY_LIBS.md + THIRD_PARTY_LAYOUT_FOR_AGENTS.md
- VE pin dir: third_party/remotetable/ (lock sha TBD until first real pin)
- Formal plans (VE sandbox plans/):
  - remotetable: remotetable-m1-lib-conformance-ve-pin-20260802-0348-plan.md
  - extractmail: extractmail-m1-extract-stdin-external-ve-pin-20260802-0348-plan.md
- Implement library work here (~/git/remotetable); VE only pin bumps + thin consumers
- Parallel agents: one track per lib host; avoid fighting over VE app/ except migration PRs
## 2026-08-02 - M1 mock conformance + backend stubs

## 2026-08-02 - M1 mock conformance + backend stubs

- Python RemoteTable + MockBackend; google-sheets/excel-graph/ethercalc skeletons
- conformance/harness.py PASS; Kotlin API sketch; Go mock package

## 2026-11-12 - libpin kit 2026.10.24

- Synced the libpin kit (fetch-deps, get-artifacts, VERSION, libpin-sandbox, libpin-bwrap, libpin-landlock) from orchestration-example@830b09e (libpin@1a98c91, LIBPIN_VERSION 2026.10.24).
- .gitignore un-ignores third_party/VERSION (and the other kit tools where they were still ignored).
- Pin tomls updated as needed for the new kit (example: source_kind=seed-src, default=false, sha256; heavy pins rclone/paddle/paddle-opt/opencv: default=false).

