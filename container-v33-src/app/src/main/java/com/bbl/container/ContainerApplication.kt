package com.bbl.container

import android.app.Application
import android.content.Context
import android.util.Log

class ContainerApplication : Application() {
    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(base)
        // O BlackBox precisa ser anexado nesta fase do processo Android.
        // Somente o attach acontece aqui; a criação pesada do motor fica para depois da UI.
        runCatching { VirtualEngineProvider.create().attach(base) }
            .onFailure { Log.e("BBLContainer", "Falha no attach do motor virtual", it) }
    }

    override fun onCreate() {
        super.onCreate()
    }
}
