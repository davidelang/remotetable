package com.davidelang.remotetable

import org.json.JSONArray
import org.json.JSONObject

/**
 * L3 directional policy MVP (schema_version 1).
 * JSON-driven **push** (A→B): keys + timestamp don't-clobber; column_map; soft-delete propagate.
 * Full A↔B merge is out of foundation scope.
 */
data class ColumnDef(val name: String, val type: String = "string")

data class TombstoneConfig(
    val column: String,
    val trueValues: List<String> = RowOps.DEFAULT_TRUE_VALUES,
)

data class TableSyncUnit(
    val id: String,
    val direction: String = "push",
    val sourceTable: String,
    val destTable: String,
    val columns: List<ColumnDef>,
    val columnMap: Map<String, String> = emptyMap(),
    val keys: List<String>,
    val timestamp: String? = null,
    val tombstone: TombstoneConfig? = null,
)

data class PushResult(
    val tableId: String,
    val written: Int,
    val softDeleted: Int,
    val skippedOlder: Int,
)

object PolicySync {
    fun parseTableUnit(obj: JSONObject): TableSyncUnit {
        val columns = mutableListOf<ColumnDef>()
        val cols = obj.optJSONArray("columns") ?: JSONArray()
        for (i in 0 until cols.length()) {
            val c = cols.optJSONObject(i) ?: continue
            columns.add(ColumnDef(c.optString("name"), c.optString("type", "string")))
        }
        val map = mutableMapOf<String, String>()
        val cm = obj.optJSONObject("column_map")
        if (cm != null) {
            val keys = cm.keys()
            while (keys.hasNext()) {
                val k = keys.next()
                map[k] = cm.optString(k)
            }
        }
        val keyList = mutableListOf<String>()
        val ka = obj.optJSONArray("keys") ?: JSONArray()
        for (i in 0 until ka.length()) keyList.add(ka.optString(i))
        val tomb = obj.optJSONObject("tombstone")?.let { t ->
            val tvs = mutableListOf<String>()
            val arr = t.optJSONArray("true_values")
            if (arr != null) {
                for (i in 0 until arr.length()) tvs.add(arr.opt(i)?.toString() ?: "")
            }
            if (tvs.isEmpty()) tvs.addAll(RowOps.DEFAULT_TRUE_VALUES)
            TombstoneConfig(t.optString("column"), tvs.filter { it.isNotBlank() })
        }
        val source = obj.optJSONObject("source")
        val dest = obj.optJSONObject("dest")
        return TableSyncUnit(
            id = obj.optString("id", "table"),
            direction = obj.optString("direction", "push"),
            sourceTable = source?.optString("table") ?: source?.optString("tab").orEmpty(),
            destTable = dest?.optString("table") ?: dest?.optString("tab").orEmpty(),
            columns = columns,
            columnMap = map,
            keys = keyList,
            timestamp = obj.optString("timestamp").ifBlank { null },
            tombstone = tomb,
        )
    }

    /**
     * Directional push source → dest for one table unit.
     * - ensure dest headers from ordered [TableSyncUnit.columns] (dest names)
     * - soft-delete: flag-only on key match
     * - insert missing keys; update when source timestamp >= dest (when configured)
     */
    fun push(source: Backend, dest: Backend, unit: TableSyncUnit): PushResult {
        require(unit.direction == "push") { "only direction=push in foundation MVP" }
        require(unit.keys.isNotEmpty()) { "keys required" }
        val srcData = source.readRows(unit.sourceTable)
        val destHeaderNames = if (unit.columns.isNotEmpty()) {
            unit.columns.map { it.name }
        } else {
            // identity from source headers via map values or source names
            srcData.headers.map { unit.columnMap[it] ?: it }
        }
        dest.ensureHeaders(unit.destTable, destHeaderNames)
        var destData = dest.readRows(unit.destTable)

        // Soft-delete propagate first (flag only)
        var softDeleted = 0
        if (unit.tombstone != null) {
            val (newDest, n) = RowOps.propagateSoftDeletes(
                source = srcData,
                dest = destData,
                keys = unit.keys,
                tombstoneColumn = unit.tombstone.column,
                trueValues = unit.tombstone.trueValues,
                columnMap = unit.columnMap,
            )
            if (n > 0) {
                dest.writeRows(unit.destTable, newDest.headers, newDest.rows, mode = "replace")
                destData = newDest
                softDeleted = n
            }
        }

        val destIdx = RowOps.headerIndex(destData.headers)
        val srcIdx = RowOps.headerIndex(srcData.headers)
        fun destKeyNames(): List<String> = unit.keys.map { unit.columnMap[it] ?: it }
        val dKeys = destKeyNames()
        val byKey = LinkedHashMap<String, Int>()
        destData.rows.forEachIndexed { i, row ->
            val k = RowOps.keyOf(row, destIdx, dKeys)
            if (k.isNotBlank()) byKey.putIfAbsent(k, i)
        }

        val rows = destData.rows.map { it.toMutableList() }.toMutableList()
        var written = 0
        var skippedOlder = 0
        val tsSrc = unit.timestamp
        val tsDest = unit.timestamp?.let { unit.columnMap[it] ?: it }

        for (srow in srcData.rows) {
            // skip pure tombstone-only create
            if (unit.tombstone != null) {
                val tcol = unit.tombstone.column
                val tv = RowOps.cell(srow, srcIdx, tcol)
                if (RowOps.isTruthyTombstone(tv, unit.tombstone.trueValues)) {
                    val k = RowOps.keyOf(srow, srcIdx, unit.keys)
                    if (k !in byKey) continue // no dest match → no-op (already handled)
                }
            }
            val sk = RowOps.keyOf(srow, srcIdx, unit.keys)
            if (sk.isBlank()) continue
            val destHdrs = destData.headers.ifEmpty { destHeaderNames }
            val mapped = CellTypes.coerceRow(
                destHdrs,
                RowOps.mapRow(srcData.headers, srow, destHdrs, unit.columnMap),
                unit.columns,
            )
            val di = byKey[sk]
            if (di == null) {
                rows.add(mapped.toMutableList())
                byKey[sk] = rows.lastIndex
                written++
            } else {
                if (tsSrc != null && tsDest != null) {
                    val sTs = parseTs(RowOps.cell(srow, srcIdx, tsSrc))
                    val dTs = parseTs(RowOps.cell(rows[di], destIdx, tsDest))
                    if (sTs < dTs) {
                        skippedOlder++
                        continue
                    }
                }
                // merge mapped non-empty into dest row (don't clear unspecified)
                val cur = rows[di]
                while (cur.size < destData.headers.size) cur.add("")
                mapped.forEachIndexed { i, v ->
                    if (i < cur.size && v.isNotEmpty()) cur[i] = v
                }
                written++
            }
        }

        val headers = destData.headers.ifEmpty { destHeaderNames }
        dest.writeRows(unit.destTable, headers, rows.map { pad(it, headers.size) }, mode = "replace")
        return PushResult(unit.id, written, softDeleted, skippedOlder)
    }

    private fun pad(row: List<String>, width: Int): List<String> {
        if (row.size >= width) return row.take(width)
        return row + List(width - row.size) { "" }
    }

    private fun parseTs(raw: String): Long {
        val t = raw.trim()
        if (t.isEmpty()) return 0L
        t.toLongOrNull()?.let { return it }
        // ISO-8601 best-effort: strip non-digits for weak ordering only
        return t.filter { it.isDigit() }.take(13).toLongOrNull() ?: 0L
    }

    /** Apply optional rate_limits block from contract JSON. */
    fun applyRateLimitsFromConfig(root: JSONObject) {
        val rl = root.optJSONObject("rate_limits") ?: return
        val keys = rl.keys()
        while (keys.hasNext()) {
            val backendId = keys.next()
            val cfg = rl.optJSONObject(backendId) ?: continue
            val map = mutableMapOf<String, Any?>()
            val ck = cfg.keys()
            while (ck.hasNext()) {
                val k = ck.next()
                map[k] = cfg.opt(k)
            }
            RateLimitRegistry.setDefault(backendId, RateLimitConfig.fromMap(map))
        }
    }
}
