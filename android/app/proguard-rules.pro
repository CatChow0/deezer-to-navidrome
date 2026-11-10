# Keep serialization model classes and their generated serializers.
-keep class io.github.catchow0.d2n.data.** { *; }
-keepclassmembers class io.github.catchow0.d2n.data.** { *; }
-keepattributes *Annotation*, Signature, Exceptions, InnerClasses, EnclosingMethod, StackMapTable, LineNumberTable

# Retrofit and OkHttp.
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn javax.annotation.**
-keep class retrofit2.** { *; }
-keepattributes RuntimeVisibleAnnotations,RuntimeVisibleParameterAnnotations
-keepclasseswithmembers class * {
    @retrofit2.http.* <methods>;
}
-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class retrofit2.** { *; }

# Kotlin coroutines and serialization.
-keep class kotlinx.serialization.** { *; }
-keepclassmembers class * {
    @kotlinx.serialization.SerialName <fields>;
}
-keep class kotlin.Metadata { *; }

# Media3 and Tink are referenced dynamically at runtime.
-keep class androidx.media3.** { *; }
-keep class com.google.crypto.tink.** { *; }
-keep class com.google.crypto.tink.aead.** { *; }

# Coil and Compose bindings.
-keep class coil.** { *; }