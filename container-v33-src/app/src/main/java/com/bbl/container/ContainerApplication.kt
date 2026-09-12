package com.bbl.container

import android.app.Application

class ContainerApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        // O motor virtual é inicializado somente depois que a tela principal já foi desenhada.
        // Isso evita travar a abertura da aplicação em algumas TV Boxes.
    }
}
