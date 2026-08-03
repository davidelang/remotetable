package com.davidelang.remotetable

import org.json.JSONArray
import org.json.JSONObject

/**
 * Row-database Backend (Baserow, NocoDB, PocketBase, Supabase, Airtable).
 * Tables are pre-created remotely; [tables] maps tab title → remote table id.
 * Writes upsert by "Sync ID" when present.
 */
class RowDbBackend(
    private val kind: String,
    private val baseUrl: String,
    private val token: String,
    private val tables: Map<String, String>,
    private val baseId: String = "",
) : Backend {
    override val backendId: String = kind.lowercase()

    private val driver: RowDbDriver = when (backendId) {
        BackendIds.BASEROW -> BaserowDriver()
        BackendIds.NOCODB -> NocoDbDriver()
        BackendIds.POCKETBASE -> PocketBaseDriver()
        BackendIds.SUPABASE -> SupabaseDriver()
        BackendIds.AIRTABLE -> AirtableDriver()
        else -> throw IllegalArgumentException("unknown rowdb kind: $kind")
    }

    private fun tableId(tab: String): String =
        tables[tab]?.trim()?.takeIf { it.isNotBlank() }
            ?: throw IllegalStateException("no table id mapped for tab \"$tab\"")

    override fun testConnection(): Map<String, Any?> {
        if (token.isBlank()) return mapOf("ok" to false, "message" to "missing token", "code" to "auth")
        if (tables.isEmpty()) return mapOf("ok" to false, "message" to "no tables mapped", "code" to "config")
        return try {
            val tab = tables.keys.first()
            driver.listFieldMaps(this, tableId(tab))
            mapOf("ok" to true, "message" to "$backendId ok")
        } catch (e: Exception) {
            mapOf("ok" to false, "message" to (e.message?.take(200) ?: "error"), "code" to "network")
        }
    }

    override fun listTabs(): List<String> = tables.keys.sorted()

    override fun ensureHeaders(tab: String, headers: List<String>): List<String> {
        driver.listFieldMaps(this, tableId(tab))
        return headers
    }

    override fun readRows(tab: String): TabData {
        val remote = driver.listFieldMaps(this, tableId(tab))
        if (remote.isEmpty()) return TabData(emptyList(), emptyList())
        val keys = linkedSetOf<String>()
        remote.forEach { (_, fields) -> keys.addAll(fields.keys) }
        val headers = mutableListOf<String>()
        if (SYNC_ID in keys) {
            headers.add(SYNC_ID)
            keys.remove(SYNC_ID)
        }
        headers.addAll(keys)
        val rows = remote.map { (_, fields) -> headers.map { fields[it].orEmpty() } }
        return TabData(headers, rows)
    }

    override fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int {
        val tid = tableId(tab)
        val remote = driver.listFieldMaps(this, tid)
        val bySync = remote.mapNotNull { (rid, fields) ->
            fields[SYNC_ID]?.trim()?.takeIf { it.isNotEmpty() }?.let { it to rid }
        }.toMap().toMutableMap()
        val syncIdx = headers.indexOf(SYNC_ID)
        val keep = mutableSetOf<String>()
        for (row in rows) {
            val padded = headers.indices.map { i -> row.getOrElse(i) { "" } }
            val sync = if (syncIdx >= 0) padded[syncIdx].trim() else ""
            if (sync.isNotEmpty()) keep.add(sync)
            val existing = if (sync.isNotEmpty()) bySync[sync] else null
            if (existing != null) {
                driver.updateRow(this, tid, existing, headers, padded)
            } else {
                val rid = driver.createRow(this, tid, headers, padded)
                if (sync.isNotEmpty()) bySync[sync] = rid
            }
        }
        if (mode == "replace") {
            remote.forEach { (rid, fields) ->
                val sid = fields[SYNC_ID]?.trim().orEmpty()
                if (sid.isNotEmpty() && sid !in keep) driver.deleteRow(this, tid, rid)
            }
        }
        return rows.size
    }

    internal fun authToken(): String = token
    internal fun base(): String = baseUrl.trimEnd('/')
    internal fun airtableBaseId(): String = baseId

    companion object {
        const val SYNC_ID = "Sync ID"
    }
}

internal interface RowDbDriver {
    fun listFieldMaps(be: RowDbBackend, tableId: String): List<Pair<String, Map<String, String>>>
    fun createRow(be: RowDbBackend, tableId: String, headers: List<String>, row: List<String>): String
    fun updateRow(be: RowDbBackend, tableId: String, rowId: String, headers: List<String>, row: List<String>)
    fun deleteRow(be: RowDbBackend, tableId: String, rowId: String)
}

internal class BaserowDriver : RowDbDriver {
    private fun auth(be: RowDbBackend) = mapOf("Authorization" to "Token ${be.authToken()}")
    private fun url(be: RowDbBackend, tableId: String, rowId: String? = null): String {
        val base = "${be.base()}/api/database/rows/table/$tableId/"
        return if (rowId != null) "${base.trimEnd('/')}/$rowId/?user_field_names=true"
        else "${base}?user_field_names=true"
    }

    override fun listFieldMaps(be: RowDbBackend, tableId: String): List<Pair<String, Map<String, String>>> {
        val out = mutableListOf<Pair<String, Map<String, String>>>()
        var page = 1
        while (true) {
            val (_, text) = HttpJson.request("GET", "${url(be, tableId)}&page=$page&size=200", auth(be))
            val json = JSONObject(text)
            val results = json.optJSONArray("results") ?: break
            if (results.length() == 0) break
            for (i in 0 until results.length()) {
                val row = results.optJSONObject(i) ?: continue
                val rid = row.opt("id")?.toString().orEmpty()
                if (rid.isBlank()) continue
                val fields = mutableMapOf<String, String>()
                row.keys().forEach { key ->
                    if (key != "id" && key != "order") fields[key] = row.opt(key)?.toString().orEmpty()
                }
                out.add(rid to fields)
            }
            if (json.optString("next").isBlank()) break
            page++
        }
        return out
    }

    override fun createRow(be: RowDbBackend, tableId: String, headers: List<String>, row: List<String>): String {
        val body = JSONObject()
        headers.forEachIndexed { i, h -> body.put(h, row.getOrElse(i) { "" }) }
        val (_, text) = HttpJson.request("POST", url(be, tableId), auth(be), body.toString())
        return JSONObject(text).opt("id")?.toString().orEmpty()
    }

    override fun updateRow(be: RowDbBackend, tableId: String, rowId: String, headers: List<String>, row: List<String>) {
        val body = JSONObject()
        headers.forEachIndexed { i, h -> body.put(h, row.getOrElse(i) { "" }) }
        HttpJson.request("PATCH", url(be, tableId, rowId), auth(be), body.toString())
    }

    override fun deleteRow(be: RowDbBackend, tableId: String, rowId: String) {
        try {
            HttpJson.request("DELETE", url(be, tableId, rowId), auth(be))
        } catch (e: RuntimeException) {
            if (e.message?.contains("HTTP 204") != true) throw e
        }
    }
}

internal class NocoDbDriver : RowDbDriver {
    private fun auth(be: RowDbBackend) = mapOf("xc-token" to be.authToken())
    private fun url(be: RowDbBackend, tableId: String) = "${be.base()}/api/v2/tables/$tableId/records"

    override fun listFieldMaps(be: RowDbBackend, tableId: String): List<Pair<String, Map<String, String>>> {
        val out = mutableListOf<Pair<String, Map<String, String>>>()
        var offset = 0
        val limit = 200
        while (true) {
            val (_, text) = HttpJson.request("GET", "${url(be, tableId)}?offset=$offset&limit=$limit", auth(be))
            val json = JSONObject(text)
            val list = json.optJSONArray("list") ?: break
            if (list.length() == 0) break
            for (i in 0 until list.length()) {
                val row = list.optJSONObject(i) ?: continue
                val rid = row.opt("Id")?.toString() ?: row.opt("id")?.toString() ?: continue
                val fields = mutableMapOf<String, String>()
                row.keys().forEach { key ->
                    if (!key.equals("Id", true) && key != "id") fields[key] = row.opt(key)?.toString().orEmpty()
                }
                out.add(rid to fields)
            }
            val last = json.optJSONObject("pageInfo")?.optBoolean("isLastPage", true) ?: true
            if (last) break
            offset += limit
        }
        return out
    }

    override fun createRow(be: RowDbBackend, tableId: String, headers: List<String>, row: List<String>): String {
        val body = JSONObject()
        headers.forEachIndexed { i, h -> body.put(h, row.getOrElse(i) { "" }) }
        val (_, text) = HttpJson.request("POST", url(be, tableId), auth(be), body.toString())
        val json = JSONObject(text)
        return json.opt("Id")?.toString() ?: json.opt("id")?.toString().orEmpty()
    }

    override fun updateRow(be: RowDbBackend, tableId: String, rowId: String, headers: List<String>, row: List<String>) {
        val body = JSONObject().put("Id", rowId.toLongOrNull() ?: rowId)
        headers.forEachIndexed { i, h -> body.put(h, row.getOrElse(i) { "" }) }
        HttpJson.request("PATCH", url(be, tableId), auth(be), body.toString())
    }

    override fun deleteRow(be: RowDbBackend, tableId: String, rowId: String) {
        val idValue: Any = rowId.toLongOrNull() ?: rowId
        val body = JSONArray().put(JSONObject().put("Id", idValue)).toString()
        try {
            HttpJson.request("DELETE", url(be, tableId), auth(be), body)
        } catch (e: RuntimeException) {
            if (e.message?.contains("HTTP 204") != true) throw e
        }
    }
}

internal class PocketBaseDriver : RowDbDriver {
    private fun auth(be: RowDbBackend) = mapOf("Authorization" to "Bearer ${be.authToken()}")
    private fun url(be: RowDbBackend, tableId: String, rowId: String? = null): String {
        val base = "${be.base()}/api/collections/$tableId/records"
        return if (rowId != null) "$base/$rowId" else base
    }

    override fun listFieldMaps(be: RowDbBackend, tableId: String): List<Pair<String, Map<String, String>>> {
        val out = mutableListOf<Pair<String, Map<String, String>>>()
        var page = 1
        while (true) {
            val (_, text) = HttpJson.request("GET", "${url(be, tableId)}?page=$page&perPage=200", auth(be))
            val json = JSONObject(text)
            val items = json.optJSONArray("items") ?: break
            if (items.length() == 0) break
            val skip = setOf("id", "collectionId", "collectionName", "created", "updated")
            for (i in 0 until items.length()) {
                val row = items.optJSONObject(i) ?: continue
                val rid = row.optString("id", "")
                if (rid.isBlank()) continue
                val fields = mutableMapOf<String, String>()
                row.keys().forEach { key ->
                    if (key !in skip) fields[key] = row.opt(key)?.toString().orEmpty()
                }
                out.add(rid to fields)
            }
            if (page >= json.optInt("totalPages", 1)) break
            page++
        }
        return out
    }

    override fun createRow(be: RowDbBackend, tableId: String, headers: List<String>, row: List<String>): String {
        val body = JSONObject()
        headers.forEachIndexed { i, h -> body.put(h, row.getOrElse(i) { "" }) }
        val (_, text) = HttpJson.request("POST", url(be, tableId), auth(be), body.toString())
        return JSONObject(text).optString("id", "")
    }

    override fun updateRow(be: RowDbBackend, tableId: String, rowId: String, headers: List<String>, row: List<String>) {
        val body = JSONObject()
        headers.forEachIndexed { i, h -> body.put(h, row.getOrElse(i) { "" }) }
        HttpJson.request("PATCH", url(be, tableId, rowId), auth(be), body.toString())
    }

    override fun deleteRow(be: RowDbBackend, tableId: String, rowId: String) {
        try {
            HttpJson.request("DELETE", url(be, tableId, rowId), auth(be))
        } catch (e: RuntimeException) {
            if (e.message?.contains("HTTP 204") != true) throw e
        }
    }
}

internal class SupabaseDriver : RowDbDriver {
    private fun auth(be: RowDbBackend) = mapOf(
        "apikey" to be.authToken(),
        "Authorization" to "Bearer ${be.authToken()}",
        "Prefer" to "return=representation",
    )

    private fun url(be: RowDbBackend, tableId: String, query: String = ""): String {
        val base = "${be.base()}/rest/v1/$tableId"
        return if (query.isBlank()) base else "$base?$query"
    }

    override fun listFieldMaps(be: RowDbBackend, tableId: String): List<Pair<String, Map<String, String>>> {
        val (_, text) = HttpJson.request("GET", url(be, tableId, "select=*"), auth(be))
        val arr = JSONArray(text)
        val out = mutableListOf<Pair<String, Map<String, String>>>()
        for (i in 0 until arr.length()) {
            val row = arr.optJSONObject(i) ?: continue
            val rid = row.opt("id")?.toString().orEmpty()
            if (rid.isBlank()) continue
            val fields = mutableMapOf<String, String>()
            row.keys().forEach { key ->
                if (key != "id") fields[key] = row.opt(key)?.toString().orEmpty()
            }
            out.add(rid to fields)
        }
        return out
    }

    override fun createRow(be: RowDbBackend, tableId: String, headers: List<String>, row: List<String>): String {
        val body = JSONObject()
        headers.forEachIndexed { i, h -> body.put(h, row.getOrElse(i) { "" }) }
        val (_, text) = HttpJson.request("POST", url(be, tableId), auth(be), body.toString())
        return try {
            val arr = JSONArray(text)
            arr.optJSONObject(0)?.opt("id")?.toString().orEmpty()
        } catch (_: Exception) {
            JSONObject(text).opt("id")?.toString().orEmpty()
        }
    }

    override fun updateRow(be: RowDbBackend, tableId: String, rowId: String, headers: List<String>, row: List<String>) {
        val body = JSONObject()
        headers.forEachIndexed { i, h -> body.put(h, row.getOrElse(i) { "" }) }
        HttpJson.request("PATCH", url(be, tableId, "id=eq.$rowId"), auth(be), body.toString())
    }

    override fun deleteRow(be: RowDbBackend, tableId: String, rowId: String) {
        try {
            HttpJson.request("DELETE", url(be, tableId, "id=eq.$rowId"), auth(be))
        } catch (e: RuntimeException) {
            if (e.message?.contains("HTTP 204") != true) throw e
        }
    }
}

internal class AirtableDriver : RowDbDriver {
    private fun auth(be: RowDbBackend) = mapOf("Authorization" to "Bearer ${be.authToken()}")
    private fun url(be: RowDbBackend, tableId: String, rowId: String? = null): String {
        val base = "https://api.airtable.com/v0/${be.airtableBaseId()}/$tableId"
        return if (rowId != null) "$base/$rowId" else base
    }

    override fun listFieldMaps(be: RowDbBackend, tableId: String): List<Pair<String, Map<String, String>>> {
        val out = mutableListOf<Pair<String, Map<String, String>>>()
        var offset: String? = null
        while (true) {
            val q = if (offset.isNullOrBlank()) "" else "?offset=$offset"
            val (_, text) = HttpJson.request("GET", url(be, tableId) + q, auth(be))
            val json = JSONObject(text)
            val records = json.optJSONArray("records") ?: break
            for (i in 0 until records.length()) {
                val rec = records.optJSONObject(i) ?: continue
                val rid = rec.optString("id", "")
                val fieldsObj = rec.optJSONObject("fields") ?: continue
                val fields = mutableMapOf<String, String>()
                fieldsObj.keys().forEach { key -> fields[key] = fieldsObj.opt(key)?.toString().orEmpty() }
                out.add(rid to fields)
            }
            offset = json.optString("offset", "").takeIf { it.isNotBlank() }
            if (offset == null) break
        }
        return out
    }

    override fun createRow(be: RowDbBackend, tableId: String, headers: List<String>, row: List<String>): String {
        val fields = JSONObject()
        headers.forEachIndexed { i, h -> fields.put(h, row.getOrElse(i) { "" }) }
        val body = JSONObject().put("fields", fields).toString()
        val (_, text) = HttpJson.request("POST", url(be, tableId), auth(be), body)
        return JSONObject(text).optString("id", "")
    }

    override fun updateRow(be: RowDbBackend, tableId: String, rowId: String, headers: List<String>, row: List<String>) {
        val fields = JSONObject()
        headers.forEachIndexed { i, h -> fields.put(h, row.getOrElse(i) { "" }) }
        val body = JSONObject().put("fields", fields).toString()
        HttpJson.request("PATCH", url(be, tableId, rowId), auth(be), body)
    }

    override fun deleteRow(be: RowDbBackend, tableId: String, rowId: String) {
        try {
            HttpJson.request("DELETE", url(be, tableId, rowId), auth(be))
        } catch (e: RuntimeException) {
            if (e.message?.contains("HTTP 204") != true) throw e
        }
    }
}
