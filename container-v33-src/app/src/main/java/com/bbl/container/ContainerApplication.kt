package com.bbl.container

import android.app.Application
import android.content.Context
import android.util.Log
import top.niunaijun.blackbox.BlackBoxCore

class ContainerApplication : Application() {
    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(base)
        try {
            BlackBoxCore.get().closeCodeInit()
            BlackBoxCore.get().onBeforeMainApplicationAttach(this, base)
            VirtualEngineProvider.create().attach(base)
            BlackBoxCore.get().onAfterMainApplicationAttach(this, base)
        } catch (t: Throwable) {
            Log.e("BBLContainer", "Engine attach failed", t)
        }
    }

    override fun onCreate() {
        super.onCreate()
        try {
            VirtualEngineProvider.create().init(this)
            Log.i("BBLContainer", "Virtual engine initialized")
        } catch (t: Throwable) {
            Log.e("BBLContainer", "Virtual engine init failed", t)
        }
    }
}
