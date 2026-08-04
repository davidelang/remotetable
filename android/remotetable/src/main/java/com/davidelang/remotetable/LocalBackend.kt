package com.davidelang.remotetable

/**
 * Explicit multi-tab in-memory book (`local` / `memory`).
 * Same grid ops as [MockBackend]; distinct backend id for config/factory.
 */
class LocalBackend(initial: Map<String, TabData> = emptyMap()) : Backend {
    override val backendId: String = BackendIds.LOCAL
    private val mem = MockBackend(initial)

    override fun testConnection(): Map<String, Any?> =
        mapOf("ok" to true, "message" to "local memory tabs=${listTabs().size}")

    override fun listTabs(): List<String> = mem.listTabs()
    override fun ensureHeaders(tab: String, headers: List<String>): List<String> =
        mem.ensureHeaders(tab, headers)
    override fun readRows(tab: String): TabData = mem.readRows(tab)
    override fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int =
        mem.writeRows(tab, headers, rows, mode)
    override fun ensureTab(tab: String) = mem.ensureTab(tab)
    override fun renameTab(oldTitle: String, newTitle: String): Boolean = mem.renameTab(oldTitle, newTitle)
    override fun deleteTab(tab: String) = mem.deleteTab(tab)
    override fun clearFromRow(tab: String, startRow1Based: Int) = mem.clearFromRow(tab, startRow1Based)
    override fun readMany(tabs: List<String>): Map<String, TabData> = mem.readMany(tabs)
    override fun writeMany(updates: Map<String, TabWrite>, mode: String): Int = mem.writeMany(updates, mode)
    override fun updateWhere(tab: String, filter: Map<String, String>, setFields: Map<String, String>): Int =
        mem.updateWhere(tab, filter, setFields)
    override fun softDeleteWhere(
        tab: String,
        filter: Map<String, String>,
        tombstoneColumn: String,
        trueValue: String,
    ): Int = mem.softDeleteWhere(tab, filter, tombstoneColumn, trueValue)
    override fun expungeWhere(tab: String, filter: Map<String, String>): Int = mem.expungeWhere(tab, filter)

    fun snapshot(): Map<String, TabData> =
        listTabs().associateWith { readRows(it) }
}
