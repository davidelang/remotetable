package com.davidelang.remotetable

/**
 * L1/L2 helpers: named columns, AND-equality filter, soft-delete, expunge defaults.
 * See `spec/CONTRACT.md`.
 */
object RowOps {
    fun headerIndex(headers: List<String>): Map<String, Int> =
        headers.withIndex().associate { it.value to it.index }

    fun cell(row: List<String>, idx: Map<String, Int>, name: String): String {
        val i = idx[name] ?: return ""
        return row.getOrElse(i) { "" }
    }

    fun matchesFilter(row: List<String>, idx: Map<String, Int>, filter: Map<String, String>): Boolean {
        if (filter.isEmpty()) return false
        for ((k, v) in filter) {
            if (cell(row, idx, k) != v) return false
        }
        return true
    }

    fun applySet(row: List<String>, headers: List<String>, setFields: Map<String, String>): List<String> {
        val out = row.toMutableList()
        while (out.size < headers.size) out.add("")
        val idx = headerIndex(headers)
        for ((name, value) in setFields) {
            val i = idx[name] ?: continue
            out[i] = value
        }
        return out
    }

    fun isTruthyTombstone(value: String, trueValues: Collection<String>): Boolean {
        val v = value.trim()
        if (v.isEmpty()) return false
        val lower = v.lowercase()
        return trueValues.any { it.equals(v, ignoreCase = true) || it.lowercase() == lower }
    }

    val DEFAULT_TRUE_VALUES: List<String> = listOf("true", "1", "yes", "TRUE", "True")

    /**
     * Soft-delete propagate rule (contract):
     * source tombstoned + dest has key match → set dest tombstone; no dest match → no-op.
     * Returns number of dest rows updated.
     */
    fun propagateSoftDeletes(
        source: TabData,
        dest: TabData,
        keys: List<String>,
        tombstoneColumn: String,
        trueValues: Collection<String> = DEFAULT_TRUE_VALUES,
        columnMap: Map<String, String> = emptyMap(),
    ): Pair<TabData, Int> {
        if (source.headers.isEmpty() || keys.isEmpty()) return dest to 0
        fun mapName(src: String): String = columnMap[src] ?: src
        val srcIdx = headerIndex(source.headers)
        val destKeys = keys.map { mapName(it) }
        val destTomb = mapName(tombstoneColumn)
        val destIdx = headerIndex(dest.headers)
        if (destKeys.any { it !in destIdx } || destTomb !in destIdx) return dest to 0

        val destByKey = LinkedHashMap<String, Int>()
        dest.rows.forEachIndexed { i, row ->
            val key = destKeys.joinToString("\u0001") { cell(row, destIdx, it) }
            if (key.isNotBlank() && key != destKeys.joinToString("\u0001") { "" }) {
                destByKey.putIfAbsent(key, i)
            }
        }

        val newRows = dest.rows.map { it.toMutableList() }.toMutableList()
        var updated = 0
        for (srow in source.rows) {
            val rawTomb = cell(srow, srcIdx, tombstoneColumn)
            if (!isTruthyTombstone(rawTomb, trueValues)) continue
            val key = keys.joinToString("\u0001") { cell(srow, srcIdx, it) }
            if (key.isBlank()) continue
            val di = destByKey[key] ?: continue // no dest match → no-op
            val drow = newRows[di]
            while (drow.size < dest.headers.size) drow.add("")
            val ti = destIdx[destTomb]!!
            if (!isTruthyTombstone(drow.getOrElse(ti) { "" }, trueValues)) {
                drow[ti] = "true"
                updated++
            }
        }
        return TabData(dest.headers, newRows.map { it.toList() }) to updated
    }

    /** Map a source row to dest header order via column_map (source→dest). */
    fun mapRow(
        sourceHeaders: List<String>,
        sourceRow: List<String>,
        destHeaders: List<String>,
        columnMap: Map<String, String>,
    ): List<String> {
        val srcIdx = headerIndex(sourceHeaders)
        val out = MutableList(destHeaders.size) { "" }
        val destIdx = headerIndex(destHeaders)
        if (columnMap.isEmpty()) {
            for (h in sourceHeaders) {
                val j = destIdx[h] ?: continue
                out[j] = cell(sourceRow, srcIdx, h)
            }
            return out
        }
        for ((srcName, destName) in columnMap) {
            val j = destIdx[destName] ?: continue
            out[j] = cell(sourceRow, srcIdx, srcName)
        }
        return out
    }

    fun keyOf(row: List<String>, idx: Map<String, Int>, keys: List<String>): String =
        keys.joinToString("\u0001") { cell(row, idx, it) }
}
