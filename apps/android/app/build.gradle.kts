plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.palmeiras.agenda"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.palmeiras.agenda"
        minSdk = 26
        targetSdk = 35
        versionCode = 37
        versionName = "1.1.37"
    }
}
