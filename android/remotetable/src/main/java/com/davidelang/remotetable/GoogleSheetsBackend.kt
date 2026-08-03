package com.davidelang.remotetable

import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/** Google Sheets API v4 via access token (no client library). */
class GoogleSheetsBackend(
    private val accessToken: String,
    private val spreadsheetId: String,
) : Backend {
    override val backendId: String = BackendIds.GOOGLE_SHEETS
    private val api = "https://sheets.googleapis.com/v4/spreadsheets"

    private fun headers(): Map<String, String> = mapOf(
        "Authorization" to "Bearer $accessToken",
        "Content-Type" to "application/json",
    )

    private fun enc(s: String): String =
        URLEncoder.encode(s, StandardCharsets.UTF_8.name()).replace("+", "%20")

    override fun testConnection(): Map<String, Any?> {
        if (accessToken.isBlank() || spreadsheetId.isBlank()) {
            return mapOf("ok" to false, "message" to "missing access_token or spreadsheet_id", "code" to "auth")
        }
        return try {
            val url = "$api/$spreadsheetId?fields=properties.title"
            val meta = HttpJson.getJson(url, headers())
            val title = meta.optJSONObject("properties")?.optString("title").orEmpty()
            mapOf("ok" to true, "message" to "spreadsheet ok: $title")
        } catch (e: Exception) {
            mapOf("ok" to false, "message" to (e.message?.take(200) ?: "error"), "code" to "network")
        }
    }

    override fun listTabs(): List<String> {
        val url = "$api/$spreadsheetId?fields=sheets.properties.title"
        val meta = HttpJson.getJson(url, headers())
        val sheets = meta.optJSONArray("sheets") ?: JSONArray()
        val out = mutableListOf<String>()
        for (i in 0 until sheets.length()) {
            val t = sheets.optJSONObject(i)?.optJSONObject("properties")?.optString("title")
            if (!t.isNullOrBlank()) out.add(t)
        }
        return out
    }

    override fun ensureTab(tab: String) {
        if (tab in listTabs()) return
        val body = JSONObject().put(
            "requests",
            JSONArray().put(
                JSONObject().put(
                    "addSheet",
                    JSONObject().put("properties", JSONObject().put("title", tab)),
                ),
            ),
        )
        HttpJson.postJson("$api/$spreadsheetId:batchUpdate", headers(), body)
    }

    override fun ensureHeaders(tab: String, headers: List<String>): List<String> {
        ensureTab(tab)
        val cur = readRows(tab)
        if (cur.headers.isEmpty()) {
            updateRange(tab, "A1", listOf(headers))
            return headers
        }
        val newH = cur.headers.toMutableList()
        for (h in headers) if (h !in newH) newH.add(h)
        if (newH != cur.headers) updateRange(tab, "A1", listOf(newH))
        return newH
    }

    override fun readRows(tab: String): TabData {
        val url = "$api/$spreadsheetId/values/${enc(tab)}"
        val data = HttpJson.getJson(url, headers())
        val values = data.optJSONArray("values") ?: return TabData(emptyList(), emptyList())
        if (values.length() == 0) return TabData(emptyList(), emptyList())
        val headers = mutableListOf<String>()
        val first = values.optJSONArray(0) ?: JSONArray()
        for (i in 0 until first.length()) headers.add(first.optString(i, ""))
        val rows = mutableListOf<List<String>>()
        for (r in 1 until values.length()) {
            val rowArr = values.optJSONArray(r) ?: JSONArray()
            val row = MutableList(headers.size) { "" }
            for (c in 0 until rowArr.length()) {
                if (c < row.size) row[c] = rowArr.optString(c, "")
                else {
                    headers.add("")
                    row.add(rowArr.optString(c, ""))
                    // expand previous rows
                    for (ri in rows.indices) {
                        rows[ri] = rows[ri] + listOf("")
                    }
                }
            }
            rows.add(row)
        }
        return TabData(headers, rows)
    }

    override fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int {
        ensureTab(tab)
        if (mode == "replace") {
            clearTab(tab)
            val body = listOf(headers) + rows
            if (body.any { it.isNotEmpty() } || headers.isNotEmpty()) {
                updateRange(tab, "A1", if (headers.isEmpty()) rows else body)
            }
            return rows.size
        }
        val existing = readRows(tab)
        if (existing.headers.isEmpty()) {
            updateRange(tab, "A1", listOf(headers) + rows)
            return rows.size
        }
        val idx = existing.headers.withIndex().associate { it.value to it.index }
        val mapped = rows.map { r ->
            val row = MutableList(existing.headers.size) { "" }
            headers.forEachIndexed { i, h ->
                val j = idx[h]
                if (j != null && i < r.size) row[j] = r[i]
            }
            row
        }
        val start = existing.rows.size + 2
        if (mapped.isNotEmpty()) updateRange(tab, "A$start", mapped)
        return mapped.size
    }

    override fun renameTab(oldTitle: String, newTitle: String): Boolean {
        if (oldTitle == newTitle) return true
        val sheetId = sheetIdByTitle(oldTitle) ?: return newTitle in listTabs()
        if (newTitle in listTabs()) return false
        val body = JSONObject().put(
            "requests",
            JSONArray().put(
                JSONObject().put(
                    "updateSheetProperties",
                    JSONObject()
                        .put("properties", JSONObject().put("sheetId", sheetId).put("title", newTitle))
                        .put("fields", "title"),
                ),
            ),
        )
        HttpJson.postJson("$api/$spreadsheetId:batchUpdate", headers(), body)
        return true
    }

    override fun deleteTab(tab: String) {
        val sheetId = sheetIdByTitle(tab) ?: return
        val body = JSONObject().put(
            "requests",
            JSONArray().put(
                JSONObject().put("deleteSheet", JSONObject().put("sheetId", sheetId)),
            ),
        )
        HttpJson.postJson("$api/$spreadsheetId:batchUpdate", headers(), body)
    }

    private fun sheetIdByTitle(title: String): Int? {
        val url = "$api/$spreadsheetId?fields=sheets.properties(sheetId,title)"
        val meta = HttpJson.getJson(url, headers())
        val sheets = meta.optJSONArray("sheets") ?: return null
        for (i in 0 until sheets.length()) {
            val p = sheets.optJSONObject(i)?.optJSONObject("properties") ?: continue
            if (p.optString("title") == title) return p.optInt("sheetId")
        }
        return null
    }

    private fun updateRange(tab: String, a1: String, values: List<List<String>>) {
        val rng = enc("$tab!$a1")
        val url = "$api/$spreadsheetId/values/$rng?valueInputOption=RAW"
        val body = JSONObject().put("values", HttpJson.jsonArrayOfRows(values))
        HttpJson.putJson(url, headers(), body)
    }

    private fun clearTab(tab: String) {
        val url = "$api/$spreadsheetId/values/${enc(tab)}:clear"
        HttpJson.postJson(url, headers(), JSONObject())
    }
}
