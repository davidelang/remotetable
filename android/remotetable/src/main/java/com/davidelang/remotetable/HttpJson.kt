package com.davidelang.remotetable

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

internal object HttpJson {
    /**
     * HTTP request. When [limiter] is set, all calls are paced and 429-retried
     * (same logical call) per [RateLimiter].
     */
    fun request(
        method: String,
        url: String,
        headers: Map<String, String> = emptyMap(),
        body: String? = null,
        contentType: String? = "application/json",
        timeoutMs: Int = 60_000,
        limiter: RateLimiter? = null,
    ): Pair<Int, String> {
        val run = {
            val conn = (URL(url).openConnection() as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = timeoutMs
                readTimeout = timeoutMs
                doInput = true
                headers.forEach { (k, v) -> setRequestProperty(k, v) }
                if (body != null) {
                    doOutput = true
                    if (contentType != null) setRequestProperty("Content-Type", contentType)
                }
            }
            try {
                if (body != null) {
                    conn.outputStream.use { it.write(body.toByteArray(StandardCharsets.UTF_8)) }
                }
                val code = conn.responseCode
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val text = stream?.use { s ->
                    BufferedReader(InputStreamReader(s, StandardCharsets.UTF_8)).readText()
                }.orEmpty()
                if (code !in 200..299) {
                    throw RuntimeException("HTTP $code: ${text.take(300)}")
                }
                code to text
            } finally {
                conn.disconnect()
            }
        }
        return if (limiter != null) limiter.withLimit(run) else run()
    }

    fun getJson(url: String, headers: Map<String, String>, limiter: RateLimiter? = null): JSONObject {
        val (_, text) = request("GET", url, headers, limiter = limiter)
        if (text.isBlank()) return JSONObject()
        return JSONObject(text)
    }

    fun putJson(
        url: String,
        headers: Map<String, String>,
        body: JSONObject,
        limiter: RateLimiter? = null,
    ): JSONObject {
        val (_, text) = request("PUT", url, headers, body.toString(), limiter = limiter)
        if (text.isBlank()) return JSONObject()
        return JSONObject(text)
    }

    fun postJson(
        url: String,
        headers: Map<String, String>,
        body: JSONObject,
        limiter: RateLimiter? = null,
    ): JSONObject {
        val (_, text) = request("POST", url, headers, body.toString(), limiter = limiter)
        if (text.isBlank()) return JSONObject()
        return JSONObject(text)
    }

    fun patchJson(
        url: String,
        headers: Map<String, String>,
        body: JSONObject,
        limiter: RateLimiter? = null,
    ): JSONObject {
        val (_, text) = request("PATCH", url, headers, body.toString(), limiter = limiter)
        if (text.isBlank()) return JSONObject()
        return JSONObject(text)
    }

    fun jsonArrayOfRows(rows: List<List<String>>): JSONArray {
        val arr = JSONArray()
        for (row in rows) {
            val ja = JSONArray()
            for (c in row) ja.put(c)
            arr.put(ja)
        }
        return arr
    }

    fun parseGrid(values: JSONArray?): TabData {
        if (values == null || values.length() == 0) return TabData(emptyList(), emptyList())
        val headers = mutableListOf<String>()
        val first = values.optJSONArray(0) ?: JSONArray()
        for (i in 0 until first.length()) headers.add(first.optString(i, ""))
        val rows = mutableListOf<List<String>>()
        for (r in 1 until values.length()) {
            val rowArr = values.optJSONArray(r) ?: JSONArray()
            val row = MutableList(headers.size) { "" }
            for (c in 0 until minOf(rowArr.length(), headers.size)) {
                row[c] = rowArr.optString(c, "")
            }
            if (rowArr.length() > headers.size) {
                for (c in headers.size until rowArr.length()) {
                    headers.add("")
                    for (ri in rows.indices) {
                        rows[ri] = rows[ri] + listOf("")
                    }
                    row.add(rowArr.optString(c, ""))
                }
            }
            while (row.size < headers.size) row.add("")
            rows.add(row)
        }
        return TabData(headers, rows)
    }
}
