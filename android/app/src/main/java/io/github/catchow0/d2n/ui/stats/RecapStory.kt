package io.github.catchow0.d2n.ui.stats

import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameMillis
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.audio.PreviewPlayer
import io.github.catchow0.d2n.data.Recap
import io.github.catchow0.d2n.data.RankRow
import io.github.catchow0.d2n.data.StorySlide
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.Cover
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.mediaUrl
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.theme.Unbounded
import io.github.catchow0.d2n.ui.theme.InstrumentSans

/** How long each slide stays, in seconds, as on the web; the outro stays. */
private val SECONDS = mapOf(
    "intro" to 6, "opener" to 7, "genres" to 8, "artist_countdown" to 11, "top_artist" to 9, "loyalty" to 8,
    "track_countdown" to 11, "top_track" to 9, "obsession" to 8, "binge" to 8, "album_run" to 8, "new_artists" to 9,
    "then_now" to 11, "biggest_month" to 7, "clock" to 8, "personality" to 9, "time" to 10,
)

/** Background and ink, the web's pairs. */
private val PALETTES = listOf(
    0xFF1B00FF to 0xFFFFE14D, 0xFFFF2E93 to 0xFF1A0033, 0xFF00E0C6 to 0xFF08002E, 0xFFFF6A13 to 0xFF14002B,
    0xFFFFE14D to 0xFF2A0A7A, 0xFF12002E to 0xFFFF5CAD, 0xFFB6FF3C to 0xFF12002E, 0xFF6A00F4 to 0xFFFDFBFF,
).map { (back, ink) -> Color(back) to Color(ink) }

private val KNOWN = SECONDS.keys + "outro"

/** The palette of slide [index], seeded by the recap's key so a recap always looks the same. */
fun paletteFor(key: String, index: Int, type: String): Pair<Color, Color> {
    if (type == "top_artist") return Color.Black to Color.White
    var seed = 0L
    key.forEach { seed = (seed * 31 + it.code) and 0xFFFFFFFFL }
    return PALETTES[((seed + index) % PALETTES.size).toInt()]
}

/** The words of the web's story, for one recap. */
class StoryWords(private val recap: Recap) {
    private val isYear = recap.kind == "year"
    val name: String = if (isYear) recap.label else recap.label.substringBefore(' ')
    val here: String = if (isYear) "this year" else "this month"
    val previous: String = recap.previous?.takeIf { !recap.soFar }?.let { if (isYear) it.label else it.label.substringBefore(' ') }.orEmpty()

    /** What a number in a top list means, always in words. */
    fun change(row: RankRow): String {
        if (row.isNew && recap.story.established == true) return "New $here"
        if (!recap.story.comparable) return ""
        val before = row.previousPlays ?: return "None in $previous"
        val delta = row.plays - before
        if (delta == 0) return "Same as $previous"
        return "${if (delta > 0) "+" else "-"}${plural(kotlin.math.abs(delta), "play")} vs $previous"
    }
}

@Composable
fun RecapStory(vm: RecapViewModel, player: PreviewPlayer, onClose: () -> Unit) {
    val recap by vm.recap.collectAsStateWithLifecycle()
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        val shown = recap.value
        when {
            shown != null -> Story(shown, player, onClose)
            recap.loading -> Message("Loading your recap…", onClose)
            else -> Message(recap.error ?: "This recap could not be loaded.", onClose, onRetry = vm::refresh)
        }
    }
}

@Composable
private fun Message(text: String, onClose: () -> Unit, onRetry: (() -> Unit)? = null) {
    Box(Modifier.fillMaxSize().background(Color(0xFF12002E)), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(text, color = Color(0xFFFDFBFF), style = TextStyle(fontFamily = InstrumentSans, fontSize = 18.sp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (onRetry != null) D2nButton("Try again", onRetry, small = true)
                D2nButton("Close", onClose, kind = ButtonKind.Ghost, small = true)
            }
        }
    }
}

@Composable
private fun Story(recap: Recap, player: PreviewPlayer, onClose: () -> Unit) {
    val slides = remember(recap) { recap.story.slides.filter { it.type in KNOWN } }
    val words = remember(recap) { StoryWords(recap) }
    val context = LocalContext.current
    // Animations turned off on the phone: the story waits for taps, as the web does with reduced motion.
    val still = remember { Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
    var index by remember { mutableIntStateOf(0) }
    var paused by remember { mutableStateOf(false) }
    var elapsed by remember { mutableFloatStateOf(0f) }
    var drag by remember { mutableFloatStateOf(0f) }
    val audioBase = mediaUrl("/api/v1/stats/audio/")

    if (slides.isEmpty()) {
        Message("Nothing played in ${words.name}.", onClose)
        return
    }
    val slide = slides[index.coerceIn(0, slides.lastIndex)]
    val length = SECONDS[slide.type] ?: 0
    val go: (Int) -> Unit = { to ->
        if (to in slides.indices) {
            index = to
            elapsed = 0f
        }
    }

    LaunchedEffect(index, paused) {
        if (paused || still || length == 0) return@LaunchedEffect
        var last = withFrameMillis { it }
        while (elapsed < length) {
            val now = withFrameMillis { it }
            elapsed += ((now - last) / 1000f).coerceAtMost(0.25f)
            last = now
        }
        if (index < slides.lastIndex) go(index + 1)
    }
    // Each slide's song: the profile's own file from a third of the way in, else its Deezer preview.
    LaunchedEffect(slide.track?.id) {
        val track = slide.track ?: return@LaunchedEffect
        if (audioBase == null) return@LaunchedEffect
        val start = if (track.duration > 0) (track.duration * 0.33).coerceAtMost((track.duration - 40).coerceAtLeast(0.0)) else 0.0
        player.playUrl("story-${track.id}", "$audioBase${track.id}", track.title, track.artist, track.image, (start * 1000).toLong(), track.deezerTrackId)
    }
    LaunchedEffect(paused) { if (paused) player.pause() else player.resume() }
    DisposableEffect(Unit) { onDispose { player.stop() } }

    val (back, ink) = paletteFor(recap.key, index, slide.type)
    Box(
        Modifier
            .fillMaxSize()
            .background(back)
            .pointerInput(slides.size) {
                // Holding pauses; a tap on the left third goes back, elsewhere on.
                detectTapGestures(
                    onPress = {
                        paused = true
                        tryAwaitRelease()
                        paused = false
                    },
                    onLongPress = { },
                    onTap = { offset -> if (offset.x < size.width / 3f) go(index - 1) else go(index + 1) },
                )
            }
            .pointerInput(Unit) {
                detectVerticalDragGestures(
                    onDragEnd = {
                        if (drag > 160f) onClose()
                        drag = 0f
                    },
                    onVerticalDrag = { _, amount -> drag = (drag + amount).coerceAtLeast(0f) },
                )
            },
    ) {
        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                slides.indices.forEach { i ->
                    val fill = when {
                        i < index -> 1f
                        i > index -> 0f
                        length == 0 || still -> 1f
                        else -> (elapsed / length).coerceIn(0f, 1f)
                    }
                    Box(Modifier.weight(1f).height(3.dp).clip(CircleShape).background(ink.copy(alpha = 0.3f))) {
                        Box(Modifier.fillMaxWidth(fill).height(3.dp).background(ink))
                    }
                }
            }
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("${index + 1} of ${slides.size}", Modifier.weight(1f).padding(start = 8.dp), color = ink.copy(alpha = 0.8f), style = TextStyle(fontFamily = InstrumentSans, fontSize = 13.sp))
                StoryButton(if (paused) R.drawable.ic_play else R.drawable.ic_pause, if (paused) "Play the story" else "Pause the story", ink) { paused = !paused }
                StoryButton(R.drawable.ic_close, "Close the recap", ink, onClick = onClose)
            }
            Box(
                Modifier.weight(1f).fillMaxWidth().padding(horizontal = 24.dp, vertical = 16.dp).semantics { liveRegion = LiveRegionMode.Polite },
                contentAlignment = Alignment.Center,
            ) {
                SlideContent(recap, words, slide, ink, onReplay = { go(0) }, onClose = onClose)
            }
            Row(Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                StoryButton(R.drawable.ic_back, "Previous slide", ink, enabled = index > 0) { go(index - 1) }
                // The back arrow, turned to point forward.
                Box(Modifier.graphicsLayer(scaleX = -1f)) {
                    StoryButton(R.drawable.ic_back, "Next slide", ink, enabled = index < slides.lastIndex) { go(index + 1) }
                }
            }
        }
    }
}

@Composable
private fun StoryButton(icon: Int, label: String, ink: Color, enabled: Boolean = true, onClick: () -> Unit) {
    IconButton(onClick, enabled = enabled) {
        Icon(painterResource(icon), contentDescription = label, tint = if (enabled) ink else ink.copy(alpha = 0.3f))
    }
}

private fun big(ink: Color, size: Int = 34) = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight(700), fontSize = size.sp, lineHeight = (size * 1.15).sp, color = ink, textAlign = TextAlign.Center)

private fun line(ink: Color, size: Int = 18) = TextStyle(fontFamily = InstrumentSans, fontWeight = FontWeight(500), fontSize = size.sp, lineHeight = (size * 1.35).sp, color = ink, textAlign = TextAlign.Center)

@Composable
private fun Kicker(text: String, ink: Color) = Text(text.uppercase(), style = line(ink.copy(alpha = 0.8f), 14))

@Composable
private fun Title(text: String, ink: Color, size: Int = 34) = Text(text, style = big(ink, size), maxLines = 3, overflow = TextOverflow.Ellipsis)

@Composable
private fun Line(text: String, ink: Color, size: Int = 18) = Text(text, style = line(ink, size))

@Composable
private fun Centered(content: @Composable ColumnScope.() -> Unit) = Column(
    Modifier.fillMaxWidth(),
    horizontalAlignment = Alignment.CenterHorizontally,
    verticalArrangement = Arrangement.spacedBy(14.dp, Alignment.CenterVertically),
    content = content,
)

@Composable
private fun Countdown(rows: List<RankRow>, words: StoryWords, ink: Color, name: (RankRow) -> String) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        rows.drop(1).take(4).reversed().forEach { row ->
            val rank = rows.indexOf(row) + 1
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("$rank", style = big(ink, 26), modifier = Modifier.width(34.dp))
                Cover(row.image, name(row), size = 52.dp)
                Column(Modifier.weight(1f)) {
                    Text(name(row), style = line(ink, 18).copy(textAlign = TextAlign.Start, fontWeight = FontWeight(700)), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val note = words.change(row)
                    Text(plural(row.plays, "play") + if (note.isNotEmpty()) " · $note" else "", style = line(ink.copy(alpha = 0.8f), 14).copy(textAlign = TextAlign.Start))
                }
            }
        }
    }
}

@Composable
private fun SlideContent(recap: Recap, words: StoryWords, slide: StorySlide, ink: Color, onReplay: () -> Unit, onClose: () -> Unit) {
    val story = recap.story
    val name = words.name
    when (slide.type) {
        "intro" -> Centered {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                (recap.top.albums + recap.top.tracks).filter { it.image != null }.take(4).forEach { Cover(it.image, it.label, size = 64.dp) }
            }
            Title(name, ink, 48)
            if (recap.kind == "month") Line(recap.label.substringAfter(' '), ink.copy(alpha = 0.8f), 22)
            Line(
                when {
                    recap.soFar -> "So far, anyway. $name isn't finished yet."
                    recap.partial -> "From your very first recorded play."
                    else -> "Here's what you were really up to ${if (words.here == "this year") "all year" else "in $name"}."
                },
                ink,
            )
        }
        "opener" -> story.opener?.let { opener ->
            Centered {
                Kicker("$name opened with", ink)
                Cover(opener.image, opener.title, size = 180.dp)
                Title(opener.title, ink, 28)
                Line(opener.artist, ink)
                Line("${day(opener.date)} at ${opener.time}", ink.copy(alpha = 0.8f), 15)
            }
        }
        "genres" -> recap.genres.firstOrNull()?.let { top ->
            Centered {
                Title("$name sounded like ${top.name}", ink, 28)
                recap.genres.take(5).forEach { genre ->
                    Column(Modifier.fillMaxWidth()) {
                        Box(Modifier.fillMaxWidth(genre.share.toFloat().coerceIn(0.12f, 1f)).height(34.dp).clip(CircleShape).background(ink.copy(alpha = 0.18f)), contentAlignment = Alignment.CenterStart) {
                            Text(genre.name, Modifier.padding(start = 14.dp), style = line(ink, 16).copy(fontWeight = FontWeight(700)))
                        }
                        Text("${(genre.share * 100).toInt()}% of known genres, ${listening(genre.seconds)}", style = line(ink.copy(alpha = 0.8f), 13).copy(textAlign = TextAlign.Start))
                    }
                }
                if (recap.coverage.genrePct < 100) Line("Genres are known for ${recap.coverage.genrePct}% of your plays.", ink.copy(alpha = 0.8f), 13)
            }
        }
        "artist_countdown" -> Centered {
            Title("Your top ${minOf(5, story.topArtists.size)} artists", ink, 26)
            Countdown(story.topArtists, words, ink) { it.label }
            Line("And number one is…", ink, 20)
        }
        "top_artist" -> story.topArtists.firstOrNull()?.let { artist ->
            Box(Modifier.fillMaxSize()) {
                Cover(artist.image, artist.label, Modifier.align(Alignment.TopCenter), size = 240.dp, shape = CircleShape)
                Column(Modifier.align(Alignment.BottomCenter), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Kicker("Your number one artist", ink)
                    Title(artist.label, ink, 40)
                    Line("${count(artist.plays)} ${if (artist.plays == 1) "play" else "plays"}", ink, 24)
                    val note = words.change(artist)
                    Line("About ${listening(artist.seconds)} together${if (note.isNotEmpty()) ". $note" else ""}.", ink)
                }
            }
        }
        "loyalty" -> story.loyalty?.let { loyalty ->
            Centered {
                val whenText = if (words.here == "this year") "this year" else "in $name"
                Title(
                    if (loyalty.oneIn < 2) "${loyalty.artist.label} took over $whenText" else "1 in ${count(loyalty.oneIn)} of your plays $whenText was ${loyalty.artist.label}",
                    ink,
                    26,
                )
                val cells = loyalty.oneIn.coerceIn(2, 12)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    repeat(cells) { i -> Box(Modifier.size(18.dp).clip(CircleShape).background(if (i == cells - 1) ink else ink.copy(alpha = 0.25f))) }
                }
                Line("That's ${loyalty.percent}% of everything you played.", ink)
            }
        }
        "track_countdown" -> Centered {
            Title("The songs on repeat", ink, 26)
            Countdown(recap.top.tracks, words, ink) { it.label }
            Line("One song beat them all…", ink, 20)
        }
        "top_track" -> recap.top.tracks.firstOrNull()?.let { track ->
            Centered {
                Kicker("Your song of $name", ink)
                Cover(track.image, track.label, size = 200.dp, shape = CircleShape)
                Title(track.label, ink, 28)
                Line(track.artist.orEmpty(), ink)
                Line("${count(track.plays)} ${if (track.plays == 1) "play" else "plays"}", ink, 24)
                words.change(track).takeIf { it.isNotEmpty() }?.let { Line(it, ink.copy(alpha = 0.8f), 15) }
            }
        }
        "obsession" -> story.obsession?.let { obsession ->
            Centered {
                Kicker("On ${day(obsession.date)} you played", ink)
                Title(obsession.title, ink, 28)
                Text("${obsession.plays}", style = big(ink, 110))
                Line("times in one day", ink, 22)
                Line(if (obsession.plays >= 25) "Are you okay?" else if (obsession.plays >= 12) "That song had you." else "It got stuck in your head.", ink)
            }
        }
        "binge" -> story.binge?.let { binge ->
            Centered {
                Kicker("Your longest sitting", ink)
                Text(listening(binge.seconds), style = big(ink, 56))
                Box(Modifier.fillMaxWidth((binge.seconds / (16f * 3600)).coerceIn(0.18f, 1f)).height(12.dp).clip(CircleShape).background(ink))
                Line("${day(binge.date)}: ${plural(binge.plays, "play")} with barely a break" + if (binge.topArtist.isNotBlank()) ", mostly ${binge.topArtist}." else ".", ink)
            }
        }
        "album_run" -> story.albumRun?.let { run ->
            Centered {
                Cover(run.image, run.title, size = 170.dp)
                Title(run.title, ink, 28)
                Line("${plural(run.tracks, "track")} in a row", ink, 22)
                Line("Out of the ${plural(run.of, "track")} you've played from it.", ink.copy(alpha = 0.8f), 15)
                Line("In one sitting on ${day(run.date)}. Respect.", ink)
            }
        }
        "new_artists" -> Centered {
            Title("${plural(recap.newArtists.size, "artist")} you'd never played before", ink, 26)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                recap.newArtists.take(4).forEach { artist ->
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(72.dp)) {
                        Cover(artist.image, artist.label, size = 64.dp, shape = CircleShape)
                        Text(artist.label, style = line(ink, 12), maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
            recap.discovery?.takeIf { it.plays >= 5 }?.let { Line("${it.label} came out of nowhere: ${plural(it.plays, "play")}.", ink) }
        }
        "then_now" -> Centered {
            Title("${words.previous} vs $name", ink, 26)
            val rows = buildList {
                story.movers?.rise?.let { add(Triple("↑ Climbing", it, "+${plural(it.delta, "play")} vs ${words.previous}")) }
                story.movers?.fall?.let { add(Triple("↓ Cooling off", it, "-${plural(kotlin.math.abs(it.delta), "play")} vs ${words.previous}")) }
                story.comeback?.let { add(Triple("↻ Back again", it, "${plural(it.plays, "play")}, none in ${words.previous}")) }
                story.dropped?.let { add(Triple("× Gone quiet", it, "${plural(it.previousPlays ?: 0, "play")} in ${words.previous}, none in $name")) }
            }
            rows.take(4).forEach { (label, artist, note) ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Cover(artist.image, artist.label, size = 52.dp, shape = CircleShape)
                    Column(Modifier.weight(1f)) {
                        Text(label, style = line(ink.copy(alpha = 0.8f), 13).copy(textAlign = TextAlign.Start))
                        Text(artist.label, style = line(ink, 18).copy(textAlign = TextAlign.Start, fontWeight = FontWeight(700)), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(note, style = line(ink.copy(alpha = 0.8f), 13).copy(textAlign = TextAlign.Start))
                    }
                }
            }
        }
        "biggest_month" -> story.biggestMonth?.let { month ->
            Centered {
                Kicker("Your biggest month", ink)
                Title(month.label.substringBefore(' '), ink, 52)
                Line("${count(month.plays)} ${if (month.plays == 1) "play" else "plays"}", ink, 24)
            }
        }
        "clock" -> story.clock?.let { clock ->
            Centered {
                Title("%02d:00 was your hour".format(clock.peakHour), ink, 28)
                val max = clock.hours.maxOrNull()?.coerceAtLeast(1) ?: 1
                Row(Modifier.fillMaxWidth().height(120.dp), horizontalArrangement = Arrangement.spacedBy(2.dp), verticalAlignment = Alignment.Bottom) {
                    clock.hours.forEachIndexed { hour, plays ->
                        Box(
                            Modifier.weight(1f).fillMaxHeight((plays.toFloat() / max).coerceIn(0.04f, 1f)).clip(CircleShape)
                                .background(if (hour == clock.peakHour) ink else ink.copy(alpha = 0.3f)),
                        )
                    }
                }
                val label = when {
                    clock.peakHour >= 22 || clock.peakHour < 5 -> "Night shift."
                    clock.peakHour < 11 -> "Early start."
                    clock.peakHour < 18 -> "Prime time."
                    else -> "Evening ritual."
                }
                Line("$label ${plural(clock.hours.getOrElse(clock.peakHour) { 0 }, "play")} started around then.", ink)
            }
        }
        "personality" -> Centered {
            Kicker("$name made you", ink)
            Title(story.personality.name, ink, 40)
            Line(story.personality.reason, ink)
        }
        "time" -> Centered {
            Kicker("Estimated listening time", ink)
            Text(listening(recap.totals.seconds), style = big(ink, 52))
            val previous = recap.previous
            val versus = if (previous != null && !recap.soFar && story.comparable && previous.totals.seconds > 0) {
                val percent = ((recap.totals.seconds - previous.totals.seconds) * 100.0 / previous.totals.seconds).toInt()
                if (percent == 0) "Exactly as much as ${words.previous}." else "${if (percent > 0) "+" else ""}$percent% vs ${words.previous}."
            } else {
                ""
            }
            Line("${plural(recap.totals.plays, "play")} of music" + if (versus.isNotEmpty()) ". $versus" else ".", ink)
            story.comparisons.forEach { Line("That's ${count(it.value)} ${it.unit}", ink.copy(alpha = 0.9f), 16) }
            if (recap.coverage.lengthPct < 100) Line("Track lengths are known for ${recap.coverage.lengthPct}% of plays, so the real time is higher.", ink.copy(alpha = 0.8f), 13)
        }
        "outro" -> Centered {
            if (recap.totals.plays == 0) {
                Title("Nothing played in $name", ink, 28)
            } else {
                Title("That was ${recap.label}${if (recap.soFar) ", so far" else ""}", ink, 28)
                Column(Modifier.fillMaxWidth().clip(io.github.catchow0.d2n.ui.theme.D2nShapes.Cell).background(ink.copy(alpha = 0.12f)).padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Fact("Listening time", listening(recap.totals.seconds), ink)
                    Fact("Plays", count(recap.totals.plays), ink)
                    story.topArtists.firstOrNull()?.let { Fact("Top artist", it.label, ink) }
                    recap.top.tracks.firstOrNull()?.let { Fact("Top track", it.label, ink) }
                    Fact("You were", story.personality.name, ink)
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (recap.totals.plays > 0) D2nButton("Replay", onReplay, small = true)
                D2nButton("Close", onClose, kind = ButtonKind.Ghost, small = true)
            }
        }
    }
}

@Composable
private fun Fact(label: String, value: String, ink: Color) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, Modifier.weight(1f), style = line(ink.copy(alpha = 0.75f), 14).copy(textAlign = TextAlign.Start))
        Text(value, style = line(ink, 15).copy(textAlign = TextAlign.End, fontWeight = FontWeight(700)), maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}
