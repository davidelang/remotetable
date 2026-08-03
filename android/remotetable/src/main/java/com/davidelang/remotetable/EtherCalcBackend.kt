package com.davidelang.remotetable

import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

/**
 * EtherCalc CSV over HTTP.
 * One room ≈ one tab; [room] is the room id (VE may pass room-per-tab).
 */
class EtherCalcBackend(
    baseUrl: String,
    private val room: String = "sheet",
    private val auth: String? = null,
) : Backend {
    override val backendId: String = BackendIds.ETHERCALC
    private val base = baseUrl.trimEnd('/')

    private fun authHeaders(contentType: String? = null): Map<String, String> = buildMap {
        if (!auth.isNullOrBlank()) put("Authorization", "Bearer $auth")
        if (contentType != null) put("Content-Type", contentType)
    }

    override fun testConnection(): Map<String, Any?> {
        if (base.isBlank()) {
            return mapOf("ok" to false, "message" to "missing base_url", "code" to "auth")
        }
        return try {
            getCsv()
            mapOf("ok" to true, "message" to "ethercalc room=$room")
        } catch (e: Exception) {
            mapOf("ok" to false, "message" to (e.message?.take(200) ?: "error"), "code" to "network")
        }
    }

    override fun listTabs(): List<String> = listOf(room)

    override fun ensureHeaders(tab: String, headers: List<String>): List<String> {
        val data = readRows(tab)
        if (data.headers.isEmpty()) {
            writeRows(tab, headers, emptyList(), mode = "replace")
            return headers
        }
        val newH = data.headers.toMutableList()
        for (h in headers) if (h !in newH) newH.add(h)
        if (newH != data.headers) {
            writeRows(tab, newH, data.rows, mode = "replace")
        }
        return newH
    }

    override fun readRows(tab: String): TabData {
        val text = getCsv()
        if (text.isBlank()) return TabData(emptyList(), emptyList())
        val lines = text.lines().filter { it.isNotEmpty() || text.isNotBlank() }
        if (lines.isEmpty()) return TabData(emptyList(), emptyList())
        val parsed = lines.map { parseCsvLine(it) }
        val headers = parsed.first()
        val rows = parsed.drop(1).map { row ->
            val m = row.toMutableList()
            while (m.size < headers.size) m.add("")
            m.toList()
        }
        return TabData(headers, rows)
    }

    override fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int {
        val hdr: List<String>
        val body: List<List<String>>
        if (mode == "replace") {
            hdr = headers
            body = rows
        } else {
            val existing = readRows(tab)
            hdr = existing.headers.ifEmpty { headers }
            body = existing.rows + rows
        }
        val csv = buildString {
            append(hdr.joinToString(",") { csvEscape(it) })
            append('\n')
            for (r in body) {
                append(r.joinToString(",") { csvEscape(it) })
                append('\n')
            }
        }
        putCsv(csv)
        return rows.size
    }

    override fun renameTab(oldTitle: String, newTitle: String): Boolean {
        // Single-room backend: rename not supported at room level.
        return oldTitle == newTitle || oldTitle == room
    }

    private fun getCsv(): String {
        val url = "$base/$room.csv"
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 30_000
            readTimeout = 60_000
            authHeaders().forEach { (k, v) -> setRequestProperty(k, v) }
        }
        try {
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.use { BufferedReader(InputStreamReader(it, StandardCharsets.UTF_8)).readText() }.orEmpty()
            if (code !in 200..299 && code != 404) {
                throw RuntimeException("ethercalc HTTP $code: ${text.take(200)}")
            }
            return if (code == 404) "" else text
        } finally {
            conn.disconnect()
        }
    }

    private fun putCsv(text: String) {
        val data = text.toByteArray(StandardCharsets.UTF_8)
        try {
            val conn = (URL("$base/$room").openConnection() as HttpURLConnection).apply {
                requestMethod = "PUT"
                doOutput = true
                connectTimeout = 30_000
                readTimeout = 60_000
                authHeaders("text/csv").forEach { (k, v) -> setRequestProperty(k, v) }
            }
            try {
                conn.outputStream.use { it.write(data) }
                if (conn.responseCode !in 200..299) {
                    throw RuntimeException("PUT failed ${conn.responseCode}")
                }
            } finally {
                conn.disconnect()
            }
        } catch (_: Exception) {
            val conn = (URL("$base/_/$room").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 30_000
                readTimeout = 60_000
                authHeaders("text/csv").forEach { (k, v) -> setRequestProperty(k, v) }
            }
            try {
                conn.outputStream.use { it.write(data) }
                if (conn.responseCode !in 200..299) {
                    throw RuntimeException("POST append failed ${conn.responseCode}")
                }
            } finally {
                conn.disconnect()
            }
        }
    }

    companion object {
        fun csvEscape(cell: String): String {
            if (cell.contains(',') || cell.contains('"') || cell.contains('\n')) {
                return "\"" + cell.replace("\"", "\"\"") + "\""
            }
            return cell
        }

        fun parseCsvLine(line: String): List<String> {
            val out = mutableListOf<String>()
            val sb = StringBuilder()
            var i = 0
            var inQuotes = false
            while (i < line.length) {
                val c = line[i]
                when {
                    inQuotes && c == '"' && i + 1 < line.length && line[i + 1] == '"' -> {
                        sb.append('"'); i += 2; continue
                    }
                    inQuotes && c == '"' -> {
                        inQuotes = false; i++; continue
                    }
                    !inQuotes && c == '"' -> {
                        inQuotes = true; i++; continue
                    }
                    !inQuotes && c == ',' -> {
                        out.add(sb.toString()); sb.clear(); i++; continue
                    }
                    else -> {
                        sb.append(c); i++
                    }
                }
            }
            out.add(sb.toString())
            return out
        }
    }
}
