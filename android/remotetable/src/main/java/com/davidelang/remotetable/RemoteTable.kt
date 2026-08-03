package com.davidelang.remotetable

import org.json.JSONObject

/**
 * Provider-neutral remote table facade (M2).
 * Live backends use HttpURLConnection + JSON token/config (no Google/MS client libs).
 */
class RemoteTable(private val backend: Backend) {
    val backendId: String get() = backend.backendId

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

    /** Extended ops (best-effort; may be no-op / false for some backends). */
    fun ensureTab(tab: String) = backend.ensureTab(tab)
    fun renameTab(oldTitle: String, newTitle: String): Boolean = backend.renameTab(oldTitle, newTitle)
    fun deleteTab(tab: String) = backend.deleteTab(tab)
    fun clearFromRow(tab: String, startRow1Based: Int) = backend.clearFromRow(tab, startRow1Based)
}

data class TabData(val headers: List<String>, val rows: List<List<String>>) {
    /** Header + data as sheet grid. */
    fun asGrid(): List<List<String>> =
        if (headers.isEmpty() && rows.isEmpty()) emptyList()
        else listOf(headers) + rows
}

interface Backend {
    val backendId: String
    fun testConnection(): Map<String, Any?>
    fun listTabs(): List<String>
    fun ensureHeaders(tab: String, headers: List<String>): List<String>
    fun readRows(tab: String): TabData
    fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int
    fun ensureTab(tab: String) {}
    fun renameTab(oldTitle: String, newTitle: String): Boolean = false
    fun deleteTab(tab: String) {}
    fun clearFromRow(tab: String, startRow1Based: Int) {
        val data = readRows(tab)
        if (data.headers.isEmpty() && data.rows.isEmpty()) return
        val keep = (startRow1Based - 2).coerceAtLeast(0)
        writeRows(tab, data.headers, data.rows.take(keep), mode = "replace")
    }
}

object BackendIds {
    const val MOCK = "mock"
    const val GOOGLE_SHEETS = "google-sheets"
    const val EXCEL_GRAPH = "excel-graph"
    const val ETHERCALC = "ethercalc"
    const val BASEROW = "baserow"
    const val NOCODB = "nocodb"
    const val POCKETBASE = "pocketbase"
    const val SUPABASE = "supabase"
    const val AIRTABLE = "airtable"
    const val FIREBASE = "firebase"
    const val ZOHO_SHEET = "zoho-sheet"
    const val ONLYOFFICE = "onlyoffice"
    const val COLLABORA = "collabora"
    val ROW_DB = listOf(BASEROW, NOCODB, POCKETBASE, SUPABASE, AIRTABLE, FIREBASE)
    val LIVE = listOf(GOOGLE_SHEETS, EXCEL_GRAPH, ETHERCALC, ZOHO_SHEET) + ROW_DB
}

/** Factory for backends from config maps (token strings, not only files). */
object Backends {
    fun mock(initial: Map<String, TabData> = emptyMap()): Backend = MockBackend(initial)

    fun googleSheets(accessToken: String, spreadsheetId: String): Backend =
        GoogleSheetsBackend(accessToken, spreadsheetId)

    fun excelGraph(accessToken: String, itemId: String, driveId: String? = null): Backend =
        ExcelGraphBackend(accessToken, itemId, driveId)

    fun ethercalc(baseUrl: String, room: String = "sheet", auth: String? = null): Backend =
        EtherCalcBackend(baseUrl, room, auth)

    fun rowDb(
        kind: String,
        baseUrl: String,
        token: String,
        tables: Map<String, String>,
        baseId: String = "",
    ): Backend = RowDbBackend(kind, baseUrl, token, tables, baseId)

    fun baserow(baseUrl: String, token: String, tables: Map<String, String>): Backend =
        rowDb(BackendIds.BASEROW, baseUrl, token, tables)

    fun nocodb(baseUrl: String, token: String, tables: Map<String, String>): Backend =
        rowDb(BackendIds.NOCODB, baseUrl, token, tables)

    fun pocketbase(baseUrl: String, token: String, tables: Map<String, String>): Backend =
        rowDb(BackendIds.POCKETBASE, baseUrl, token, tables)

    fun supabase(baseUrl: String, token: String, tables: Map<String, String>): Backend =
        rowDb(BackendIds.SUPABASE, baseUrl, token, tables)

    fun airtable(token: String, baseId: String, tables: Map<String, String>): Backend =
        rowDb(BackendIds.AIRTABLE, "https://api.airtable.com", token, tables, baseId)

    fun firebase(projectId: String, token: String, tables: Map<String, String>): Backend {
        val base = "https://firestore.googleapis.com/v1/projects/$projectId/databases/(default)/documents"
        return rowDb(BackendIds.FIREBASE, base, token, tables)
    }

    fun zohoSheet(
        accessToken: String,
        workbookId: String,
        apiDomain: String = "https://sheet.zoho.com",
        sheets: Map<String, String> = emptyMap(),
    ): Backend = ZohoSheetBackend(accessToken, workbookId, apiDomain, sheets)

    fun onlyOffice(message: String = "OnlyOffice headless backend deferred"): Backend =
        DeferredBackend(BackendIds.ONLYOFFICE, message)

    fun collabora(message: String = "Collabora headless backend deferred"): Backend =
        DeferredBackend(BackendIds.COLLABORA, message)

    fun fromConfig(backendId: String, config: Map<String, String>): Backend = when (backendId) {
        BackendIds.MOCK -> mock()
        BackendIds.GOOGLE_SHEETS -> googleSheets(
            config["access_token"] ?: config["token"] ?: "",
            config["spreadsheet_id"] ?: "",
        )
        BackendIds.EXCEL_GRAPH -> excelGraph(
            config["access_token"] ?: config["token"] ?: "",
            config["item_id"] ?: "",
            config["drive_id"],
        )
        BackendIds.ETHERCALC -> ethercalc(
            config["base_url"] ?: "",
            config["room"] ?: "sheet",
            config["auth"] ?: config["access_token"],
        )
        BackendIds.BASEROW, BackendIds.NOCODB, BackendIds.POCKETBASE, BackendIds.SUPABASE, BackendIds.AIRTABLE,
        BackendIds.FIREBASE,
        -> {
            val tablesJson = config["tables_json"] ?: config["tables"] ?: "{}"
            val tables = parseTablesMap(tablesJson)
            val base = when {
                backendId == BackendIds.FIREBASE && config["project_id"].orEmpty().isNotBlank() ->
                    "https://firestore.googleapis.com/v1/projects/${config["project_id"]}/databases/(default)/documents"
                else -> config["base_url"] ?: ""
            }
            rowDb(
                backendId,
                base,
                config["access_token"] ?: config["token"] ?: "",
                tables,
                config["base_id"] ?: "",
            )
        }
        BackendIds.ZOHO_SHEET, "zoho_sheet", "zoho" -> zohoSheet(
            config["access_token"] ?: config["token"] ?: "",
            config["workbook_id"] ?: config["item_id"] ?: "",
            config["api_domain"] ?: "https://sheet.zoho.com",
            parseTablesMap(config["sheets_json"] ?: config["tables_json"] ?: config["tables"] ?: "{}"),
        )
        BackendIds.ONLYOFFICE -> onlyOffice()
        BackendIds.COLLABORA -> collabora()
        else -> throw IllegalArgumentException("unknown backend: $backendId")
    }

    private fun parseTablesMap(raw: String): Map<String, String> {
        if (raw.isBlank()) return emptyMap()
        return try {
            val obj = JSONObject(raw)
            val out = mutableMapOf<String, String>()
            val keys = obj.keys()
            while (keys.hasNext()) {
                val k = keys.next()
                out[k] = obj.opt(k)?.toString().orEmpty()
            }
            out.filterValues { it.isNotBlank() }
        } catch (_: Exception) {
            emptyMap()
        }
    }
}


class MockBackend(initial: Map<String, TabData> = emptyMap()) : Backend {
    override val backendId: String = BackendIds.MOCK
    private val tabs = initial.mapValues { (_, v) ->
        TabData(v.headers.toList(), v.rows.map { it.toMutableList() }.toMutableList())
    }.toMutableMap()

    override fun testConnection(): Map<String, Any?> = mapOf("ok" to true, "message" to "mock")
    override fun listTabs(): List<String> = tabs.keys.sorted()
    override fun ensureTab(tab: String) {
        if (tab !in tabs) tabs[tab] = TabData(emptyList(), mutableListOf())
    }

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

    override fun readRows(tab: String): TabData = tabs[tab] ?: TabData(emptyList(), emptyList())

    override fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int {
        ensureHeaders(tab, headers)
        val cur = tabs[tab]!!
        val newRows = if (mode == "replace") {
            rows.map { pad(it, cur.headers.size) }.toMutableList()
        } else {
            (cur.rows.map { it.toMutableList() } + rows.map { pad(it, cur.headers.size) }).toMutableList()
        }
        tabs[tab] = TabData(cur.headers, newRows)
        return rows.size
    }

    override fun renameTab(oldTitle: String, newTitle: String): Boolean {
        if (oldTitle == newTitle) return true
        val data = tabs.remove(oldTitle) ?: return newTitle in tabs
        if (newTitle in tabs) return false
        tabs[newTitle] = data
        return true
    }

    override fun deleteTab(tab: String) {
        tabs.remove(tab)
    }

    private fun pad(row: List<String>, width: Int): MutableList<String> {
        val m = row.toMutableList()
        while (m.size < width) m.add("")
        return m
    }
}
