package com.davidelang.remotetable

/**
 * Placeholder for collaborative editors without a stable headless row API yet.
 * [testConnection] reports not-implemented; other ops throw.
 */
class DeferredBackend(
    override val backendId: String,
    private val reason: String = "not implemented: no headless row API yet",
) : Backend {
    override fun testConnection(): Map<String, Any?> =
        mapOf("ok" to false, "message" to reason, "code" to "deferred")

    override fun listTabs(): List<String> = error(reason)
    override fun ensureHeaders(tab: String, headers: List<String>): List<String> = error(reason)
    override fun readRows(tab: String): TabData = error(reason)
    override fun writeRows(tab: String, headers: List<String>, rows: List<List<String>>, mode: String): Int =
        error(reason)
}
