package com.davidelang.remotetable

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * File-backed multi-tab book (offline L0).
 * On-disk: `{ "tabs": { "Name": { "headers": [...], "rows": [[...]] } } }`.
 * Each [writeRows] / [ensureHeaders] flushes the whole book to [path].
 */
class JsonBookBackend(
    private val path: String,
    initial: Map<String, TabData> = emptyMap(),
) : Backend {
    override val backendId: String = BackendIds.JSON_BOOK
    private val mem = MockBackend(loadOr(initial))

    private fun loadOr(fallback: Map<String, TabData>): Map<String, TabData> {
        val f = File(path)
        if (!f.isFile) return fallback
        return try {
            val root = JSONObject(f.readText())
            val tabs = root.optJSONObject("tabs") ?: return fallback
            val out = mutableMapOf<String, TabData>()
            val keys = tabs.keys()
            while (keys.hasNext()) {
                val name = keys.next()
                val obj = tabs.optJSONObject(name) ?: continue
                val headers = mutableListOf<String>()
                val hArr = obj.optJSONArray("headers") ?: JSONArray()
                for (i in 0 until hArr.length()) headers.add(hArr.optString(i, ""))
                val rows = mutableListOf<List<String>>()
                val rArr = obj.optJSONArray("rows") ?: JSONArray()
                for (r in 0 until rArr.length()) {
                    val rowArr = rArr.optJSONArray(r) ?: JSONArray()
                    val row = MutableList(headers.size) { "" }
                    for (c in 0 until minOf(rowArr.length(), headers.size)) {
                        row[c] = rowArr.optString(c, "")
                    }
                    rows.add(row)
                }
                out[name] = TabData(headers, rows)
            }
            out
        } catch (_: Exception) {
            fallback
        }
    }

    private fun flush() {
        val root = JSONObject()
        val tabs = JSONObject()
        for (name in mem.listTabs()) {
            val data = mem.readRows(name)
            val obj = JSONObject()
            val h = JSONArray()
            data.headers.forEach { h.put(it) }
            obj.put("headers", h)
            val rows = JSONArray()
            for (row in data.rows) {
                val ra = JSONArray()
                row.forEach { ra.put(it) }
                rows.put(ra)
            }
            obj.put("rows", rows)
            tabs.put(name, obj)
        }
        root.put("tabs", tabs)
        val f = File(path)
        f.parentFile?.mkdirs()
        f.writeText(root.toString(2) + "\n")
    }

    override fun testConnection(): Map<String, Any?> = mapOf(
        "ok" to true,
        "message" to "json-book path=$path tabs=${listTabs().size}",
    )

    override fun listTabs(): List<String> = mem.listTabs()

    override fun ensureHeaders(tab: String, headers: List<String>): List<String> {
        val out = mem.ensureHeaders(tab, headers)
        flush()
        return out
    }

    override fun readRows(tab: String): TabData = mem.readRows(tab)

    override fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int {
        val n = mem.writeRows(tab, headers, rows, mode)
        flush()
        return n
    }

    override fun ensureTab(tab: String) {
        mem.ensureTab(tab)
        flush()
    }

    override fun renameTab(oldTitle: String, newTitle: String): Boolean {
        val ok = mem.renameTab(oldTitle, newTitle)
        if (ok) flush()
        return ok
    }

    override fun deleteTab(tab: String) {
        mem.deleteTab(tab)
        flush()
    }
}
