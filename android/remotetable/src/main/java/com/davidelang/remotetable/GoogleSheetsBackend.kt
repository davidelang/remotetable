package com.davidelang.remotetable

import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/**
 * Google Sheets API v4 via access token (no client library).
 * L0: paced HTTP, metadata cache, batchGet bulk read, range update / append / clear trailing.
 */
class GoogleSheetsBackend(
    private val accessToken: String,
    private val spreadsheetId: String,
    rateLimitConfig: RateLimitConfig = RateLimitRegistry.defaultFor(BackendIds.GOOGLE_SHEETS),
    progress: RateLimitProgress? = null,
) : Backend {
    override val backendId: String = BackendIds.GOOGLE_SHEETS
    private val api = "https://sheets.googleapis.com/v4/spreadsheets"
    private val limiter = RateLimiter(rateLimitConfig, progress)

    /** Cached tab titles + sheetIds; invalidated on structural changes. */
    private var metaCache: List<Pair<String, Int>>? = null

    fun setProgress(progress: RateLimitProgress?) {
        limiter.setProgress(progress)
    }

    private fun headers(): Map<String, String> = mapOf(
        "Authorization" to "Bearer $accessToken",
        "Content-Type" to "application/json",
    )

    private fun enc(s: String): String =
        URLEncoder.encode(s, StandardCharsets.UTF_8.name()).replace("+", "%20")

    private fun getJson(url: String): JSONObject = HttpJson.getJson(url, headers(), limiter)
    private fun putJson(url: String, body: JSONObject): JSONObject =
        HttpJson.putJson(url, headers(), body, limiter)
    private fun postJson(url: String, body: JSONObject): JSONObject =
        HttpJson.postJson(url, headers(), body, limiter)

    private fun loadMeta(force: Boolean = false): List<Pair<String, Int>> {
        if (!force) metaCache?.let { return it }
        val url = "$api/$spreadsheetId?fields=sheets.properties(sheetId,title)"
        val meta = getJson(url)
        val sheets = meta.optJSONArray("sheets") ?: JSONArray()
        val out = mutableListOf<Pair<String, Int>>()
        for (i in 0 until sheets.length()) {
            val p = sheets.optJSONObject(i)?.optJSONObject("properties") ?: continue
            val t = p.optString("title")
            if (t.isNotBlank()) out.add(t to p.optInt("sheetId"))
        }
        metaCache = out
        return out
    }

    private fun invalidateMeta() {
        metaCache = null
    }

    override fun testConnection(): Map<String, Any?> {
        if (accessToken.isBlank() || spreadsheetId.isBlank()) {
            return mapOf("ok" to false, "message" to "missing access_token or spreadsheet_id", "code" to "auth")
        }
        return try {
            val url = "$api/$spreadsheetId?fields=properties.title"
            val meta = getJson(url)
            val title = meta.optJSONObject("properties")?.optString("title").orEmpty()
            mapOf("ok" to true, "message" to "spreadsheet ok: $title")
        } catch (e: Exception) {
            mapOf("ok" to false, "message" to (e.message?.take(200) ?: "error"), "code" to "network")
        }
    }

    override fun listTabs(): List<String> = loadMeta().map { it.first }

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
        postJson("$api/$spreadsheetId:batchUpdate", body)
        invalidateMeta()
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
        val url = "$api/$spreadsheetId/values/${enc("'$tab'!A:ZZ")}"
        val data = getJson(url)
        return HttpJson.parseGrid(data.optJSONArray("values"))
    }

    /**
     * Bulk read via values.batchGet (chunks of ≤40 ranges).
     * One paced HTTP call per chunk instead of N listTabs + N GETs.
     */
    override fun readMany(tabs: List<String>): Map<String, TabData> {
        val names = tabs.map { it.trim() }.filter { it.isNotEmpty() }.distinct()
        if (names.isEmpty()) return emptyMap()
        val out = LinkedHashMap<String, TabData>(names.size)
        val chunks = names.chunked(BATCH_GET_MAX_RANGES)
        for (chunk in chunks) {
            // values.batchGet: GET with repeated ranges (≤40 per call)
            val q = chunk.joinToString("&") { "ranges=${enc("'$it'!A:ZZ")}" }
            val getUrl = "$api/$spreadsheetId/values:batchGet?$q&majorDimension=ROWS"
            val data = getJson(getUrl)
            val valueRanges = data.optJSONArray("valueRanges") ?: JSONArray()
            for ((index, tabName) in chunk.withIndex()) {
                val vr = valueRanges.optJSONObject(index)
                val values = vr?.optJSONArray("values")
                out[tabName] = HttpJson.parseGrid(values)
            }
        }
        return out
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
        // append: use values:append (no full-tab rewrite)
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
        if (mapped.isNotEmpty()) appendValues(tab, mapped)
        return mapped.size
    }

    /** Point update starting at 1-based sheet row (1 = header). No full-tab rewrite. */
    override fun updateRangeRows(tab: String, startRow1Based: Int, rows: List<List<String>>): Int {
        if (rows.isEmpty()) return 0
        val start = startRow1Based.coerceAtLeast(1)
        updateRange(tab, "A$start", rows)
        return rows.size
    }

    /** values:append only — no full-tab read (caller ensures headers when needed). */
    override fun appendDataRows(tab: String, rows: List<List<String>>): Int {
        if (rows.isEmpty()) return 0
        ensureTab(tab)
        appendValues(tab, rows)
        return rows.size
    }

    override fun clearFromRow(tab: String, startRow1Based: Int) {
        if (startRow1Based < 1) return
        val rng = enc("'$tab'!A$startRow1Based:ZZ")
        val url = "$api/$spreadsheetId/values/$rng:clear"
        postJson(url, JSONObject())
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
        postJson("$api/$spreadsheetId:batchUpdate", body)
        invalidateMeta()
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
        postJson("$api/$spreadsheetId:batchUpdate", body)
        invalidateMeta()
    }

    /**
     * Expunge: delete matching **data** rows via deleteDimension (key absent).
     * Filter is AND equality on header names.
     */
    override fun expungeWhere(tab: String, filter: Map<String, String>): Int {
        if (filter.isEmpty()) return 0
        val data = readRows(tab)
        if (data.headers.isEmpty() || data.rows.isEmpty()) return 0
        val sheetId = sheetIdByTitle(tab) ?: return 0
        val idx = data.headers.withIndex().associate { it.value to it.index }
        // Collect 0-based data indices matching filter (sheet row = index + 2)
        val matchSheetRows = mutableListOf<Int>()
        data.rows.forEachIndexed { i, row ->
            if (RowOps.matchesFilter(row, idx, filter)) {
                matchSheetRows.add(i + 2)
            }
        }
        if (matchSheetRows.isEmpty()) return 0
        // Delete from bottom so indices stay valid
        matchSheetRows.sortDescending()
        val requests = JSONArray()
        for (sheetRow in matchSheetRows) {
            // sheetRow is 1-based inclusive; grid range startIndex is 0-based exclusive end
            val startIndex = sheetRow - 1
            val endIndex = sheetRow
            requests.put(
                JSONObject().put(
                    "deleteDimension",
                    JSONObject()
                        .put(
                            "range",
                            JSONObject()
                                .put("sheetId", sheetId)
                                .put("dimension", "ROWS")
                                .put("startIndex", startIndex)
                                .put("endIndex", endIndex),
                        ),
                ),
            )
        }
        // batch in chunks of 50
        var deleted = 0
        val chunkSize = 50
        var i = 0
        while (i < requests.length()) {
            val chunk = JSONArray()
            val end = minOf(i + chunkSize, requests.length())
            for (j in i until end) chunk.put(requests.get(j))
            postJson(
                "$api/$spreadsheetId:batchUpdate",
                JSONObject().put("requests", chunk),
            )
            deleted += chunk.length()
            i = end
        }
        return deleted
    }

    private fun sheetIdByTitle(title: String): Int? =
        loadMeta().firstOrNull { it.first == title }?.second

    private fun updateRange(tab: String, a1: String, values: List<List<String>>) {
        val rng = enc("'$tab'!$a1")
        val url = "$api/$spreadsheetId/values/$rng?valueInputOption=RAW"
        val body = JSONObject().put("values", HttpJson.jsonArrayOfRows(values))
        putJson(url, body)
    }

    private fun appendValues(tab: String, values: List<List<String>>) {
        val rng = enc("'$tab'!A:ZZ")
        val url =
            "$api/$spreadsheetId/values/$rng:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
        val body = JSONObject().put("values", HttpJson.jsonArrayOfRows(values))
        postJson(url, body)
    }

    private fun clearTab(tab: String) {
        val url = "$api/$spreadsheetId/values/${enc("'$tab'")}:clear"
        postJson(url, JSONObject())
    }

    companion object {
        const val BATCH_GET_MAX_RANGES = 40
    }
}
