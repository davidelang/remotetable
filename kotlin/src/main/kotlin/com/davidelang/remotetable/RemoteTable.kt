package com.davidelang.remotetable

/** Provider-neutral remote table facade (M1). */
class RemoteTable(private val backend: Backend) {
    fun testConnection(): Map<String, Any?> = backend.testConnection()
    fun listTabs(): List<String> = backend.listTabs()
    fun ensureHeaders(tab: String, headers: List<String>): List<String> =
        backend.ensureHeaders(tab, headers)
    fun readRows(tab: String): TabData = backend.readRows(tab)
    fun writeRows(
        tab: String,
        headers: List<String>,
        rows: List<List<String>>,
        mode: String = "append",
    ): Int = backend.writeRows(tab, headers, rows, mode)
}

data class TabData(val headers: List<String>, val rows: List<List<String>>)

interface Backend {
    val backendId: String
    fun testConnection(): Map<String, Any?>
    fun listTabs(): List<String>
    fun ensureHeaders(tab: String, headers: List<String>): List<String>
    fun readRows(tab: String): TabData
    fun writeRows(
        tab: String,
        headers: List<String>,
        rows: List<List<String>>,
        mode: String,
    ): Int
}

/** In-memory multi-tab store for conformance. */
class MockBackend(
    initial: Map<String, TabData> = emptyMap(),
) : Backend {
    override val backendId: String = "mock"
    private val tabs = initial.mapValues { (_, v) ->
        TabData(v.headers.toList(), v.rows.map { it.toMutableList() }.toMutableList())
    }.toMutableMap()

    override fun testConnection(): Map<String, Any?> =
        mapOf("ok" to true, "message" to "mock")

    override fun listTabs(): List<String> = tabs.keys.sorted()

    override fun ensureHeaders(tab: String, headers: List<String>): List<String> {
        val cur = tabs[tab]
        if (cur == null) {
            tabs[tab] = TabData(headers.toList(), mutableListOf())
            return headers
        }
        val h = cur.headers.toMutableList()
        val rows = cur.rows.map { it.toMutableList() }.toMutableList()
        for (name in headers) {
            if (name !in h) {
                h.add(name)
                rows.forEach { it.add("") }
            }
        }
        tabs[tab] = TabData(h, rows)
        return h
    }

    override fun readRows(tab: String): TabData =
        tabs[tab] ?: TabData(emptyList(), emptyList())

    override fun writeRows(
        tab: String,
        headers: List<String>,
        rows: List<List<String>>,
        mode: String,
    ): Int {
        ensureHeaders(tab, headers)
        val cur = tabs[tab]!!
        val newRows = if (mode == "replace") {
            rows.map { it.toMutableList() }.toMutableList()
        } else {
            (cur.rows.map { it.toMutableList() } + rows.map { it.toMutableList() }).toMutableList()
        }
        tabs[tab] = TabData(cur.headers, newRows)
        return rows.size
    }
}

/** M1 required live backend ids (stubs until network clients land). */
object BackendIds {
    const val GOOGLE_SHEETS = "google-sheets"
    const val EXCEL_GRAPH = "excel-graph"
    const val ETHERCALC = "ethercalc"
}
