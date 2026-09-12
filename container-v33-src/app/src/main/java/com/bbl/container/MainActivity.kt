package com.bbl.container

import android.app.Activity
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.ViewGroup
import android.widget.*
import java.io.File
import kotlin.concurrent.thread

class MainActivity : Activity() {
    private val api by lazy { ApiClient(getString(R.string.server_url)) }
    private lateinit var status: TextView
    private lateinit var code: EditText
    private lateinit var appsBox: LinearLayout
    private lateinit var activate: Button
    private lateinit var refresh: Button
    private val prefs by lazy { getSharedPreferences("p", 0) }
    private val appState by lazy { getSharedPreferences("virtual_app_state", 0) }
    @Volatile private var engineReady = false
    @Volatile private var engineError: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.setBackgroundColor(Color.rgb(13, 15, 19))
        buildUi()

        activate.setOnClickListener { activateDevice() }
        refresh.setOnClickListener { loadCatalog() }

        if (!prefs.getString("token", null).isNullOrBlank() && !prefs.getString("device_id", null).isNullOrBlank()) {
            status.text = "Conectando ao painel..."
            loadCatalog()
        } else {
            status.text = "Digite o código de ativação para liberar os aplicativos."
        }

        Handler(Looper.getMainLooper()).postDelayed({ bootstrapEngine() }, 1200)
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(28), dp(24), dp(28), dp(24))
            setBackgroundColor(Color.rgb(13, 15, 19))
        }
        val title = TextView(this).apply {
            text = "BBL CONTAINER"
            setTextColor(Color.rgb(245, 196, 81))
            textSize = 32f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        val subtitle = TextView(this).apply {
            text = "Aplicativos liberados pelo seu painel"
            setTextColor(Color.LTGRAY)
            textSize = 17f
            setPadding(0, dp(4), 0, dp(18))
        }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        code = EditText(this).apply {
            hint = "Código de ativação"
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            isSingleLine = true
            setPadding(dp(14), dp(8), dp(14), dp(8))
        }
        activate = Button(this).apply { text = "ATIVAR"; isFocusable = true }
        refresh = Button(this).apply { text = "ATUALIZAR APPS"; isFocusable = true }
        row.addView(code, LinearLayout.LayoutParams(dp(340), ViewGroup.LayoutParams.WRAP_CONTENT))
        row.addView(activate, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { leftMargin = dp(10) })
        row.addView(refresh, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { leftMargin = dp(10) })

        status = TextView(this).apply {
            setTextColor(Color.WHITE)
            textSize = 18f
            setPadding(0, dp(14), 0, dp(14))
        }
        val section = TextView(this).apply {
            text = "APLICATIVOS"
            setTextColor(Color.rgb(245, 196, 81))
            textSize = 20f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(0, dp(4), 0, dp(8))
        }
        appsBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val scroll = ScrollView(this).apply { addView(appsBox) }

        root.addView(title)
        root.addView(subtitle)
        root.addView(row)
        root.addView(status)
        root.addView(section)
        root.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
    }

    private fun activateDevice() {
        val activationCode = code.text.toString().trim()
        if (activationCode.isBlank()) {
            status.text = "Informe o código de ativação."
            return
        }
        status.text = "Ativando dispositivo..."
        activate.isEnabled = false
        thread {
            runCatching {
                val androidId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID).orEmpty()
                val did = if (androidId.isBlank()) "${android.os.Build.MANUFACTURER}-${android.os.Build.MODEL}" else androidId
                api.activate(activationCode, did)
            }.onSuccess { s ->
                prefs.edit().putString("token", s.token).putString("device_id", s.deviceId).apply()
                runOnUiThread {
                    activate.isEnabled = true
                    status.text = "Ativado. Buscando aplicativos..."
                    loadCatalog()
                }
            }.onFailure {
                runOnUiThread { activate.isEnabled = true }
                showError(it)
            }
        }
    }

    private fun loadCatalog() {
        val token = prefs.getString("token", null)
        val did = prefs.getString("device_id", null)
        if (token.isNullOrBlank() || did.isNullOrBlank()) {
            status.text = "Ative este aparelho primeiro."
            return
        }
        status.text = "Sincronizando aplicativos..."
        refresh.isEnabled = false
        thread {
            runCatching { api.catalog(did, token) }.onSuccess { apps ->
                runOnUiThread {
                    refresh.isEnabled = true
                    showApps(apps)
                    status.text = if (apps.isEmpty()) "Nenhum aplicativo liberado para este aparelho no painel." else "${apps.size} aplicativo(s) liberado(s)."
                }
            }.onFailure {
                runOnUiThread { refresh.isEnabled = true }
                showError(it)
            }
        }
    }

    private fun showApps(apps: List<CatalogApp>) {
        appsBox.removeAllViews()
        if (apps.isEmpty()) {
            appsBox.addView(TextView(this).apply {
                text = "Quando você liberar aplicativos no painel, eles aparecerão aqui."
                setTextColor(Color.LTGRAY)
                textSize = 18f
                setPadding(dp(12), dp(18), dp(12), dp(18))
            })
            return
        }
        apps.forEach { app ->
            val button = Button(this).apply {
                text = "${app.name}\n${app.packageName}  •  ${app.version}\nBAIXAR / ABRIR"
                textSize = 18f
                gravity = Gravity.START or Gravity.CENTER_VERTICAL
                isFocusable = true
                setPadding(dp(20), dp(14), dp(20), dp(14))
                setOnClickListener { prepareAndRun(app) }
            }
            appsBox.addView(button, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) })
        }
    }

    private fun bootstrapEngine() {
        thread(name = "bbl-engine-init") {
            runCatching {
                val engine = VirtualEngineProvider.create()
                engine.attach(applicationContext)
                engine.init(applicationContext)
                check(engine.status().available) { engine.status().details }
            }.onSuccess {
                engineReady = true
                runOnUiThread {
                    if (status.text.toString().contains("motor", ignoreCase = true)) status.text = "Motor virtual pronto."
                }
            }.onFailure {
                engineError = "Motor virtual indisponível: ${it.message ?: it.javaClass.simpleName}"
                Log.e("BBLContainer", engineError, it)
                runOnUiThread {
                    if (status.text.isNullOrBlank()) status.text = engineError
                }
            }
        }
    }

    private fun prepareAndRun(a: CatalogApp) {
        if (!engineReady) {
            status.text = engineError ?: "Motor virtual ainda está iniciando. Aguarde alguns segundos e tente novamente."
            return
        }
        val engine = VirtualEngineProvider.create()
        status.text = "Baixando ${a.name}..."
        thread {
            val f = File(filesDir, "virtual_apps/${a.id}.apk")
            f.parentFile?.mkdirs()
            runCatching {
                if (!f.exists() || (a.sha256.isNotBlank() && !ApiClient.sha256(f).equals(a.sha256, true))) api.download(a.downloadUrl, f)
                if (a.sha256.isNotBlank()) require(ApiClient.sha256(f).equals(a.sha256, true)) { "Arquivo baixado não passou na verificação SHA-256" }
                val parsedPkg = packageManager.getPackageArchiveInfo(f.absolutePath, PackageManager.GET_META_DATA)?.packageName
                require(parsedPkg == a.packageName) { "APK inválido: pacote ${parsedPkg ?: "desconhecido"}, esperado ${a.packageName}" }
                runOnUiThread { status.text = "Instalando ${a.name} dentro do BBL Container..." }
                engine.installVirtual(f, a.packageName).getOrThrow()
                appState.edit().putString("pkg_${a.id}", a.packageName).apply()
                runOnUiThread { status.text = "Abrindo ${a.name}..." }
                engine.launchVirtual(a.packageName).getOrThrow()
            }.onSuccess {
                runOnUiThread { status.text = "${a.name} instalado no contêiner e iniciado." }
            }.onFailure { showError(it) }
        }
    }

    private fun showError(e: Throwable) {
        Log.e("BBLContainer", "Erro", e)
        runOnUiThread { status.text = "ERRO: ${e.message ?: e.javaClass.simpleName}" }
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()
}
