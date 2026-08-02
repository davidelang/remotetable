# remotetable

**MIT** · Provider-neutral **remote tables** abstraction (rclone-inspired), multi-format I/O, and eventual A↔B sync/merge.

Not VehicleExpenses-specific. VehicleExpenses will become a consumer after the library meets a conformance suite with **no loss of app functionality**.

## Status

Pre-repo staging under VehicleExpenses sandbox. Awaiting GitHub URL under the owner’s user account.

| Milestone | Scope |
|-----------|--------|
| **M1 (app)** | Library API + backends: **Google Sheets**, **excel-graph** (Microsoft Graph Excel Online), **EtherCalc**; Kotlin + Go + Python stay on **same conformance suite**; VE cutover for those three; other VE backends keep in-tree code until ported |
| **M2** | CLI tools, format conversion (A→B including remote↔remote e.g. Sheets→EtherCalc) |
| **M3+** | A↔B merge (id + row timestamp), then collision rules; remaining backends; **OnlyOffice/Collabora**; packaging (tgz/deb/rpm/OpenWrt/PPA) later |

## Implementations

- `go/` — primary non-Android implementation (static binary for hosts later)
- `python/` — dual implementation for tinkering (not necessarily thin wrapper)
- `kotlin/` — Android/VE-oriented impl; AI-assisted translation from reference; **must pass conformance**
- `spec/` — operations + formats + backend IDs
- `conformance/` — golden fixtures and harness (all languages)

No single native binary required on Android (option C).

## Backend IDs (capability names)

| ID | Product |
|----|---------|
| `google-sheets` | Google Sheets |
| `excel-graph` | Excel Online via Microsoft Graph (co-authoring workbook API — not “file on shared drive only”) |
| `ethercalc` | EtherCalc |
| `onlyoffice` / `collabora` | Deferred (TODO) |
| … | Other VE backends phased in |

**Branding note for VE migration:** rename existing app/UI wire name `excel` → **`excel-graph`** when cutting over (capability unchanged).

## Formats

JSON, CSV, TSV, name=value; multi-tab as **zip** or **tar** (+ gz/xz) of **one file per tab**.  
`--wide`: pad columns with empty fields / tabs for visual alignment (CSV assumes trim of edges per usual CSV rules); **never** merge multiple tabs into one wide matrix.

## Auth (v1)

User-supplied **plain JSON token file**. OAuth device flow and service accounts later.

## Authorship / agents

After GitHub publish, **dedicated agents** own this repo. They should not fight over VehicleExpenses app trees except coordinated migration PRs.

## License

MIT — see `LICENSE`.
