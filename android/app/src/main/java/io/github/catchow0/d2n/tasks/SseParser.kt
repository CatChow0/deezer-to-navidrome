package io.github.catchow0.d2n.tasks

import okio.BufferedSource

/** One message of an event stream: its `id:`, its `data:` lines joined, and a
 * `retry:` delay when the server sends one. */
data class SseMessage(val id: Int?, val data: String?, val retryMillis: Long?)

/** Reads an event stream (text/event-stream) as it arrives. Comment lines
 * (`: keepalive`) are skipped; a blank line ends a message. */
object SseParser {
    fun messages(source: BufferedSource): Sequence<SseMessage> = sequence {
        var id: Int? = null
        var data: StringBuilder? = null
        var retry: Long? = null
        var started = false
        while (true) {
            val line = source.readUtf8Line() ?: break
            if (line.isEmpty()) {
                if (started) yield(SseMessage(id, data?.toString(), retry))
                id = null
                data = null
                retry = null
                started = false
                continue
            }
            if (line.startsWith(":")) continue
            val colon = line.indexOf(':')
            val field = if (colon < 0) line else line.substring(0, colon)
            val value = if (colon < 0) "" else line.substring(colon + 1).removePrefix(" ")
            when (field) {
                "id" -> id = value.toIntOrNull()
                "data" -> data = (data?.append('\n') ?: StringBuilder()).append(value)
                "retry" -> retry = value.toLongOrNull()
                else -> continue
            }
            started = true
        }
    }
}
