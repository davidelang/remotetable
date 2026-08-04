package com.davidelang.remotetable

/**
 * Spreadsheet-ish type coerce for wire cells (CONTRACT schema_version 1).
 * Unknown type → string (trimmed). Output is always a string cell value.
 */
object CellTypes {
    const val STRING = "string"
    const val NUMBER = "number"
    const val TIMESTAMP = "timestamp"
    const val CHECKBOX = "checkbox"

    fun coerce(value: String, type: String?): String {
        val t = type?.trim()?.lowercase().orEmpty()
        val raw = value
        return when (t) {
            "", STRING -> raw
            NUMBER -> coerceNumber(raw)
            TIMESTAMP -> coerceTimestamp(raw)
            CHECKBOX -> coerceCheckbox(raw)
            else -> raw
        }
    }

    fun coerceNumber(raw: String): String {
        val s = raw.trim()
        if (s.isEmpty()) return ""
        // strip currency symbols / spaces; keep digits, dot, minus
        val cleaned = s.replace(Regex("""[^\d.\-eE+]"""), "")
        if (cleaned.isEmpty()) return s
        return cleaned.toDoubleOrNull()?.let {
            // avoid scientific noise for whole numbers
            if (it == it.toLong().toDouble() && !it.isNaN() && it in Long.MIN_VALUE.toDouble()..Long.MAX_VALUE.toDouble()) {
                it.toLong().toString()
            } else {
                it.toString()
            }
        } ?: s
    }

    fun coerceTimestamp(raw: String): String {
        val s = raw.trim()
        if (s.isEmpty()) return ""
        s.toLongOrNull()?.let { return it.toString() }
        // ISO-8601-ish: extract digits for weak epoch ms if pure digits after strip
        val digits = s.filter { it.isDigit() }
        if (digits.length >= 10) {
            // prefer first 13 as millis, else 10 as seconds → millis
            return when {
                digits.length >= 13 -> digits.take(13)
                else -> (digits.take(10).toLongOrNull()?.times(1000L))?.toString() ?: s
            }
        }
        return s
    }

    fun coerceCheckbox(raw: String): String {
        val s = raw.trim()
        if (s.isEmpty()) return "false"
        val lower = s.lowercase()
        return when (lower) {
            "true", "1", "yes", "y", "on", "checked" -> "true"
            "false", "0", "no", "n", "off", "unchecked" -> "false"
            else -> if (RowOps.isTruthyTombstone(s, RowOps.DEFAULT_TRUE_VALUES)) "true" else "false"
        }
    }

    /** Coerce each cell in [row] by matching [headers] to [columns] (by dest column name). */
    fun coerceRow(
        headers: List<String>,
        row: List<String>,
        columns: List<ColumnDef>,
    ): List<String> {
        val typeByName = columns.associate { it.name to it.type }
        return headers.mapIndexed { i, h ->
            val v = row.getOrElse(i) { "" }
            coerce(v, typeByName[h])
        }
    }
}
