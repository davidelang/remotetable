# remotetable — Spec overview (draft)

Canonical details will grow here and under `conformance/`.

## Operations (sketch)

- List tabs / ensure headers  
- Read all rows / write rows (full or incremental as backends allow)  
- Test connection  
- Format codecs: JSON, CSV, TSV, name=value; multi-tab zip|tar|tar.gz|tar.xz  

## Backend IDs

`google-sheets` | `excel-graph` | `ethercalc` | (later) others including onlyoffice/collabora  

## Sync phases (product)

1. A→B copy/conversion (including remote→remote)  
2. A↔B merge (row id + timestamp)  
3. A↔B with collision rules/tools  

## Auth v1

Token file: plain JSON path (shape TBD per backend).

## Conformance

All of Go, Python, Kotlin must pass the same fixtures in `conformance/`.
