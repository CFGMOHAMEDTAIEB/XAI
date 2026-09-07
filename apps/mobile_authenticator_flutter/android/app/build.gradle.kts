plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val signingPath = System.getenv("XAI_ANDROID_KEYSTORE")
val signingReady = !signingPath.isNullOrBlank() && listOf("XAI_ANDROID_STORE_PASSWORD", "XAI_ANDROID_KEY_ALIAS", "XAI_ANDROID_KEY_PASSWORD").all { !System.getenv(it).isNullOrBlank() }
val allowDebugSigning = System.getenv("XAI_ALLOW_DEBUG_SIGNING") == "true"
gradle.taskGraph.whenReady {
    if (allTasks.any { it.name.contains("Release") } && !signingReady && !allowDebugSigning) {
        throw GradleException("Release requires XAI_ANDROID_KEYSTORE, XAI_ANDROID_STORE_PASSWORD, XAI_ANDROID_KEY_ALIAS, XAI_ANDROID_KEY_PASSWORD; debug signing must be explicitly opted into for development distribution.")
    }
}
android {
    namespace = "com.example.xai_compress_authenticator"
    compileSdk = 37
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        manifestPlaceholders["allowCleartext"] = "false"
        applicationId = "com.example.xai_compress_authenticator"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (signingReady) {
            create("production") {
                storeFile = file(signingPath!!)
                storePassword = System.getenv("XAI_ANDROID_STORE_PASSWORD")
                keyAlias = System.getenv("XAI_ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("XAI_ANDROID_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        debug { manifestPlaceholders["allowCleartext"] = "true" }
        release {
            manifestPlaceholders["allowCleartext"] = "false"
            if (signingReady) signingConfig = signingConfigs.getByName("production")
            else if (allowDebugSigning) signingConfig = signingConfigs.getByName("debug")
        }
    }
}


kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}



flutter {
    source = "../.."
}
