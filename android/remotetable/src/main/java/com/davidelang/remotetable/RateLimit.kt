package com.davidelang.remotetable

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import kotlin.random.Random

/**
 * Proactive pace + 429 detect/backoff/retry for L0 transports.
 * Defaults align with known Google Sheets ~60/min read and write caps.
 *
 * See `spec/CONTRACT.md` rate_limits.
 */
data class RateLimitConfig(
    val readPerMinute: Int = 45,
    val writePerMinute: Int = 45,
    /** Min gap between any API calls for this limiter scope. */
    val minGapMs: Long = 1_300L,
    val maxAttempts: Int = 8,
) {
    companion object {
        /** Google Sheets schema_version 1 defaults. */
        val GOOGLE_SHEETS: RateLimitConfig = RateLimitConfig(
            readPerMinute = 45,
            writePerMinute = 45,
            minGapMs = 1_300L,
            maxAttempts = 8,
        )

        fun fromMap(map: Map<String, Any?>?): RateLimitConfig {
            if (map == null || map.isEmpty()) return GOOGLE_SHEETS
            fun num(key: String, default: Long): Long {
                val v = map[key] ?: return default
                return when (v) {
                    is Number -> v.toLong()
                    is String -> v.toLongOrNull() ?: default
                    else -> default
                }
            }
            return RateLimitConfig(
                readPerMinute = num("read_per_minute", 45).toInt().coerceAtLeast(1),
                writePerMinute = num("write_per_minute", 45).toInt().coerceAtLeast(1),
                minGapMs = num("min_gap_ms", 1_300L).coerceAtLeast(0L),
                maxAttempts = num("max_attempts", 8).toInt().coerceIn(1, 32),
            )
        }
    }
}

fun interface RateLimitProgress {
    fun onStatus(message: String)
}

/**
 * Thread-safe limiter for one backend instance (or shared scope).
 * Blocking sleeps are intentional for HttpURLConnection paths on worker threads.
 */
class RateLimiter(
    private val config: RateLimitConfig = RateLimitConfig.GOOGLE_SHEETS,
    progress: RateLimitProgress? = null,
) {
    private val lastCallAtMs = AtomicLong(0L)
    private val progressRef = AtomicReference(progress)

    fun setProgress(progress: RateLimitProgress?) {
        progressRef.set(progress)
    }

    fun config(): RateLimitConfig = config

    fun <T> withLimit(block: () -> T): T {
        var attempt = 0
        while (true) {
            paceIfNeeded()
            try {
                val result = block()
                lastCallAtMs.set(System.currentTimeMillis())
                return result
            } catch (e: Exception) {
                if (!isRateLimitError(e)) throw e
                attempt++
                if (attempt >= config.maxAttempts) throw e
                val waitMs = backoffMs(attempt)
                val sec = (waitMs / 1000L).toInt()
                val status =
                    "Rate limited — waiting ${sec}s (try $attempt/${config.maxAttempts})…"
                notify(status)
                Thread.sleep(waitMs)
            }
        }
    }

    private fun paceIfNeeded() {
        val last = lastCallAtMs.get()
        if (last <= 0L || config.minGapMs <= 0L) return
        val elapsed = System.currentTimeMillis() - last
        val wait = config.minGapMs - elapsed
        if (wait > 0L) Thread.sleep(wait)
    }

    private fun notify(message: String) {
        try {
            progressRef.get()?.onStatus(message)
        } catch (_: Exception) {
            // progress must never break transport
        }
    }

    companion object {
        fun isRateLimitError(throwable: Throwable): Boolean {
            var t: Throwable? = throwable
            while (t != null) {
                if (isRateLimitError(t.message)) return true
                if (isRateLimitError(t.toString())) return true
                t = t.cause
            }
            return false
        }

        fun isRateLimitError(message: String?): Boolean {
            val m = message?.trim().orEmpty()
            if (m.isEmpty()) return false
            val lower = m.lowercase()
            return lower.contains("ratelimitexceeded") ||
                lower.contains("resource_exhausted") ||
                lower.contains("quota exceeded") ||
                lower.contains("write requests per minute") ||
                lower.contains("read requests per minute") ||
                lower.contains("read_requests") ||
                lower.contains("write_requests") ||
                lower.contains("user-rate limit exceeded") ||
                lower.contains("http 429") ||
                lower.contains("status code 429") ||
                lower.contains("statuscode=429") ||
                Regex("""\b429\b""").containsMatchIn(m)
        }

        /** attemptAfterFailure 1 → 60–120s; later → 90–180s; cap 180s. */
        fun backoffMs(attemptAfterFailure: Int): Long {
            val n = attemptAfterFailure.coerceAtLeast(1)
            val ms = when (n) {
                1 -> 60_000L + Random.nextLong(0, 60_001L)
                else -> 90_000L + Random.nextLong(0, 90_001L)
            }
            return ms.coerceIn(60_000L, 180_000L)
        }
    }
}

/** Optional registry so config JSON can install defaults per backend id. */
object RateLimitRegistry {
    private val defaults = ConcurrentHashMap<String, RateLimitConfig>()

    init {
        // min_gap_ms is the primary throttle; read/write_per_minute are documentation/config
        // for apps (dual independent buckets not required in foundation).
        defaults[BackendIds.GOOGLE_SHEETS] = RateLimitConfig.GOOGLE_SHEETS
        val conservative = RateLimitConfig(
            readPerMinute = 45,
            writePerMinute = 45,
            minGapMs = 1_300L,
            maxAttempts = 8,
        )
        defaults[BackendIds.EXCEL_GRAPH] = conservative
        defaults[BackendIds.ETHERCALC] = RateLimitConfig(
            readPerMinute = 60,
            writePerMinute = 60,
            minGapMs = 1_000L,
            maxAttempts = 8,
        )
        defaults[BackendIds.ZOHO_SHEET] = conservative
        for (id in BackendIds.ROW_DB) {
            defaults[id] = RateLimitConfig(
                readPerMinute = 60,
                writePerMinute = 60,
                minGapMs = 1_000L,
                maxAttempts = 8,
            )
        }
    }

    fun setDefault(backendId: String, config: RateLimitConfig) {
        defaults[backendId] = config
    }

    fun defaultFor(backendId: String): RateLimitConfig =
        defaults[backendId] ?: RateLimitConfig()

    fun applyFromContractJson(rateLimits: Map<String, Map<String, Any?>>?) {
        if (rateLimits == null) return
        for ((backendId, cfg) in rateLimits) {
            defaults[backendId] = RateLimitConfig.fromMap(cfg)
        }
    }
}
