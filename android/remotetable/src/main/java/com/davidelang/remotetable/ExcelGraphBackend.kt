package com.davidelang.remotetable

import org.json.JSONObject
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/** Microsoft Graph Excel Online workbook API. */
class ExcelGraphBackend(
    private val accessToken: String,
    private val itemId: String,
    private val driveId: String? = null,
) : Backend {
    override val backendId: String = BackendIds.EXCEL_GRAPH
    private val graph = "https://graph.microsoft.com/v1.0"

    private fun root(): String =
        if (!driveId.isNullOrBlank()) {
            "$graph/drives/$driveId/items/$itemId/workbook"
        } else {
            "$graph/me/drive/items/$itemId/workbook"
        }

    private fun headers(): Map<String, String> = mapOf(
        "Authorization" to "Bearer $accessToken",
        "Content-Type" to "application/json",
    )

    private fun encSheet(name: String): String =
        URLEncoder.encode(name, StandardCharsets.UTF_8.name()).replace("+", "%20")

    override fun testConnection(): Map<String, Any?> {
        if (accessToken.isBlank() || itemId.isBlank()) {
            return mapOf("ok" to false, "message" to "missing access_token or item_id", "code" to "auth")
        }
        return try {
            val data = HttpJson.getJson("${root()}/worksheets", headers())
            val n = data.optJSONArray("value")?.length() ?: 0
            mapOf("ok" to true, "message" to "workbook ok sheets=$n")
        } catch (e: Exception) {
            mapOf("ok" to false, "message" to (e.message?.take(200) ?: "error"), "code" to "network")
        }
    }

    override fun listTabs(): List<String> {
        val data = HttpJson.getJson("${root()}/worksheets", headers())
        val arr = data.optJSONArray("value") ?: return emptyList()
        val out = mutableListOf<String>()
        for (i in 0 until arr.length()) {
            val n = arr.optJSONObject(i)?.optString("name").orEmpty()
            if (n.isNotBlank()) out.add(n)
        }
        return out
    }

    override fun ensureTab(tab: String) {
        if (tab in listTabs()) return
        HttpJson.postJson(
            "${root()}/worksheets/add",
            headers(),
            JSONObject().put("name", tab),
        )
    }

    override fun ensureHeaders(tab: String, headers: List<String>): List<String> {
        ensureTab(tab)
        val cur = readRows(tab)
        if (cur.headers.isEmpty()) {
            writeRange(tab, "A1", listOf(headers))
            return headers
        }
        val newH = cur.headers.toMutableList()
        for (h in headers) if (h !in newH) newH.add(h)
        if (newH != cur.headers) writeRange(tab, "A1", listOf(newH))
        return newH
    }

    override fun readRows(tab: String): TabData {
        val name = encSheet(tab)
        val data = HttpJson.getJson("${root()}/worksheets('$name')/usedRange", headers())
        val values = data.optJSONArray("values") ?: return TabData(emptyList(), emptyList())
        if (values.length() == 0) return TabData(emptyList(), emptyList())
        val headers = mutableListOf<String>()
        val first = values.optJSONArray(0) ?: return TabData(emptyList(), emptyList())
        for (i in 0 until first.length()) headers.add(first.optString(i, ""))
        val rows = mutableListOf<List<String>>()
        for (r in 1 until values.length()) {
            val rowArr = values.optJSONArray(r) ?: org.json.JSONArray()
            val row = MutableList(headers.size) { "" }
            for (c in 0 until minOf(rowArr.length(), headers.size)) {
                row[c] = rowArr.optString(c, "")
            }
            rows.add(row)
        }
        return TabData(headers, rows)
    }

    override fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int {
        ensureTab(tab)
        if (mode == "replace") {
            writeRange(tab, "A1", listOf(headers) + rows)
            return rows.size
        }
        val existing = readRows(tab)
        if (existing.headers.isEmpty()) {
            writeRange(tab, "A1", listOf(headers) + rows)
            return rows.size
        }
        val start = existing.rows.size + 2
        if (rows.isNotEmpty()) writeRange(tab, "A$start", rows)
        return rows.size
    }

    override fun renameTab(oldTitle: String, newTitle: String): Boolean {
        if (oldTitle == newTitle) return true
        val tabs = listTabs()
        if (oldTitle !in tabs) return newTitle in tabs
        if (newTitle in tabs) return false
        val name = encSheet(oldTitle)
        HttpJson.patchJson(
            "${root()}/worksheets('$name')",
            headers(),
            JSONObject().put("name", newTitle),
        )
        return true
    }

    override fun deleteTab(tab: String) {
        val name = encSheet(tab)
        HttpJson.request("DELETE", "${root()}/worksheets('$name')", headers())
    }

    private fun writeRange(tab: String, a1: String, values: List<List<String>>) {
        if (values.isEmpty()) return
        val name = encSheet(tab)
        val url = "${root()}/worksheets('$name')/range(address='$a1')"
        HttpJson.patchJson(url, headers(), JSONObject().put("values", HttpJson.jsonArrayOfRows(values)))
    }
}
