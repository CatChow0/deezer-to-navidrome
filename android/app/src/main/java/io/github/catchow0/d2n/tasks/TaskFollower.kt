package io.github.catchow0.d2n.tasks

import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.D2nJson
import io.github.catchow0.d2n.data.TaskEvent
import io.github.catchow0.d2n.data.NotThisServer
import io.github.catchow0.d2n.data.apiCall
import java.io.IOException
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerializationException
import okhttp3.Call
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request

/** What following a task gives: its events, then how it ended. */
sealed interface TaskUpdate {
    data class Event(val event: TaskEvent) : TaskUpdate
    data class Ended(val error: Boolean, val message: String?) : TaskUpdate
}

/**
 * Follows a task live. Android's stream client does not reconnect by itself,
 * so this one does: after each of the server's 45 s segments, or a cut, it
 * resumes from the last event it got (Last-Event-ID). When the stream fails
 * three times in a row (a proxy that buffers it, say), it asks for the events
 * after the last one instead, the server waiting up to 25 s for the next.
 */
class TaskFollower(
    private val client: OkHttpClient,
    private val api: (HttpUrl) -> D2nApi,
    private val pause: suspend (Long) -> Unit = { delay(it) },
) {
    private sealed interface Segment {
        data class Ended(val error: Boolean, val message: String?) : Segment
        data class Closed(val gotEvents: Boolean) : Segment
        data class Failed(val gotEvents: Boolean) : Segment
    }

    fun follow(base: HttpUrl, taskId: String, after: Int = -1): Flow<TaskUpdate> = channelFlow {
        var last = after
        var retry = SERVER_RETRY
        var failures = 0
        while (failures < STREAM_FAILURES) {
            val request = Request.Builder()
                .url(base.resolve("api/v1/tasks/$taskId/stream")!!)
                .header("Accept", "text/event-stream")
                .apply { if (last >= 0) header("Last-Event-ID", last.toString()) }
                .build()
            val call = client.newCall(request)
            val segment = whileCancellable(call) {
                var gotEvents = false
                try {
                    call.execute().use { response ->
                        if (!response.isSuccessful) return@whileCancellable Segment.Failed(gotEvents = false)
                        for (message in SseParser.messages(response.body.source())) {
                            message.retryMillis?.let { retry = it }
                            val event = message.data?.let(::decode) ?: continue
                            if (message.id == null) {
                                // Without an ID, only the server's "Task not found".
                                if (event.done) return@whileCancellable Segment.Ended(true, event.message)
                                continue
                            }
                            last = message.id
                            gotEvents = true
                            send(TaskUpdate.Event(event.copy(index = message.id)))
                            if (event.done) return@whileCancellable Segment.Ended(event.error, event.message)
                        }
                    }
                    Segment.Closed(gotEvents)
                } catch (e: IOException) {
                    Segment.Failed(gotEvents)
                }
            }
            when (segment) {
                is Segment.Ended -> {
                    send(TaskUpdate.Ended(segment.error, segment.message))
                    return@channelFlow
                }
                is Segment.Closed -> {
                    // An answer without events (a login page, a buffering proxy, or
                    // a task idle for minutes) is not getting through either.
                    failures = if (segment.gotEvents) 0 else failures + 1
                    if (failures < STREAM_FAILURES) pause(retry)
                }
                is Segment.Failed -> {
                    failures = if (segment.gotEvents) 1 else failures + 1
                    if (failures < STREAM_FAILURES) pause(BACKOFF[(failures - 1).coerceIn(0, BACKOFF.lastIndex)])
                }
            }
        }
        // The stream does not get through: wait for the events instead.
        var attempt = 0
        while (true) {
            val answer = try {
                apiCall { api(base).taskEvents(taskId, after = last, wait = WAIT_SECONDS) }
            } catch (e: NotThisServer) {
                // Not this app answering (a login page): waiting longer will not help.
                send(TaskUpdate.Ended(true, e.message))
                return@channelFlow
            } catch (e: ApiError) {
                if (e.status == 404) {
                    send(TaskUpdate.Ended(true, e.message))
                    return@channelFlow
                }
                pause(BACKOFF[attempt.coerceAtMost(BACKOFF.lastIndex)])
                attempt++
                continue
            } catch (e: ApiFailure) {
                pause(BACKOFF[attempt.coerceAtMost(BACKOFF.lastIndex)])
                attempt++
                continue
            }
            attempt = 0
            for (event in answer.events) {
                last = event.index
                send(TaskUpdate.Event(event))
                if (event.done) {
                    send(TaskUpdate.Ended(event.error, event.message))
                    return@channelFlow
                }
            }
            if (answer.task.done && answer.events.isEmpty()) {
                send(TaskUpdate.Ended(answer.task.error, answer.task.message))
                return@channelFlow
            }
        }
    }

    private fun decode(data: String): TaskEvent? = try {
        D2nJson.decodeFromString(TaskEvent.serializer(), data)
    } catch (e: SerializationException) {
        null
    }

    /** Runs a blocking read on IO; if the collector goes away meanwhile, the
     * call is cancelled, which ends the read at once. */
    private suspend fun <T> whileCancellable(call: Call, block: suspend () -> T): T = coroutineScope {
        val watcher = launch(start = CoroutineStart.UNDISPATCHED) {
            try {
                awaitCancellation()
            } finally {
                call.cancel()
            }
        }
        try {
            withContext(Dispatchers.IO) { block() }
        } finally {
            watcher.cancel()
        }
    }

    private companion object {
        const val SERVER_RETRY = 1_500L
        const val STREAM_FAILURES = 3
        const val WAIT_SECONDS = 25
        val BACKOFF = listOf(1_000L, 2_000L, 5_000L, 10_000L)
    }
}
