package com.davidelang.remotetable

import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/**
 * Zoho Sheet API v2 grid backend (access token + workbook id).
 * [sheets] maps logical tab title → worksheet name (defaults to tab title).
 */
class ZohoSheetBackend(
    private val accessToken: String,
    private val workbookId: String,
    private val apiDomain: String = "https://sheet.zoho.com",
    private val sheets: Map<String, String> = emptyMap(),
) : Backend {
    override val backendId: String = BackendIds.ZOHO_SHEET

    private fun auth(): Map<String, String> =
        mapOf("Authorization" to "Zoho-oauthtoken $accessToken")

    private fun enc(name: String): String =
        URLEncoder.encode(name, StandardCharsets.UTF_8.name()).replace("+", "%20")

    private fun apiBase(): String = "${apiDomain.trimEnd('/')}/api/v2"

    private fun worksheetName(tab: String): String =
        sheets[tab]?.trim()?.takeIf { it.isNotBlank() } ?: tab

    override fun testConnection(): Map<String, Any?> {
        if (accessToken.isBlank() || workbookId.isBlank()) {
            return mapOf("ok" to false, "message" to "missing access_token or workbook_id", "code" to "auth")
        }
        return try {
            listTabs()
            mapOf("ok" to true, "message" to "zoho workbook ok")
        } catch (e: Exception) {
            mapOf("ok" to false, "message" to (e.message?.take(200) ?: "error"), "code" to "network")
        }
    }

    override fun listTabs(): List<String> {
        if (sheets.isNotEmpty()) return sheets.keys.sorted()
        val url = "${apiBase()}/$workbookId/worksheets"
        val (_, text) = HttpJson.request("GET", url, auth())
        val json = JSONObject(text)
        val worksheets = json.optJSONArray("worksheets")
            ?: json.optJSONObject("worksheet_details")?.let { JSONArray().put(it) }
            ?: JSONArray()
        val out = mutableListOf<String>()
        for (i in 0 until worksheets.length()) {
            val item = worksheets.optJSONObject(i) ?: continue
            val name = item.optString("worksheet_name", item.optString("name", "")).trim()
            if (name.isNotBlank()) out.add(name)
        }
        return out
    }

    override fun ensureTab(tab: String) {
        val name = worksheetName(tab)
        if (name in listTabs()) return
        val body = JSONObject().put("worksheet_name", name)
        HttpJson.request("POST", "${apiBase()}/$workbookId/worksheets", auth(), body.toString())
    }

    override fun ensureHeaders(tab: String, headers: List<String>): List<String> {
        ensureTab(tab)
        val cur = readRows(tab)
        if (cur.headers.isEmpty()) {
            writeGrid(tab, listOf(headers))
            return headers
        }
        val merged = cur.headers.toMutableList()
        for (h in headers) if (h !in merged) merged.add(h)
        if (merged != cur.headers) {
            val padded = cur.rows.map { row ->
                List(merged.size) { i -> row.getOrElse(i) { "" } }
            }
            writeGrid(tab, listOf(merged) + padded)
        }
        return merged
    }

    override fun readRows(tab: String): TabData {
        val name = worksheetName(tab)
        val url = "${apiBase()}/$workbookId/worksheets/${enc(name)}/cells"
        val (_, text) = HttpJson.request("GET", url, auth())
        val grid = parseCells(text)
        if (grid.isEmpty()) return TabData(emptyList(), emptyList())
        val headers = grid.first()
        val rows = grid.drop(1)
        return TabData(headers, rows)
    }

    override fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int {
        ensureHeaders(tab, headers)
        val cur = readRows(tab)
        val h = cur.headers.ifEmpty { headers }
        val newRows = if (mode == "replace") {
            rows.map { pad(it, h.size) }
        } else {
            cur.rows.map { pad(it, h.size) } + rows.map { pad(it, h.size) }
        }
        writeGrid(tab, listOf(h) + newRows)
        return rows.size
    }

    override fun renameTab(oldTitle: String, newTitle: String): Boolean {
        if (oldTitle == newTitle) return true
        val oldName = worksheetName(oldTitle)
        val newName = worksheetName(newTitle)
        val existing = listTabs()
        if (oldName !in existing) return newName in existing
        if (newName in existing) return false
        val body = JSONObject().put("worksheet_name", newName)
        return try {
            HttpJson.request("PUT", "${apiBase()}/$workbookId/worksheets/${enc(oldName)}", auth(), body.toString())
            true
        } catch (_: Exception) {
            false
        }
    }

    override fun deleteTab(tab: String) {
        val name = worksheetName(tab)
        try {
            HttpJson.request("DELETE", "${apiBase()}/$workbookId/worksheets/${enc(name)}", auth())
        } catch (e: RuntimeException) {
            if (e.message?.contains("HTTP 404") == true) return
            throw e
        }
    }

    private fun writeGrid(tab: String, grid: List<List<String>>) {
        val name = worksheetName(tab)
        val data = JSONArray()
        grid.forEachIndexed { rowIndex, row ->
            row.forEachIndexed { colIndex, value ->
                data.put(
                    JSONObject()
                        .put("row", rowIndex + 1)
                        .put("column", colIndex + 1)
                        .put("value", value),
                )
            }
        }
        val body = JSONObject().put("cells", data)
        HttpJson.request(
            "POST",
            "${apiBase()}/$workbookId/worksheets/${enc(name)}/cells",
            auth(),
            body.toString(),
        )
    }

    private fun parseCells(body: String): List<List<String>> {
        if (body.isBlank()) return emptyList()
        val json = JSONObject(body)
        val cells = json.optJSONArray("cells") ?: json.optJSONArray("range_details") ?: return emptyList()
        val sparse = mutableMapOf<Pair<Int, Int>, String>()
        var maxRow = 0
        var maxCol = 0
        for (i in 0 until cells.length()) {
            val cell = cells.optJSONObject(i) ?: continue
            val row = cell.optInt("row", cell.optInt("row_index", 0))
            val col = cell.optInt("column", cell.optInt("column_index", 0))
            if (row <= 0 || col <= 0) continue
            val value = cell.optString("value", cell.optString("display_value", ""))
            sparse[row to col] = value
            maxRow = maxOf(maxRow, row)
            maxCol = maxOf(maxCol, col)
        }
        if (maxRow == 0 || maxCol == 0) return emptyList()
        return (1..maxRow).map { r ->
            (1..maxCol).map { c -> sparse[r to c].orEmpty() }
        }
    }

    private fun pad(row: List<String>, n: Int): List<String> =
        List(n) { i -> row.getOrElse(i) { "" } }
}
