# remotetable — Spec overview (M1)

**License:** MIT. **Consumer:** any app (VehicleExpenses is equal, not owner).

## Goal M1

Library API + backends **google-sheets**, **excel-graph**, **ethercalc** with shared **conformance** across Go / Python / Kotlin. VE pins AAR/JAR after host ships.

## Operations

See `OPS.md` — list tabs, ensure headers, read/write rows, test connection.

## Auth v1

User-supplied **plain JSON token file** (path). Backend-specific keys.

## Conformance

`conformance/` fixtures + harness. All languages must pass the same goldens (mock backend always; live backends when credentials present).

## Sync product phases (library roadmap)

1. A→B copy/conversion  
2. A↔B merge (id + timestamp)  
3. Collision rules  

M1 is API + three backends + conformance, not full A↔B merge.

## Out of M1

CLI packaging, OnlyOffice/Collabora (see `TODO.md`), full format matrix.
