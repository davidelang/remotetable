# Local EtherCalc (remotetable validation)

**Mapping:** one **room** ≈ one CSV grid ≈ one logical tab (smoke only; multi-room VE layout is later).

| Setting | Default |
|---------|---------|
| Image | `audreyt/ethercalc:latest` |
| URL | `http://127.0.0.1:8000` |
| Smoke room | `ve-smoke` |

## Start / stop

From `third_party/remotetable/src` (or library clone root):

```bash
conformance/ethercalc/up.sh
conformance/ethercalc/down.sh
```

Health: `curl -s "http://127.0.0.1:8000/ve-smoke.csv"` (empty CSV OK).

## Smoke tests

```bash
# with server up
REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/ethercalc_live_smoke.py

# or via main harness (also runs offline first)
REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/harness.py
```

Without docker / server down: smoke **SKIP**s; offline harness still **PASS**.

### Room Vehicles → EtherCalc e2e

Golden json-book (`fixtures/room_vehicles_export.json`, same shape as VE
`RoomVehiclesBackend.exportJsonBook`) always validated offline. With server:

```bash
REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/room_export_to_ethercalc_smoke.py
```

See parent `conformance/README.md` § Room Vehicles → json-book → EtherCalc.

### Room Fuel multi-tab → multi-room EtherCalc

Each `Fuel - *` tab in `fixtures/room_fuel_export.json` is pushed to a **unique room**
(slug + run id). Offline multi-tab json-book always PASS; EtherCalc SKIP without env.

```bash
REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/room_fuel_export_smoke.py
```

See parent `conformance/README.md` § Room Fuel multi-tab.

Optional overrides:

```bash
export REMOTETABLE_ETHERCALC_BASE_URL=http://127.0.0.1:8000
export REMOTETABLE_ETHERCALC_ROOM=ve-smoke
```

No secrets required.

## Semantics note

`audreyt/ethercalc` accepts CSV via `POST /_/{room}` which **appends** a paste block.
Smoke tests use a **unique room name per run**. Application `write_rows(..., mode=replace)`
best-effort clears then POSTs; do not rely on perfect wipe across all EtherCalc versions.
