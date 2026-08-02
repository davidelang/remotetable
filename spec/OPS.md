# remotetable operations (M1)

Backend-neutral ops. Implementations: Go, Python, Kotlin. Conformance goldens under `conformance/`.

## Connection

| Op | Input | Output |
|----|--------|--------|
| `test_connection` | backend id + token file path | `{ "ok": bool, "message": string }` |

## Tabs / headers

| Op | Input | Output |
|----|--------|--------|
| `list_tabs` | connection | `{ "tabs": [string] }` |
| `ensure_headers` | connection, tab, headers[] | `{ "ok": bool, "headers": [string] }` |

## Rows

| Op | Input | Output |
|----|--------|--------|
| `read_rows` | connection, tab | `{ "headers": [string], "rows": [[string]] }` |
| `write_rows` | connection, tab, headers, rows, mode=`replace`\|`append` | `{ "written": int }` |

## Formats (lib core M1)

- **JSON:** object with `tabs: { name: { headers, rows } }` or single-tab shorthand.
- Multi-tab zip of one JSON/CSV per tab is M2; M1 backends use native multi-tab APIs.

## Backend IDs (M1 required)

- `google-sheets`
- `excel-graph` (Microsoft Graph Excel Online — not Drive-file-only)
- `ethercalc`

## Auth v1

Plain JSON token file path. Shape per backend is documented under `spec/auth-*.md` or in backend README. No OAuth device flow in M1.

## Errors

Stable error codes: `auth`, `not_found`, `permission`, `network`, `unsupported`, `invalid`.
