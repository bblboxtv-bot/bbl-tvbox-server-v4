package com.bbl.boxtv.launcher

import android.app.Activity
import android.app.AlertDialog
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.*
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var root: LinearLayout
    private lateinit var clientInfo: TextView
    private lateinit var status: TextView
    private lateinit var title: TextView
    private lateinit var clock: TextView
    private lateinit var deviceId: String
    private var currentConfig: DeviceConfig? = null
    private var currentApps: List<RemoteApp> = emptyList()
    private val prefs by lazy { getSharedPreferences("bbl", Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        deviceId = DeviceIdentity.get(this)
        buildUi()
        refreshClock()
        if (savedToken().isBlank()) showActivation() else sync()
    }

    override fun onResume() {
        super.onResume()
        if (::deviceId.isInitialized && savedToken().isNotBlank()) sync()
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun buildUi() {
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 18, 24, 20)
            setBackgroundColor(Color.rgb(9, 11, 15))
        }

        val top = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        clientInfo = TextView(this).apply {
            text = "CLIENTE\nID: ---\nAGUARDANDO"
            textSize = 14f
            setTextColor(Color.WHITE)
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            setPadding(16, 10, 16, 10)
            setBackgroundColor(Color.rgb(28, 30, 34))
        }
        top.addView(clientInfo, LinearLayout.LayoutParams(310, 88).apply { rightMargin = 16 })

        val brand = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val logo = ImageView(this).apply {
            setImageResource(R.drawable.ic_bbl)
            scaleType = ImageView.ScaleType.FIT_CENTER
        }
        brand.addView(logo, LinearLayout.LayoutParams(78, 70))

        title = TextView(this).apply {
            text = "BBL.BOXTV"
            textSize = 28f
            setTextColor(Color.WHITE)
            setTypeface(typeface, 1)
            setPadding(12, 0, 8, 0)
        }
        brand.addView(title, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(brand, LinearLayout.LayoutParams(0, 88, 1f))

        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.END or Gravity.CENTER_VERTICAL
        }

        clock = TextView(this).apply {
            textSize = 15f
            setTextColor(Color.WHITE)
            gravity = Gravity.END
        }
        actions.addView(clock, LinearLayout.LayoutParams(-1, -2))

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
        }
        row.addView(Button(this).apply {
            text = "Configurações"
            isAllCaps = false
            isFocusable = true
            setOnClickListener {
                try { startActivity(Intent(Settings.ACTION_SETTINGS)) }
                catch (_: Exception) { Toast.makeText(this@MainActivity, "Não foi possível abrir Configurações", Toast.LENGTH_SHORT).show() }
            }
        }, LinearLayout.LayoutParams(190, 52).apply { rightMargin = 8 })

        row.addView(Button(this).apply {
            text = "Loja de Apps"
            isAllCaps = false
            isFocusable = true
            setOnClickListener { showAppStore() }
        }, LinearLayout.LayoutParams(190, 52))

        actions.addView(row, LinearLayout.LayoutParams(-1, -2))
        top.addView(actions, LinearLayout.LayoutParams(410, 88).apply { leftMargin = 16 })

        status = TextView(this).apply {
            textSize = 14f
            setTextColor(Color.LTGRAY)
            setPadding(0, 8, 0, 10)
        }

        root.addView(top)
        root.addView(status)
        setContentView(root)
    }

    private fun refreshClock() {
        clock.text = SimpleDateFormat("dd/MM/yyyy  HH:mm", Locale("pt", "BR")).format(Date())
        clock.postDelayed({ refreshClock() }, 30000L)
    }

    private fun clearContent() {
        while (root.childCount > 2) root.removeViewAt(2)
    }

    private fun savedToken() = prefs.getString("device_token", "") ?: ""

    private fun showActivation(message: String = "") {
        clearContent()
        clientInfo.text = "CLIENTE\nID: " + deviceId + "\nNÃO ATIVADO"
        status.text = "Digite o código de ativação"

        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(90, 50, 90, 50)
        }
        box.addView(TextView(this).apply {
            text = "ATIVAÇÃO BBL.BOXTV"
            textSize = 28f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setTypeface(typeface, 1)
        })
        if (message.isNotBlank()) box.addView(TextView(this).apply {
            text = message
            textSize = 16f
            setTextColor(Color.rgb(255, 130, 130))
            gravity = Gravity.CENTER
        })
        val code = EditText(this).apply {
            hint = "BBL-XXXX-XXXX"
            textSize = 22f
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            gravity = Gravity.CENTER
            isSingleLine = true
        }
        box.addView(code, LinearLayout.LayoutParams(-1, -2))
        box.addView(Button(this).apply {
            text = "ATIVAR"
            isAllCaps = false
            setOnClickListener { activate(code.text.toString(), this) }
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = 18 })
        root.addView(box, LinearLayout.LayoutParams(-1, -1))
    }

    private fun activate(code: String, button: Button) {
        if (code.trim().isBlank()) {
            Toast.makeText(this, "Digite o código de ativação", Toast.LENGTH_SHORT).show()
            return
        }
        button.isEnabled = false
        status.text = "Ativando..."
        executor.execute {
            try {
                ApiClient.healthCheck()
                val token = ApiClient.enroll(deviceId, code)
                prefs.edit().putString("device_token", token).apply()
                val cfg = ApiClient.getPolicy(deviceId, token)
                runOnUiThread { render(cfg) }
            } catch (e: ApiClient.HttpStatusException) {
                runOnUiThread {
                    button.isEnabled = true
                    val detail = e.body.take(180).replace("\n", " ")
                    showActivation("Falha na ativação (HTTP " + e.code + "): " + detail)
                }
            } catch (e: Exception) {
                runOnUiThread {
                    button.isEnabled = true
                    showActivation("Falha de conexão: " + e.javaClass.simpleName + " - " + (e.message ?: "sem detalhe"))
                }
            }
        }
    }

    private fun sync() {
        val token = savedToken()
        if (token.isBlank()) return showActivation()
        status.text = "Sincronizando..."
        executor.execute {
            try {
                val cfg = ApiClient.getPolicy(deviceId, token)
                runOnUiThread { render(cfg) }
            } catch (e: ApiClient.HttpStatusException) {
                runOnUiThread {
                    if (e.code == 401) {
                        prefs.edit().remove("device_token").apply()
                        showActivation("Ativação necessária")
                    } else status.text = "Falha no servidor (HTTP " + e.code + ")"
                }
            } catch (_: Exception) {
                runOnUiThread { status.text = "Servidor indisponível" }
            }
        }
    }

    private fun render(cfg: DeviceConfig) {
        currentConfig = cfg
        currentApps = cfg.apps
        clearContent()
        title.text = cfg.brandingName
        if (!cfg.active) {
            clientInfo.text = "CLIENTE\nID: " + deviceId + "\nBLOQUEADO"
            status.text = "ACESSO BLOQUEADO"
            root.addView(TextView(this).apply {
                text = "Este aparelho está bloqueado. Entre em contato com o administrador."
                textSize = 24f
                gravity = Gravity.CENTER
                setTextColor(Color.WHITE)
            }, LinearLayout.LayoutParams(-1, -1))
            return
        }

        val exp = if (cfg.expiresAt.isBlank()) "SEM VALIDADE" else cfg.expiresAt.take(10)
        clientInfo.text = "CLIENTE\nID: " + deviceId + "\nATIVO • " + exp
        status.text = if (cfg.message.isBlank()) "ATIVO" else cfg.message

        root.addView(TextView(this).apply {
            text = "Aplicativos liberados pelo painel"
            textSize = 20f
            setTextColor(Color.WHITE)
            setPadding(4, 12, 4, 8)
        })
        root.addView(buildAppsRow(cfg.apps), LinearLayout.LayoutParams(-1, 0, 1f))
    }

    private fun showAppStore() {
        clearContent()
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        header.addView(TextView(this).apply {
            text = "LOJA DE APPS"
            textSize = 26f
            setTypeface(typeface, 1)
            setTextColor(Color.WHITE)
        }, LinearLayout.LayoutParams(0, -2, 1f))
        header.addView(Button(this).apply {
            text = "Voltar"
            isAllCaps = false
            setOnClickListener { currentConfig?.let { render(it) } }
        }, LinearLayout.LayoutParams(150, 52))
        root.addView(header)

        root.addView(TextView(this).apply {
            text = "Aplicativos disponíveis"
            textSize = 18f
            setTextColor(Color.LTGRAY)
            setPadding(4, 14, 4, 8)
        })
        root.addView(buildAppsRow(currentApps), LinearLayout.LayoutParams(-1, 0, 1f))
    }

    private fun buildAppsRow(apps: List<RemoteApp>): HorizontalScrollView {
        val scroll = HorizontalScrollView(this).apply { isFillViewport = true }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        if (apps.isEmpty()) {
            row.addView(TextView(this).apply {
                text = "Nenhum aplicativo liberado no painel."
                textSize = 20f
                setTextColor(Color.WHITE)
                setPadding(30, 30, 30, 30)
            })
        } else {
            apps.forEach { app ->
                val installed = isInstalled(app.packageName)
                row.addView(Button(this).apply {
                    text = app.label + "\n" + if (installed) "ABRIR" else "INSTALAR"
                    textSize = 18f
                    isAllCaps = false
                    isFocusable = true
                    setOnClickListener {
                        if (installed) launchPackage(app.packageName) else requestInstall(app)
                    }
                }, LinearLayout.LayoutParams(300, 150).apply { setMargins(10, 10, 10, 10) })
            }
        }
        scroll.addView(row)
        return scroll
    }

    private fun isInstalled(pkg: String): Boolean = try {
        packageManager.getPackageInfo(pkg, 0)
        true
    } catch (_: Exception) { false }

    private fun requestInstall(app: RemoteApp) {
        if (app.downloadUrl.isBlank()) {
            Toast.makeText(this, "APK não configurado no painel", Toast.LENGTH_LONG).show()
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !packageManager.canRequestPackageInstalls()) {
            try {
                startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + packageName)))
            } catch (_: Exception) {
                startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS))
            }
            return
        }
        status.text = "Baixando " + app.label + "..."
        executor.execute {
            try {
                val file = File(cacheDir, "remote_apks/" + app.packageName + ".apk")
                ApiClient.downloadApk(app, file)
                install(file, app)
            } catch (e: Exception) {
                runOnUiThread {
                    status.text = "Falha ao baixar " + app.label
                    Toast.makeText(this, e.message ?: "Erro no download", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun install(apk: File, app: RemoteApp) {
        try {
            val installer = packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
            params.setAppPackageName(app.packageName)
            val sessionId = installer.createSession(params)
            installer.openSession(sessionId).use { session ->
                apk.inputStream().use { input ->
                    session.openWrite("base.apk", 0, apk.length()).use { out ->
                        input.copyTo(out)
                        session.fsync(out)
                    }
                }
                val callback = Intent(this, InstallResultReceiver::class.java)
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0
                val pending = PendingIntent.getBroadcast(this, sessionId, callback, flags)
                session.commit(pending.intentSender)
            }
        } catch (e: Exception) {
            runOnUiThread {
                Toast.makeText(this, "Falha ao instalar: " + (e.message ?: "erro"), Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun launchPackage(pkg: String) {
        packageManager.getLaunchIntentForPackage(pkg)?.let { startActivity(it) }
            ?: Toast.makeText(this, "Aplicativo não instalado", Toast.LENGTH_SHORT).show()
    }
}

internal object DeviceIdentity {
    fun get(context: Context): String {
        val prefs = context.getSharedPreferences("bbl", Context.MODE_PRIVATE)
        prefs.getString("device_id", null)?.let { return it }
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        val suffix = (androidId?.takeLast(8) ?: UUID.randomUUID().toString().take(8)).uppercase()
        return ("BOX-" + suffix).also { prefs.edit().putString("device_id", it).apply() }
    }
}
