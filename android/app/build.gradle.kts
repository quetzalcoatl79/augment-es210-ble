plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.lamapp.augment"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.lamapp.augment"
        minSdk = 33          // téléphone de l'utilisateur = Android 16 (API 36)
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // Aucune dépendance externe : on n'utilise que les APIs Android (BLE natif).
}
