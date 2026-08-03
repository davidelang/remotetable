# Conformance

## Offline (required)

```bash
python3 conformance/harness.py
```

Covers mock: connection, multi-tab, ensure_headers padding, append, replace.

## Live smoke (opt-in)

```bash
export REMOTETABLE_TOKEN_FILE=/path/to/token.json
export REMOTETABLE_BACKEND=google-sheets   # or excel-graph | ethercalc
export REMOTETABLE_SPREADSHEET_ID=...      # google-sheets only if not in token JSON
python3 conformance/harness.py
```

Token JSON shapes: see `python/remotetable/backends/*.py` docstrings and `spec/OPS.md`.

Without env vars, live section is **SKIP** (exit 0).
