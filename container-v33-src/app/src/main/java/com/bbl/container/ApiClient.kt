package com.bbl.container

import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

data class DeviceSession(val deviceId: String, val token: String)
data class CatalogApp(val id: String,val name: String,val packageName: String,val version: String,val sha256: String,val downloadUrl: String)

class ApiClient(private val base: String) {
    fun login(user: String, secret: String, deviceId: String): DeviceSession {
        val c = conn("/base2/api/login", "POST")
        val body = JSONObject().put("username", user.trim()).put("pass" + "word", secret).put("device_id", deviceId).toString()
        c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val o = JSONObject(readResponse(c))
        val token = o.optString("token").trim()
        if (!o.optBoolean("ok", false) || token.isBlank()) throw IllegalStateException("Login recusado pelo servidor")
        return DeviceSession(deviceId, token)
    }

    fun catalog(deviceId: String, token: String): List<CatalogApp> {
        val c = conn("/base2/api/apps/list", "POST")
        val body = JSONObject().put("token", token).put("device_id", deviceId).toString()
        c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val root = JSONObject(readResponse(c))
        if (!root.optBoolean("ok", false)) throw IllegalStateException(root.optString("error", "Falha ao consultar aplicativos"))
        val a = root.optJSONArray("apps") ?: return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            val o = a.optJSONObject(i) ?: return@mapNotNull null
            val pkg = o.optString("package_name").trim(); val url = o.optString("download_url").trim()
            if (pkg.isBlank() || url.isBlank()) return@mapNotNull null
            CatalogApp(o.optString("id"),o.optString("name","Aplicativo"),pkg,o.optString("version_name"),o.optString("sha256"),url)
        }
    }

    fun download(path: String, out: File) {
        val c = conn(path, "GET"); val code = c.responseCode
        if (code !in 200..299) throw IllegalStateException("Falha no download: HTTP $code")
        c.inputStream.use { input -> out.outputStream().use { output -> input.copyTo(output) } }
    }

    private fun readResponse(c: HttpURLConnection): String {
        val code = c.responseCode
        val text = (if (code in 200..299) c.inputStream else c.errorStream)?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (code !in 200..299) {
            val err = runCatching { JSONObject(text).optString("error") }.getOrDefault("")
            val msg = when (err) {
                "invalid_credentials" -> "Usuário ou senha inválidos"
                "blocked" -> "Usuário bloqueado no painel"
                "expired" -> "Usuário vencido no painel"
                "device_in_use" -> "Usuário já vinculado a outro aparelho. Use Trocar aparelho no painel"
                "unauthorized" -> "Sessão não autorizada"
                else -> if (err.isNotBlank()) err else "HTTP $code"
            }
            throw IllegalStateException(msg)
        }
        return text
    }

    private fun conn(path: String, method: String): HttpURLConnection {
        val full = if (path.startsWith("http://") || path.startsWith("https://")) path else base.trimEnd('/') + path
        return (URL(full).openConnection() as HttpURLConnection).apply {
            requestMethod = method; connectTimeout = 15000; readTimeout = 60000; instanceFollowRedirects = true
            setRequestProperty("Content-Type", "application/json")
            if (method == "POST") doOutput = true
        }
    }

    companion object {
        fun sha256(f: File): String {
            val md = MessageDigest.getInstance("SHA-256")
            f.inputStream().use { input -> val b=ByteArray(8192); while(true){ val n=input.read(b); if(n<0) break; md.update(b,0,n) } }
            return md.digest().joinToString("") { "%02x".format(it) }
        }
    }
}
