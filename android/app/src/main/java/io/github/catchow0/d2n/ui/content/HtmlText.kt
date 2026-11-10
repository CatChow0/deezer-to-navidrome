package io.github.catchow0.d2n.ui.content

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** A piece of the notes or the help, as native text. */
sealed interface HtmlBlock {
    data class Heading(val level: Int, val text: AnnotatedString) : HtmlBlock
    data class Paragraph(val text: AnnotatedString) : HtmlBlock
    data class Item(val marker: String, val depth: Int, val text: AnnotatedString) : HtmlBlock
    data class Code(val text: String) : HtmlBlock
    data class Table(val rows: List<List<AnnotatedString>>, val header: Boolean) : HtmlBlock
}

private val TOKEN = Regex("""<(/?)([a-zA-Z0-9]+)([^>]*)>|([^<]+)""")
private val HREF = Regex("""href\s*=\s*"([^"]*)"""")
private val ENTITIES = mapOf(
    "amp" to "&", "lt" to "<", "gt" to ">", "quot" to "\"", "apos" to "'", "nbsp" to " ",
    "rarr" to "→", "larr" to "←", "mdash" to "—", "ndash" to "–", "hellip" to "…", "middot" to "·",
    "rsquo" to "’", "lsquo" to "‘", "rdquo" to "”", "ldquo" to "“", "times" to "×",
)
private val BLOCKS = setOf("p", "div", "section", "figure", "figcaption", "h1", "h2", "h3", "h4", "h5", "li", "ul", "ol", "table", "tr", "pre", "header")

fun decodeEntities(text: String): String = Regex("""&(#x?[0-9a-fA-F]+|[a-zA-Z]+);""").replace(text) { match ->
    val name = match.groupValues[1]
    when {
        name.startsWith("#x") || name.startsWith("#X") -> name.drop(2).toIntOrNull(16)?.let { String(Character.toChars(it)) }
        name.startsWith("#") -> name.drop(1).toIntOrNull()?.let { String(Character.toChars(it)) }
        else -> ENTITIES[name]
    } ?: match.value
}

/**
 * The HTML of a note or a help section, in blocks: headings, paragraphs, list
 * items, code and tables, with bold, italic, code and links inside. Anything
 * else (classes, buttons, spans) keeps its text.
 */
fun parseHtml(html: String): List<HtmlBlock> {
    val blocks = mutableListOf<HtmlBlock>()
    val lists = ArrayDeque<IntArray>() // [ordered (1/0), count]
    var builder = AnnotatedString.Builder()
    var open = 0
    var heading = 0
    var marker: String? = null
    var depth = 0
    var pre: StringBuilder? = null
    var rows: MutableList<MutableList<AnnotatedString>>? = null
    var header = false
    var cell: AnnotatedString.Builder? = null

    fun target() = cell ?: builder

    fun trimmed(built: AnnotatedString): AnnotatedString {
        val end = built.text.indexOfLast { !it.isWhitespace() }
        val start = built.text.indexOfFirst { !it.isWhitespace() }
        return if (end < 0) AnnotatedString("") else built.subSequence(start, end + 1)
    }

    fun flush() {
        val text = trimmed(builder.toAnnotatedString())
        if (text.isNotEmpty()) {
            blocks += when {
                heading > 0 -> HtmlBlock.Heading(heading, text)
                marker != null -> HtmlBlock.Item(marker!!, depth, text)
                else -> HtmlBlock.Paragraph(text)
            }
        }
        builder = AnnotatedString.Builder()
        open = 0
        heading = 0
        marker = null
    }

    fun append(raw: String) {
        pre?.let {
            it.append(decodeEntities(raw))
            return
        }
        val target = target()
        var text = decodeEntities(raw).replace(Regex("\\s+"), " ")
        if (target.length == 0 || target.toAnnotatedString().text.endsWith(" ") || target.toAnnotatedString().text.endsWith("\n")) text = text.trimStart()
        if (text.isNotEmpty()) target.append(text)
    }

    val source = html.replace(Regex("<!--.*?-->", RegexOption.DOT_MATCHES_ALL), "")
    for (match in TOKEN.findAll(source)) {
        val text = match.groupValues[4]
        if (text.isNotEmpty()) {
            append(text)
            continue
        }
        val closing = match.groupValues[1] == "/"
        val tag = match.groupValues[2].lowercase()
        val attrs = match.groupValues[3]
        if (pre != null && !(closing && tag == "pre")) continue
        if (!closing) {
            if (tag in BLOCKS && cell == null) flush()
            when (tag) {
                "h1", "h2", "h3", "h4", "h5" -> heading = tag.drop(1).toInt()
                "ul" -> lists.addLast(intArrayOf(0, 0))
                "ol" -> lists.addLast(intArrayOf(1, 0))
                "li" -> {
                    val list = lists.lastOrNull()
                    depth = (lists.size - 1).coerceAtLeast(0)
                    marker = if (list != null && list[0] == 1) "${++list[1]}." else "•"
                }
                "pre" -> pre = StringBuilder()
                "br" -> target().append("\n")
                "table" -> {
                    rows = mutableListOf()
                    header = false
                }
                "tr" -> rows?.add(mutableListOf())
                "td", "th" -> {
                    if (tag == "th") header = true
                    cell = AnnotatedString.Builder()
                }
                "b", "strong" -> {
                    target().pushStyle(SpanStyle(fontWeight = FontWeight.Bold, color = D2nColors.Text))
                    if (cell == null) open++
                }
                "i", "em" -> {
                    target().pushStyle(SpanStyle(fontStyle = FontStyle.Italic))
                    if (cell == null) open++
                }
                "code" -> {
                    target().pushStyle(SpanStyle(fontFamily = FontFamily.Monospace, background = D2nColors.GlassHover, color = D2nColors.Mint))
                    if (cell == null) open++
                }
                "a" -> {
                    val href = HREF.find(attrs)?.groupValues?.get(1).orEmpty()
                    if (href.startsWith("http://") || href.startsWith("https://")) {
                        target().pushLink(LinkAnnotation.Url(href, TextLinkStyles(SpanStyle(color = D2nColors.Cyan, textDecoration = TextDecoration.Underline))))
                    } else {
                        target().pushStyle(SpanStyle(color = D2nColors.Cyan))
                    }
                    if (cell == null) open++
                }
            }
        } else {
            when (tag) {
                "pre" -> {
                    blocks += HtmlBlock.Code(pre.toString().trimEnd())
                    pre = null
                }
                "td", "th" -> {
                    cell?.let { rows?.lastOrNull()?.add(trimmed(it.toAnnotatedString())) }
                    cell = null
                }
                "table" -> {
                    rows?.filter { it.isNotEmpty() }?.takeIf { it.isNotEmpty() }?.let { blocks += HtmlBlock.Table(it, header) }
                    rows = null
                }
                "ul", "ol" -> {
                    flush()
                    lists.removeLastOrNull()
                }
                "b", "strong", "i", "em", "code", "a" -> if (cell != null) {
                    runCatching { cell!!.pop() }
                } else if (open > 0) {
                    builder.pop()
                    open--
                }
                else -> if (tag in BLOCKS) flush()
            }
        }
    }
    flush()
    return blocks
}

@Composable
fun HtmlContent(blocks: List<HtmlBlock>, modifier: Modifier = Modifier, color: Color = D2nColors.TextSoft) {
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        blocks.forEach { block ->
            when (block) {
                is HtmlBlock.Heading -> Text(
                    block.text,
                    Modifier.padding(top = 6.dp).semantics { heading() },
                    style = if (block.level <= 3) MaterialTheme.typography.titleMedium else MaterialTheme.typography.titleSmall,
                    color = D2nColors.Text,
                )
                is HtmlBlock.Paragraph -> Text(block.text, style = MaterialTheme.typography.bodyMedium, color = color)
                is HtmlBlock.Item -> Row(Modifier.padding(start = (block.depth * 16).dp)) {
                    Text(block.marker, Modifier.width(22.dp), style = MaterialTheme.typography.bodyMedium, color = D2nColors.Cyan)
                    Text(block.text, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = color)
                }
                is HtmlBlock.Code -> Text(
                    block.text,
                    Modifier
                        .fillMaxWidth()
                        .background(D2nColors.GlassRaised, D2nShapes.Control)
                        .border(1.dp, D2nColors.Line, D2nShapes.Control)
                        .horizontalScroll(rememberScrollState())
                        .padding(12.dp),
                    style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                    color = D2nColors.Mint,
                    softWrap = false,
                )
                is HtmlBlock.Table -> Column(
                    Modifier.fillMaxWidth().background(D2nColors.GlassRaised, D2nShapes.Control).border(1.dp, D2nColors.Line, D2nShapes.Control).padding(8.dp),
                ) {
                    block.rows.forEachIndexed { i, row ->
                        if (i > 0) HorizontalDivider(color = D2nColors.Line)
                        Row(Modifier.padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            row.forEach { cell ->
                                Text(
                                    cell,
                                    Modifier.weight(1f),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = if (block.header && i == 0) D2nColors.Text else color,
                                    fontWeight = if (block.header && i == 0) FontWeight.SemiBold else null,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
