pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "d2n"
include(":app")
// The baseline profile's generator runs on a PC with an emulator. The Docker
// build's context holds app/ alone, so there it is left out.
if (file("baselineprofile").isDirectory) include(":baselineprofile")
