# syntax=docker/dockerfile:1
# The Android app's build, the same in Jenkins and on the owner's PC.
# android/scripts/build-apk.sh runs it:
#   docker buildx build --file android/Dockerfile --target out \
#     --output type=local,dest=dist/android \
#     --secret id=keystore,src=<release.jks> \
#     --secret id=keystore_password,env=D2N_KEYSTORE_PASSWORD \
#     --build-arg D2N_VERSION=… --build-arg D2N_COMMIT=… --build-arg D2N_BUILT_AT=… \
#     android
# The key and its password arrive as build secrets: mounted for one command,
# never stored in a layer. The APK comes out through --output, with no bind
# mount, which also works when the Jenkins agent runs in a container.

FROM eclipse-temurin:21.0.13_9-jdk-noble AS sdk
ENV ANDROID_HOME=/opt/android-sdk
# commandlinetools-linux-16111833 (cmdline-tools 23.0): SHA-1 as listed in
# Google's repository2-3.xml, SHA-256 computed from that download.
ARG CMDLINE_TOOLS=16111833
ARG CMDLINE_TOOLS_SHA256=0877a1d048fe4a24efe2eff536ca4223f7adeb58648bb81909d33c446918cfa8
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl unzip \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL -o /tmp/tools.zip "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" \
 && echo "${CMDLINE_TOOLS_SHA256}  /tmp/tools.zip" | sha256sum -c - \
 && mkdir -p "$ANDROID_HOME/cmdline-tools" \
 && unzip -q /tmp/tools.zip -d "$ANDROID_HOME/cmdline-tools" \
 && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" \
 && rm /tmp/tools.zip
ENV PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
# compileSdk 37 (current AndroidX needs it; the app targets 36) and the
# build-tools app/build.gradle.kts names.
RUN yes | sdkmanager --licenses > /dev/null \
 && sdkmanager --install "platforms;android-37.0" "build-tools;36.1.0" > /dev/null

FROM sdk AS build
WORKDIR /src
# The wrapper and the settings first, so that a change in app/ keeps them cached.
COPY gradlew settings.gradle.kts build.gradle.kts gradle.properties ./
COPY gradle gradle
COPY app app
ARG D2N_VERSION
ARG D2N_COMMIT
ARG D2N_BUILT_AT
RUN --mount=type=cache,target=/root/.gradle \
    --mount=type=secret,id=keystore,required=true \
    --mount=type=secret,id=keystore_password,required=true \
    D2N_KEYSTORE_FILE=/run/secrets/keystore \
    D2N_KEYSTORE_PASSWORD="$(cat /run/secrets/keystore_password)" \
    sh ./gradlew --no-daemon --console=plain \
      -Pd2n.version="$D2N_VERSION" -Pd2n.commit="$D2N_COMMIT" -Pd2n.builtAt="$D2N_BUILT_AT" \
      testDebugUnitTest packageD2n

FROM scratch AS out
COPY --from=build /src/app/build/d2n/ /
