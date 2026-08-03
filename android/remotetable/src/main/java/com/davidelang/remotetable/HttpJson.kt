package com.davidelang.remotetable

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

internal object HttpJson {
    fun request(
        method: String,
        url: String,
        headers: Map<String, String> = emptyMap(),
        body: String? = null,
        contentType: String? = "application/json",
        timeoutMs: Int = 60_000,
    ): Pair<Int, String> {
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
            return code to text
        } finally {
            conn.disconnect()
        }
    }

    fun getJson(url: String, headers: Map<String, String>): JSONObject {
        val (_, text) = request("GET", url, headers)
        if (text.isBlank()) return JSONObject()
        return JSONObject(text)
    }

    fun putJson(url: String, headers: Map<String, String>, body: JSONObject): JSONObject {
        val (_, text) = request("PUT", url, headers, body.toString())
        if (text.isBlank()) return JSONObject()
        return JSONObject(text)
    }

    fun postJson(url: String, headers: Map<String, String>, body: JSONObject): JSONObject {
        val (_, text) = request("POST", url, headers, body.toString())
        if (text.isBlank()) return JSONObject()
        return JSONObject(text)
    }

    fun patchJson(url: String, headers: Map<String, String>, body: JSONObject): JSONObject {
        val (_, text) = request("PATCH", url, headers, body.toString())
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
            // also accept longer rows by expanding
            if (rowArr.length() > headers.size) {
                for (c in headers.size until rowArr.length()) {
                    headers.add("")
                    rows.forEach { /* can't mutate immutable */ }
                }
            }
            while (row.size < headers.size) row.add("")
            rows.add(row)
        }
        return TabData(headers, rows)
    }
}
