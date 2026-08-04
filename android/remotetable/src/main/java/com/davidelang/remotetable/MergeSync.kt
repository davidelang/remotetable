package com.davidelang.remotetable

import org.json.JSONArray
import org.json.JSONObject

/**
 * L3 A↔B merge: union / lww_row / field_fill (CONTRACT.md).
 * Config-driven only; no domain field meaning.
 */
enum class MergeMode {
    UNION,
    LWW_ROW,
    FIELD_FILL,
    ;

    companion object {
        fun parse(raw: String?): MergeMode = when (raw?.trim()?.lowercase()) {
            "union" -> UNION
            "lww_row", "lww", "lww-row" -> LWW_ROW
            "field_fill", "field-fill", "fill" -> FIELD_FILL
            else -> LWW_ROW
        }
    }
}

data class MergeUnit(
    val id: String,
    val mergeMode: MergeMode,
    /** "a" | "b" | "none" */
    val writeTarget: String,
    val tableA: String,
    val tableB: String,
    val columns: List<ColumnDef>,
    val columnMapA: Map<String, String>,
    val columnMapB: Map<String, String>,
    /** Logical key column names (after maps). */
    val keys: List<String>,
    /** Logical timestamp column name. */
    val timestamp: String?,
    val tombstone: TombstoneConfig?,
)

data class MergeResult(
    val tableId: String,
    val mode: MergeMode,
    val rowCount: Int,
    val keysFromAOnly: Int,
    val keysFromBOnly: Int,
    val keysBoth: Int,
    val written: Boolean,
    val data: TabData,
)

object MergeSync {
    fun parseMergeUnit(obj: JSONObject): MergeUnit {
        val columns = mutableListOf<ColumnDef>()
        val cols = obj.optJSONArray("columns") ?: JSONArray()
        for (i in 0 until cols.length()) {
            val c = cols.optJSONObject(i) ?: continue
            columns.add(ColumnDef(c.optString("name"), c.optString("type", "string")))
        }
        fun parseMap(name: String): Map<String, String> {
            val out = mutableMapOf<String, String>()
            val cm = obj.optJSONObject(name) ?: return out
            val keys = cm.keys()
            while (keys.hasNext()) {
                val k = keys.next()
                out[k] = cm.optString(k)
            }
            return out
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
        val a = obj.optJSONObject("a")
        val b = obj.optJSONObject("b")
        // legacy source/dest accepted as a/b
        val source = obj.optJSONObject("source")
        val dest = obj.optJSONObject("dest")
        return MergeUnit(
            id = obj.optString("id", "merge"),
            mergeMode = MergeMode.parse(obj.optString("merge_mode", "lww_row")),
            writeTarget = obj.optString("write_target", "none").ifBlank { "none" },
            tableA = a?.optString("table") ?: a?.optString("tab")
                ?: source?.optString("table") ?: source?.optString("tab").orEmpty(),
            tableB = b?.optString("table") ?: b?.optString("tab")
                ?: dest?.optString("table") ?: dest?.optString("tab").orEmpty(),
            columns = columns,
            columnMapA = parseMap("column_map_a").ifEmpty { parseMap("column_map") },
            columnMapB = parseMap("column_map_b"),
            keys = keyList,
            timestamp = obj.optString("timestamp").ifBlank { null },
            tombstone = tomb,
        )
    }

    /**
     * Pure merge of two tables already loaded as [TabData].
     * Maps each side into logical [MergeUnit.columns] names, then applies mode.
     */
    fun mergeTabData(a: TabData, b: TabData, unit: MergeUnit): TabData {
        require(unit.keys.isNotEmpty()) { "keys required" }
        val logical = if (unit.columns.isNotEmpty()) {
            unit.columns.map { it.name }
        } else {
            // union of both header sets after maps
            val ha = a.headers.map { unit.columnMapA[it] ?: it }
            val hb = b.headers.map { unit.columnMapB[it] ?: it }
            (ha + hb).distinct()
        }
        val mapA = indexLogical(a, logical, unit.columnMapA, unit.columns, unit.keys)
        val mapB = indexLogical(b, logical, unit.columnMapB, unit.columns, unit.keys)
        val allKeys = LinkedHashSet<String>().apply {
            addAll(mapA.keys)
            addAll(mapB.keys)
        }
        val outRows = mutableListOf<List<String>>()
        for (key in allKeys) {
            val rowA = mapA[key]
            val rowB = mapB[key]
            val merged = when (unit.mergeMode) {
                MergeMode.UNION, MergeMode.LWW_ROW ->
                    pickFullRow(rowA, rowB, logical, unit)
                MergeMode.FIELD_FILL ->
                    fieldFill(rowA, rowB, logical, unit)
            }
            outRows.add(CellTypes.coerceRow(logical, merged, unit.columns))
        }
        return TabData(logical, outRows)
    }

    fun merge(backendA: Backend, backendB: Backend, unit: MergeUnit): MergeResult {
        require(
            unit.writeTarget in setOf("a", "b", "none") || unit.writeTarget.isBlank(),
        ) { "write_target must be a|b|none" }
        val dataA = backendA.readRows(unit.tableA)
        val dataB = backendB.readRows(unit.tableB)
        val merged = mergeTabData(dataA, dataB, unit)
        val idxA = indexLogical(dataA, merged.headers, unit.columnMapA, unit.columns, unit.keys)
        val idxB = indexLogical(dataB, merged.headers, unit.columnMapB, unit.columns, unit.keys)
        var aOnly = 0
        var bOnly = 0
        var both = 0
        val all = (idxA.keys + idxB.keys).toSet()
        for (k in all) {
            when {
                k in idxA && k in idxB -> both++
                k in idxA -> aOnly++
                else -> bOnly++
            }
        }
        var written = false
        val target = unit.writeTarget.ifBlank { "none" }
        if (target == "a") {
            backendA.ensureHeaders(unit.tableA, merged.headers)
            backendA.writeRows(unit.tableA, merged.headers, merged.rows, mode = "replace")
            written = true
        } else if (target == "b") {
            backendB.ensureHeaders(unit.tableB, merged.headers)
            backendB.writeRows(unit.tableB, merged.headers, merged.rows, mode = "replace")
            written = true
        }
        return MergeResult(
            tableId = unit.id,
            mode = unit.mergeMode,
            rowCount = merged.rows.size,
            keysFromAOnly = aOnly,
            keysFromBOnly = bOnly,
            keysBoth = both,
            written = written,
            data = merged,
        )
    }

    /** Map physical tab into key → logical row. */
    internal fun indexLogical(
        data: TabData,
        logical: List<String>,
        columnMap: Map<String, String>,
        columns: List<ColumnDef>,
        keys: List<String>,
    ): Map<String, List<String>> {
        val out = LinkedHashMap<String, List<String>>()
        val idx = RowOps.headerIndex(logical)
        for (row in data.rows) {
            val mapped = CellTypes.coerceRow(
                logical,
                RowOps.mapRow(data.headers, row, logical, columnMap),
                columns,
            )
            val key = RowOps.keyOf(mapped, idx, keys)
            if (key.isBlank()) continue
            out.putIfAbsent(key, mapped)
        }
        return out
    }

    /**
     * Full-row pick: newer ts wins; missing ts on one side → other wins if present;
     * equal ts → prefer a. Newer tombstone over older live is automatic via ts.
     */
    internal fun pickFullRow(
        rowA: List<String>?,
        rowB: List<String>?,
        logical: List<String>,
        unit: MergeUnit,
    ): List<String> {
        if (rowA == null && rowB == null) return List(logical.size) { "" }
        if (rowA == null) return rowB!!
        if (rowB == null) return rowA
        val cmp = compareTs(rowA, rowB, logical, unit.timestamp)
        // cmp > 0 → a newer; < 0 → b newer; 0 → prefer a
        return if (cmp >= 0) rowA else rowB
    }

    internal fun fieldFill(
        rowA: List<String>?,
        rowB: List<String>?,
        logical: List<String>,
        unit: MergeUnit,
    ): List<String> {
        if (rowA == null && rowB == null) return List(logical.size) { "" }
        if (rowA == null) return rowB!!
        if (rowB == null) return rowA
        val winnerIsA = compareTs(rowA, rowB, logical, unit.timestamp) >= 0
        val winner = if (winnerIsA) rowA else rowB
        val loser = if (winnerIsA) rowB else rowA
        val out = winner.toMutableList()
        while (out.size < logical.size) out.add("")
        for (i in logical.indices) {
            val w = out.getOrElse(i) { "" }
            val l = loser.getOrElse(i) { "" }
            if (w.trim().isEmpty() && l.trim().isNotEmpty()) {
                out[i] = l
            }
        }
        // Ensure tombstone from winner if winner is tombstoned (already in winner row).
        // If loser is newer tombstone — compareTs already chose winner by ts.
        return out
    }

    /** Positive if a newer than b; negative if b newer; 0 equal → callers prefer a. */
    internal fun compareTs(
        rowA: List<String>,
        rowB: List<String>,
        logical: List<String>,
        timestamp: String?,
    ): Int {
        if (timestamp.isNullOrBlank()) return 0 // prefer a
        val idx = RowOps.headerIndex(logical)
        val ta = parseTs(RowOps.cell(rowA, idx, timestamp))
        val tb = parseTs(RowOps.cell(rowB, idx, timestamp))
        return when {
            ta == 0L && tb == 0L -> 0
            ta == 0L -> -1 // b has ts, a missing → b wins
            tb == 0L -> 1
            ta > tb -> 1
            ta < tb -> -1
            else -> 0
        }
    }

    fun parseTs(raw: String): Long {
        val t = raw.trim()
        if (t.isEmpty()) return 0L
        t.toLongOrNull()?.let { return it }
        return t.filter { it.isDigit() }.take(13).toLongOrNull() ?: 0L
    }
}
