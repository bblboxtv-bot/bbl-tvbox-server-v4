package com.bbl.boxtv.launcher

import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.util.Locale

internal data class RemoteApp(
    val packageName: String,
    val label: String,
    val downloadUrl: String = "",
    val versionCode: Long = 0L,
    val sha256: String = ""
)

internal data class DeviceConfig(
    val active: Boolean,
    val expiresAt: String = "",
    val apps: List<RemoteApp> = emptyList(),
    val brandingName: String = "BBL.BOXTV",
    val message: String = ""
)

internal object ApiClient {
    private val apiBaseUrl = BuildConfig.API_BASE_URL.trimEnd('/')

    fun healthCheck(): String {
        val c = URL("${apiBaseUrl}/health").openConnection() as HttpURLConnection
        try {
            c.connectTimeout = 12000
            c.readTimeout = 12000
            c.requestMethod = "GET"
            val code = c.responseCode
            val text = (if (code in 200..299) c.inputStream else c.errorStream)?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) throw HttpStatusException(code, text)
            return text
        } finally { c.disconnect() }
    }

    fun enroll(deviceId: String, activationCode: String): String {
        val c = URL("$" + "{apiBaseUrl}/api/enroll").openConnection() as HttpURLConnection
        try {
            c.doOutput = true
            c.connectTimeout = 10000
            c.readTimeout = 10000
            c.requestMethod = "POST"
            c.setRequestProperty("Content-Type", "application/json")
            val body = JSONObject()
                .put("activationCode", activationCode.trim().uppercase(Locale.ROOT))
                .put("deviceId", deviceId)
                .put("manufacturer", android.os.Build.MANUFACTURER ?: "")
                .put("model", android.os.Build.MODEL ?: "")
                .put("android_version", android.os.Build.VERSION.RELEASE ?: "")
                .put("launcher_version", BuildConfig.VERSION_NAME)
                .toString()
            c.outputStream.use { it.write(body.toByteArray()) }
            val code = c.responseCode
            val text = (if (code in 200..299) c.inputStream else c.errorStream)?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) throw HttpStatusException(code, text)
            val j = JSONObject(text)
            return j.optString("device_token", j.optString("deviceToken", j.optString("token"))).also {
                if (it.isBlank()) error("Servidor não retornou token")
            }
        } finally { c.disconnect() }
    }

    fun getPolicy(deviceId: String, token: String): DeviceConfig {
        val id = URLEncoder.encode(deviceId, "UTF-8")
        val c = URL("$" + "{apiBaseUrl}/api/devices/$" + "{id}/policy").openConnection() as HttpURLConnection
        try {
            c.connectTimeout = 10000
            c.readTimeout = 10000
            c.requestMethod = "GET"
            c.setRequestProperty("Authorization", "Bearer $" + "token")
            c.setRequestProperty("Accept", "application/json")
            val code = c.responseCode
            if (code !in 200..299) throw HttpStatusException(code)
            val j = JSONObject(c.inputStream.bufferedReader().use { it.readText() })
            val arr = j.optJSONArray("apps")
            val apps = mutableListOf<RemoteApp>()
            if (arr != null) for (i in 0 until arr.length()) {
                val a = arr.optJSONObject(i) ?: continue
                val pkg = a.optString("package_name").trim()
                if (pkg.isNotBlank()) {
                    apps += RemoteApp(
                        packageName = pkg,
                        label = a.optString("name", pkg).ifBlank { pkg },
                        downloadUrl = a.optString("download_url", "").trim(),
                        versionCode = a.optString("version_code", "0").toLongOrNull() ?: a.optLong("version_code", 0L),
                        sha256 = a.optString("sha256", "").trim().lowercase()
                    )
                }
            }
            val branding = j.optJSONObject("branding") ?: JSONObject()
            val locked = j.optBoolean("locked", false) || j.optBoolean("expired", false)
            return DeviceConfig(
                active = !locked,
                expiresAt = j.optString("expires_at", ""),
                apps = apps,
                brandingName = branding.optString("name", "BBL.BOXTV").ifBlank { "BBL.BOXTV" },
                message = j.optString("message", branding.optString("message", ""))
            )
        } finally { c.disconnect() }
    }

    fun downloadApk(app: RemoteApp, destination: File) {
        val value = app.downloadUrl.trim()
        if (value.isBlank()) error("Aplicativo sem URL de download")
        val url = if (value.startsWith("http://") || value.startsWith("https://")) value else "$" + "{apiBaseUrl}/" + value.trimStart('/')
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.connectTimeout = 15000
            c.readTimeout = 60000
            c.instanceFollowRedirects = true
            c.requestMethod = "GET"
            val code = c.responseCode
            if (code !in 200..299) throw HttpStatusException(code)
            destination.parentFile?.mkdirs()
            c.inputStream.use { input -> destination.outputStream().use { output -> input.copyTo(output) } }
            if (app.sha256.isNotBlank()) {
                val md = MessageDigest.getInstance("SHA-256")
                destination.inputStream().use { input ->
                    val b = ByteArray(65536)
                    while (true) {
                        val n = input.read(b)
                        if (n <= 0) break
                        md.update(b, 0, n)
                    }
                }
                val got = md.digest().joinToString("") { "%02x".format(it) }
                if (!got.equals(app.sha256, true)) {
                    destination.delete()
                    error("Falha na verificação do APK")
                }
            }
        } finally { c.disconnect() }
    }

    internal class HttpStatusException(val code: Int, val body: String = "") :
        RuntimeException("HTTP $" + "code $" + "body")
}
