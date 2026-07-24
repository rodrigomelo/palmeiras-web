import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val keystorePropertiesFile = rootProject.file("keystore.properties")
val keystoreProperties = Properties().apply {
    if (keystorePropertiesFile.isFile) {
        keystorePropertiesFile.inputStream().use(::load)
    }
}

android {
    namespace = "com.palmeiras.agenda"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.palmeiras.agenda"
        minSdk = 26
        targetSdk = 36
        versionCode = 56
        versionName = "1.2.0"
    }

    signingConfigs {
        if (keystorePropertiesFile.isFile) {
            create("release") {
                storeFile = rootProject.file(
                    requireNotNull(keystoreProperties.getProperty("storeFile")) {
                        "storeFile is missing from keystore.properties"
                    }
                )
                storePassword = requireNotNull(keystoreProperties.getProperty("storePassword")) {
                    "storePassword is missing from keystore.properties"
                }
                keyAlias = requireNotNull(keystoreProperties.getProperty("keyAlias")) {
                    "keyAlias is missing from keystore.properties"
                }
                keyPassword = requireNotNull(keystoreProperties.getProperty("keyPassword")) {
                    "keyPassword is missing from keystore.properties"
                }
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    jvmToolchain(17)
}

val verifyReleaseSigning by tasks.registering {
    group = "verification"
    description = "Fails before bundling when the Google Play upload key is unavailable."
    doLast {
        check(keystorePropertiesFile.isFile) {
            "Release bundle is not signed. Restore the Google Play upload key and create " +
                "apps/android/keystore.properties from keystore.properties.example."
        }
    }
}

tasks.matching { it.name == "signReleaseBundle" }.configureEach {
    dependsOn(verifyReleaseSigning)
}
