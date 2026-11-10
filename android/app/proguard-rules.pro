# R8 rules of the app itself. The libraries ship theirs (consumer rules):
# OkHttp, Retrofit, kotlinx.serialization, Navigation, Coil, Media3 and Tink.

# Readable stack traces in crash reports: keep the file names and line numbers,
# without the source file names in the APK.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
