package com.bbl.container

import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

data class DeviceSession(val deviceId: String, val token: String)
data class CatalogApp(
    val id: String,
    val name: String,
    val packageName: String,
    val version: String,
    val sha256: String,
    val downloadUrl: String
)

class ApiClient(private val base: String) {
    fun activate(code: String, deviceId: String): DeviceSession {
        val c = conn("/api/enroll", "POST", null)
        val body = JSONObject()
            .put("activation_code", code)
            .put("device_id", deviceId)
            .put("manufacturer", android.os.Build.MANUFACTURER ?: "")
            .put("model", android.os.Build.MODEL ?: "")
            .put("android_version", android.os.Build.VERSION.RELEASE ?: "")
            .put("launcher_version", "0.4.0")
            .toString()
        c.outputStream.use { it.write(body.toByteArray()) }
        val o = JSONObject(readResponse(c))
        return DeviceSession(o.getString("device_id"), o.getString("device_token"))
    }

    fun catalog(deviceId: String, token: String): List<CatalogApp> {
        val c = conn("/api/devices/$deviceId/policy", "GET", token)
        val root = JSONObject(readResponse(c))
        if (root.optBoolean("locked", false) || root.optBoolean("expired", false)) {
            throw IllegalStateException("Dispositivo bloqueado ou vencido no painel")
        }
        val a = root.optJSONArray("apps") ?: return emptyList()
        return (0 until a.length()).map { i ->
            val o = a.getJSONObject(i)
            CatalogApp(
                o.optString("id"),
                o.optString("name", "Aplicativo"),
                o.optString("package_name"),
                o.optString("version_name"),
                o.optString("sha256"),
                o.optString("download_url")
            )
        }
    }

    fun download(path: String, out: File) {
        val c = conn(path, "GET", null)
        if (c.responseCode !in 200..299) throw IllegalStateException("Falha no download: HTTP ${c.responseCode}")
        c.inputStream.use { input -> out.outputStream().use { output -> input.copyTo(output) } }
    }

    private fun readResponse(c: HttpURLConnection): String {
        val code = c.responseCode
        val stream = if (code in 200..299) c.inputStream else c.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (code !in 200..299) throw IllegalStateException("Servidor respondeu HTTP $code: $text")
        return text
    }

    private fun conn(path: String, method: String, token: String?): HttpURLConnection {
        val full = if (path.startsWith("http://") || path.startsWith("https://")) path else base.trimEnd('/') + path
        val c = URL(full).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = 15000
        c.readTimeout = 45000
        c.setRequestProperty("Content-Type", "application/json")
        if (token != null) c.setRequestProperty("Authorization", "Bearer $token")
        if (method == "POST") c.doOutput = true
        return c
    }

    companion object {
        fun sha256(f: File): String {
            val md = MessageDigest.getInstance("SHA-256")
            f.inputStream().use { input ->
                val b = ByteArray(8192)
                while (true) {
                    val n = input.read(b)
                    if (n < 0) break
                    md.update(b, 0, n)
                }
            }
            return md.digest().joinToString("") { "%02x".format(it) }
        }
    }
}
