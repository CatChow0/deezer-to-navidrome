package io.github.catchow0.d2n.data

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive

/**
 * An ID the server sends as a number or as text, depending on where it comes
 * from: a Deezer track is 3135556 in a playlist's rows and "3135556" in a
 * search. The app always reads it as text.
 */
object FlexibleIdSerializer : KSerializer<String> {
    override val descriptor = PrimitiveSerialDescriptor("FlexibleId", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): String {
        val json = decoder as? JsonDecoder ?: return decoder.decodeString()
        val element = json.decodeJsonElement()
        return if (element is JsonPrimitive && element !is JsonNull) element.content else ""
    }

    override fun serialize(encoder: Encoder, value: String) = encoder.encodeString(value)
}

typealias FlexibleId = @Serializable(with = FlexibleIdSerializer::class) String
