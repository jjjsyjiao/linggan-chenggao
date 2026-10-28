pluginManagement {
    val flutterSdkPath =
        run {
            val properties = java.util.Properties()
            // Flutter writes UTF-8 paths; Properties.load(InputStream) decodes
            // ISO-8859-1 and corrupts a SDK path containing Chinese characters.
            file("local.properties").reader(Charsets.UTF_8).use { properties.load(it) }
            // The Flutter plugin loader reads this file again via InputStream.
            // Store standard Java Unicode escapes so both readers see the same
            // paths, including when this checkout or the SDK has a Chinese name.
            file("local.properties").outputStream().use { properties.store(it, null) }
            val flutterSdkPath = properties.getProperty("flutter.sdk")
            require(flutterSdkPath != null) { "flutter.sdk not set in local.properties" }
            flutterSdkPath
        }

    includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    id("com.android.application") version "9.1.0" apply false
    id("org.jetbrains.kotlin.android") version "2.4.0" apply false
}

include(":app")
