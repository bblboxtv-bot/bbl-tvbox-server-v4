package com.bbl.boxtv.launcher

import android.app.Activity
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.Drawable
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.widget.ImageView
import com.google.zxing.BarcodeFormat
import com.google.zxing.MultiFormatWriter
import com.google.zxing.common.BitMatrix
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.*
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var page: LinearLayout
    private lateinit var status: TextView
    private lateinit var clientCard: TextView
    private lateinit var clock: TextView
    private lateinit var dateText: TextView
    private lateinit var deviceId: String
    private var currentConfig: DeviceConfig? = null
    private var currentApps: List<RemoteApp> = emptyList()
    private val prefs by lazy { getSharedPreferences("bbl", Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        deviceId = DeviceIdentity.get(this)
        buildShell()
        val preview = DeviceConfig(active = true, apps = emptyList(), brandingName = "BBL.BOXTV", message = "Sincronizando...")
        currentConfig = preview
        buildHome(preview)
        clientCard.text = "CLIENTE\n" + deviceId + "\nSINCRONIZANDO..."
        status.text = "Conectando ao painel..."
        tickClock()
        if (savedToken().isBlank()) showActivation() else sync()
    }

    override fun onBackPressed() {
        val cfg=currentConfig
        if(cfg!=null){
            render(cfg)
        }else{
            // Launcher home should never close on BACK.
            moveTaskToBack(false)
        }
    }

    override fun onResume() {
        super.onResume()
        if (::deviceId.isInitialized && savedToken().isNotBlank()) sync()
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun dp(v:Int)= (v * resources.displayMetrics.density).toInt()

    private fun panelBg(radius:Int=18, stroke:Int=1): GradientDrawable =
        GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(Color.rgb(22,28,92), Color.rgb(8,12,54))).apply {
            cornerRadius=dp(radius).toFloat()
            setStroke(dp(stroke), Color.rgb(40,110,255))
        }

    private fun buildShell() {
        val frame=FrameLayout(this).apply { setBackgroundColor(Color.rgb(2,5,26)) }
        frame.addView(BackdropView(this), FrameLayout.LayoutParams(-1,-1))

        page=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL
            setPadding(dp(26),dp(18),dp(26),dp(18))
        }
        frame.addView(page, FrameLayout.LayoutParams(-1,-1))
        setContentView(frame)
    }

    private fun buildHome(cfg:DeviceConfig) {
        page.removeAllViews()

        val top=LinearLayout(this).apply { orientation=LinearLayout.HORIZONTAL; gravity=Gravity.CENTER_VERTICAL }

        val left=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL }
        val greet=TextView(this).apply {
            text="• BOA NOITE"; textSize=17f; setTextColor(Color.rgb(77,232,255)); setTypeface(typeface,Typeface.BOLD)
        }
        left.addView(greet)
        val timeRow=LinearLayout(this).apply { orientation=LinearLayout.HORIZONTAL; gravity=Gravity.BOTTOM }
        clock=TextView(this).apply { textSize=42f; setTextColor(Color.WHITE); setTypeface(typeface,Typeface.BOLD) }
        dateText=TextView(this).apply { textSize=16f; setTextColor(Color.WHITE); setPadding(dp(12),0,0,dp(6)) }
        timeRow.addView(clock)
        timeRow.addView(dateText)
        left.addView(timeRow)
        clientCard=TextView(this).apply {
            text="CLIENTE\n"+deviceId+"\nAGUARDANDO"
            textSize=14f; setTextColor(Color.WHITE); setPadding(dp(14),dp(8),dp(14),dp(8)); background=panelBg(14)
        }
        left.addView(clientCard, LinearLayout.LayoutParams(dp(260),dp(66)).apply { topMargin=dp(8) })
        top.addView(left, LinearLayout.LayoutParams(0,dp(150),1.05f))

        val sys=LinearLayout(this).apply {
            orientation=LinearLayout.HORIZONTAL; gravity=Gravity.CENTER; setPadding(dp(16),dp(10),dp(16),dp(10)); background=panelBg()
        }
        sys.addView(TextView(this).apply {
            text="◔ 31%\n0.9/2.7 GB"; gravity=Gravity.CENTER; textSize=17f; setTextColor(Color.WHITE)
        },LinearLayout.LayoutParams(0,dp(92),1f))
        sys.addView(TextView(this).apply {
            text="▥ Wi‑Fi\n192.168.0.122"; gravity=Gravity.CENTER; textSize=16f; setTextColor(Color.WHITE)
        },LinearLayout.LayoutParams(0,dp(92),1f))
        top.addView(sys,LinearLayout.LayoutParams(0,dp(108),1.0f).apply { leftMargin=dp(14); rightMargin=dp(14) })

        val actions=LinearLayout(this).apply { orientation=LinearLayout.HORIZONTAL; gravity=Gravity.END }
        fun shortcut(icon:String,label:String,click:()->Unit):TextView = TextView(this).apply {
            text="$icon\n$label"; gravity=Gravity.CENTER; textSize=15f; setTextColor(Color.WHITE); setTypeface(typeface,Typeface.BOLD)
            background=panelBg(14); isFocusable=true; setPadding(dp(8),dp(6),dp(8),dp(6)); setOnClickListener{click()}
            setOnFocusChangeListener { v, has -> v.scaleX=if(has)1.06f else 1f; v.scaleY=if(has)1.06f else 1f }
        }
        actions.addView(shortcut("☎","Suporte"){ showSupportScreen() }, LinearLayout.LayoutParams(dp(104),dp(92)).apply{rightMargin=dp(8)})
        actions.addView(shortcut("▣","Loja"){ showAppStore() }, LinearLayout.LayoutParams(dp(94),dp(92)).apply{rightMargin=dp(8)})
        actions.addView(shortcut("♨","Otimizar"){ Toast.makeText(this,"Otimização concluída",Toast.LENGTH_SHORT).show() }, LinearLayout.LayoutParams(dp(104),dp(92)).apply{rightMargin=dp(8)})
        actions.addView(shortcut("⌁","Wi‑Fi"){ startActivity(Intent(Settings.ACTION_WIFI_SETTINGS)) }, LinearLayout.LayoutParams(dp(94),dp(92)).apply{rightMargin=dp(8)})
        actions.addView(shortcut("⚙","Ajustes"){ startActivity(Intent(Settings.ACTION_SETTINGS)) }, LinearLayout.LayoutParams(dp(104),dp(92)))
        top.addView(actions,LinearLayout.LayoutParams(0,dp(108),1.55f))
        page.addView(top)

        status=TextView(this).apply { textSize=13f; setTextColor(Color.rgb(150,190,255)); setPadding(0,dp(3),0,dp(7)) }
        page.addView(status)

        val hero=HeroView(this).apply { isFocusable=false }
        page.addView(hero,LinearLayout.LayoutParams(-1,dp(250)).apply{topMargin=dp(4)})

        page.addView(TextView(this).apply {
            text="★  FAVORITOS"; textSize=18f; setTextColor(Color.WHITE); setTypeface(typeface,Typeface.BOLD)
            setPadding(dp(12),dp(7),dp(12),dp(7)); background=panelBg(10)
        },LinearLayout.LayoutParams(dp(250),dp(46)).apply{topMargin=dp(10)})

        val favorites=homeFavoriteApps(cfg.apps)
        page.addView(buildFavoriteRow(favorites),LinearLayout.LayoutParams(-1,0,1f))
        tickClock()
    }

    private fun focusTile()=GradientDrawable(GradientDrawable.Orientation.TL_BR,intArrayOf(Color.rgb(31,34,154),Color.rgb(12,14,72))).apply{
        cornerRadius=dp(18).toFloat(); setStroke(dp(3),Color.rgb(48,230,255))
    }

    private fun render(cfg:DeviceConfig) {
        currentConfig=cfg; currentApps=cfg.apps
        if(!cfg.active){
            page.removeAllViews()
            showBlockedScreen()
            return
        }
        buildHome(cfg)
        val exp=if(cfg.expiresAt.isBlank())"SEM VALIDADE" else cfg.expiresAt.take(10)
        clientCard.text="CLIENTE\n"+deviceId+"   •   ATIVO\n"+exp
        status.text=if(cfg.message.isBlank())"ONLINE • Controle remoto ativo" else cfg.message
    }

    private fun showHomeFavorites(){ currentConfig?.let{ render(it) } }

    private fun normalizeName(value:String):String =
        value.lowercase(Locale.ROOT)
            .replace(" ", "")
            .replace(".", "")
            .replace("_", "")
            .replace("-", "")

    private fun homeFavoriteApps(apps:List<RemoteApp>):List<RemoteApp>{
        fun isUni(app:RemoteApp):Boolean{
            val s=normalizeName(app.label+" "+app.packageName)
            return s.contains("unitv")
        }
        fun isTudoNovo(app:RemoteApp):Boolean{
            val pkg=app.packageName.lowercase(Locale.ROOT)
            val s=normalizeName(app.label+" "+app.packageName)
            return pkg=="com.rtxapps.reuse" || pkg.startsWith("com.rtxapps.reuse.") ||
                s.contains("tudoliberado") || (s.contains("tudo") && !s.contains("acesso"))
        }
        val result=mutableListOf<RemoteApp>()
        apps.firstOrNull{isUni(it)}?.let{result.add(it)}
        apps.firstOrNull{
            val pkg=it.packageName.lowercase(Locale.ROOT)
            pkg=="com.rtxapps.reuse" || pkg.startsWith("com.rtxapps.reuse.")
        }?.let{if(result.none{r->r.packageName==it.packageName})result.add(it)}
          ?: apps.firstOrNull{isTudoNovo(it)}?.let{if(result.none{r->r.packageName==it.packageName})result.add(it)}

        apps.firstOrNull{
            val s=normalizeName(it.label+" "+it.packageName)
            it.packageName.equals("com.bx.sport.live9",true) || s.contains("stvesporte") || s.contains("stvfutebol") || (s.contains("stv") && (s.contains("esporte") || s.contains("futebol")))
        }?.let{if(result.none{r->r.packageName==it.packageName})result.add(it)}
        return result
    }

    private fun buildFavoriteRow(apps:List<RemoteApp>):LinearLayout{
        val row=LinearLayout(this).apply{
            orientation=LinearLayout.HORIZONTAL
            gravity=Gravity.START or Gravity.CENTER_VERTICAL
            setPadding(0,dp(8),0,0)
        }

        val uni=apps.firstOrNull{normalizeName(it.label+" "+it.packageName).contains("unitv")}
        val tudo=apps.firstOrNull{
            val pkg=it.packageName.lowercase(Locale.ROOT)
            pkg=="com.rtxapps.reuse" || pkg.startsWith("com.rtxapps.reuse.")
        } ?: apps.firstOrNull{
            val s=normalizeName(it.label+" "+it.packageName)
            s.contains("tudoliberado") || (s.contains("tudo") && !s.contains("acesso"))
        }

        val stv=apps.firstOrNull{
            val s=normalizeName(it.label+" "+it.packageName)
            it.packageName.equals("com.bx.sport.live9",true) || s.contains("stvesporte") || s.contains("stvfutebol") || (s.contains("stv") && (s.contains("esporte") || s.contains("futebol")))
        }

        row.addView(buildFavoriteCard(uni,"UniTV Free","UN"),LinearLayout.LayoutParams(dp(260),dp(350)).apply{rightMargin=dp(18)})
        row.addView(buildFavoriteCard(tudo,"Tudo Liberado","TL"),LinearLayout.LayoutParams(dp(300),dp(350)).apply{rightMargin=dp(18)})
        row.addView(buildFavoriteCard(stv,"STV Esporte","ST"),LinearLayout.LayoutParams(dp(260),dp(350)))
        return row
    }

    private fun buildFavoriteCard(app:RemoteApp?,fallbackLabel:String,initials:String):LinearLayout{
        val installed=app?.let{isInstalled(it.packageName)}?:false
        return LinearLayout(this).apply{
            orientation=LinearLayout.VERTICAL
            gravity=Gravity.CENTER
            setPadding(dp(12),dp(10),dp(12),dp(10))
            background=focusTile()
            isFocusable=app!=null
            setOnFocusChangeListener{v,h->v.scaleX=if(h)1.06f else 1f;v.scaleY=if(h)1.06f else 1f}

            val iconView=ImageView(this@MainActivity).apply{
                scaleType=ImageView.ScaleType.FIT_CENTER
                setPadding(dp(8),dp(8),dp(8),dp(8))
                background=GradientDrawable().apply{
                    shape=GradientDrawable.OVAL
                    setColor(when(initials){
                        "UN" -> Color.rgb(44,145,255)
                        "ST" -> Color.rgb(35,180,120)
                        else -> Color.rgb(255,128,38)
                    })
                }
                if(app!=null && installed){
                    try{ setImageDrawable(packageManager.getApplicationIcon(app.packageName)) }catch(_:Exception){}
                }
            }
            if(iconView.drawable!=null){
                addView(iconView,LinearLayout.LayoutParams(dp(105),dp(105)))
            }else{
                addView(TextView(this@MainActivity).apply{
                    text=initials
                    gravity=Gravity.CENTER
                    textSize=28f
                    setTextColor(Color.WHITE)
                    setTypeface(typeface,Typeface.BOLD)
                    background=iconView.background
                },LinearLayout.LayoutParams(dp(105),dp(105)))
            }

            addView(TextView(this@MainActivity).apply{
                text=(app?.label?:fallbackLabel)+"\n"+when{
                    app==null -> "NÃO CONFIGURADO"
                    installed -> "ABRIR"
                    else -> "INSTALAR"
                }
                gravity=Gravity.CENTER
                textSize=17f
                setTextColor(Color.WHITE)
                setTypeface(typeface,Typeface.BOLD)
                setPadding(0,dp(8),0,0)
            },LinearLayout.LayoutParams(-1,dp(150)))

            if(app!=null){
                setOnClickListener{
                    if(installed) launchPackage(app.packageName) else requestInstall(app)
                }
            }
        }
    }

    private fun tickClock(){
        if(::clock.isInitialized){
            val now=Date()
            clock.text=SimpleDateFormat("HH:mm",Locale("pt","BR")).format(now)
            dateText.text=SimpleDateFormat("EEE, dd 'de' MMM",Locale("pt","BR")).format(now)
            clock.postDelayed({tickClock()},30000)
        }
    }

    private fun savedToken()=prefs.getString("device_token","")?:""

    private fun showActivation(message:String=""){
        page.removeAllViews()
        val box=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;gravity=Gravity.CENTER;setPadding(dp(90),dp(70),dp(90),dp(70))}
        box.addView(TextView(this).apply{text="ATIVAÇÃO BBL.BOXTV";textSize=30f;setTextColor(Color.WHITE);gravity=Gravity.CENTER;setTypeface(typeface,Typeface.BOLD)})
        if(message.isNotBlank()) box.addView(TextView(this).apply{text=message;textSize=16f;setTextColor(Color.rgb(255,130,170));gravity=Gravity.CENTER;setPadding(0,dp(12),0,dp(12))})
        val code=EditText(this).apply{hint="BBL-XXXX-XXXX";textSize=24f;setTextColor(Color.WHITE);setHintTextColor(Color.LTGRAY);gravity=Gravity.CENTER;isSingleLine=true}
        box.addView(code,LinearLayout.LayoutParams(-1,dp(64)))
        box.addView(Button(this).apply{text="ATIVAR";isAllCaps=false;setOnClickListener{activate(code.text.toString(),this)}},LinearLayout.LayoutParams(-1,dp(64)).apply{topMargin=dp(14)})
        page.addView(box,LinearLayout.LayoutParams(-1,-1))
    }

    private fun activate(code:String,button:Button){
        if(code.trim().isBlank())return
        button.isEnabled=false
        executor.execute{
            try{
                ApiClient.healthCheck()
                val token=ApiClient.enroll(deviceId,code)
                prefs.edit().putString("device_token",token).apply()
                val cfg=ApiClient.getPolicy(deviceId,token)
                runOnUiThread{render(cfg)}
            }catch(e:ApiClient.HttpStatusException){
                runOnUiThread{showActivation("Falha HTTP "+e.code+": "+e.body.take(150))}
            }catch(e:Exception){
                runOnUiThread{showActivation("Falha de conexão: "+(e.message?:"sem detalhe"))}
            }
        }
    }

    private fun sync(){
        val token=savedToken()
        if(token.isBlank())return showActivation()
        executor.execute{
            try{
                val cfg=ApiClient.getPolicy(deviceId,token)
                runOnUiThread{render(cfg)}
            }catch(e:ApiClient.HttpStatusException){
                runOnUiThread{if(e.code==401){prefs.edit().remove("device_token").apply();showActivation("Ativação necessária")}else Toast.makeText(this,"HTTP "+e.code,Toast.LENGTH_SHORT).show()}
            }catch(e:Exception){
                runOnUiThread{
                    if(::status.isInitialized) status.text="Falha ao sincronizar: "+(e.message?:"erro desconhecido")
                    Toast.makeText(this,"Falha ao sincronizar com o painel",Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private val supportNumber = "21 98851-0594"
    private val supportWhatsApp = "5521988510594"

    private fun qrBitmap(content:String,size:Int):Bitmap{
        val matrix:BitMatrix=MultiFormatWriter().encode(content,BarcodeFormat.QR_CODE,size,size)
        val bmp=Bitmap.createBitmap(size,size,Bitmap.Config.RGB_565)
        for(x in 0 until size) for(y in 0 until size){
            bmp.setPixel(x,y,if(matrix.get(x,y)) Color.BLACK else Color.WHITE)
        }
        return bmp
    }

    private fun showSupportScreen(){
        page.removeAllViews()
        val box=LinearLayout(this).apply{
            orientation=LinearLayout.VERTICAL
            gravity=Gravity.CENTER
            setPadding(dp(70),dp(35),dp(70),dp(35))
        }
        box.addView(TextView(this).apply{
            text="SUPORTE BBL.BOXTV"
            textSize=30f
            setTextColor(Color.WHITE)
            gravity=Gravity.CENTER
            setTypeface(typeface,Typeface.BOLD)
        })
        val qr=ImageView(this).apply{
            setImageBitmap(qrBitmap("https://wa.me/"+supportWhatsApp,dp(240)))
            setPadding(dp(10),dp(10),dp(10),dp(10))
            setBackgroundColor(Color.WHITE)
        }
        box.addView(qr,LinearLayout.LayoutParams(dp(270),dp(270)).apply{topMargin=dp(18)})
        box.addView(TextView(this).apply{
            text="Entre em contato com o suporte\n"+supportNumber
            textSize=22f
            setTextColor(Color.WHITE)
            gravity=Gravity.CENTER
            setPadding(0,dp(16),0,dp(16))
            setTypeface(typeface,Typeface.BOLD)
        })
        box.addView(Button(this).apply{
            text="Voltar"
            isAllCaps=false
            setOnClickListener{currentConfig?.let{render(it)}}
        },LinearLayout.LayoutParams(dp(180),dp(58)))
        page.addView(box,LinearLayout.LayoutParams(-1,-1))
    }

    private fun showBlockedScreen(){
        page.removeAllViews()
        val box=LinearLayout(this).apply{
            orientation=LinearLayout.VERTICAL
            gravity=Gravity.CENTER
            setPadding(dp(70),dp(28),dp(70),dp(28))
        }
        box.addView(TextView(this).apply{
            text="APARELHO BLOQUEADO\nEntre em contato com o suporte."
            gravity=Gravity.CENTER
            textSize=30f
            setTextColor(Color.WHITE)
            setTypeface(typeface,Typeface.BOLD)
        })
        val qr=ImageView(this).apply{
            setImageBitmap(qrBitmap("https://wa.me/"+supportWhatsApp,dp(220)))
            setPadding(dp(10),dp(10),dp(10),dp(10))
            setBackgroundColor(Color.WHITE)
        }
        box.addView(qr,LinearLayout.LayoutParams(dp(250),dp(250)).apply{topMargin=dp(18)})
        box.addView(TextView(this).apply{
            text=supportNumber
            textSize=24f
            setTextColor(Color.WHITE)
            gravity=Gravity.CENTER
            setPadding(0,dp(14),0,0)
            setTypeface(typeface,Typeface.BOLD)
        })
        page.addView(box,LinearLayout.LayoutParams(-1,-1))
    }

    private fun showAppStore(){
        page.removeAllViews()
        val header=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL}
        header.addView(TextView(this).apply{text="LOJA DE APPS";textSize=28f;setTextColor(Color.WHITE);setTypeface(typeface,Typeface.BOLD)},LinearLayout.LayoutParams(0,dp(70),1f))
        header.addView(Button(this).apply{text="Voltar";isAllCaps=false;setOnClickListener{currentConfig?.let{render(it)}}},LinearLayout.LayoutParams(dp(150),dp(58)))
        page.addView(header)
        page.addView(buildAppsRow(currentApps),LinearLayout.LayoutParams(-1,0,1f))
    }

    private fun buildAppsRow(apps:List<RemoteApp>):HorizontalScrollView{
        val scroll=HorizontalScrollView(this).apply{isFillViewport=true;isHorizontalScrollBarEnabled=false}
        val row=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL;setPadding(0,dp(8),0,0)}
        if(apps.isEmpty()){
            row.addView(TextView(this).apply{text="Nenhum aplicativo liberado no painel.";textSize=20f;setTextColor(Color.WHITE);setPadding(dp(30),dp(30),dp(30),dp(30))})
        }else apps.forEach{app->
            val installed=isInstalled(app.packageName)
            val card=LinearLayout(this).apply{
                orientation=LinearLayout.VERTICAL;gravity=Gravity.CENTER;setPadding(dp(10),dp(6),dp(10),dp(10));background=panelBg(14);isFocusable=true
                setOnFocusChangeListener{v,h->v.scaleX=if(h)1.06f else 1f;v.scaleY=if(h)1.06f else 1f}
                setOnClickListener{if(!installed)requestInstall(app)}
            }
            card.addView(TextView(this).apply{text="ILIMITADO";gravity=Gravity.CENTER;textSize=12f;setTextColor(Color.rgb(30,25,35));setTypeface(typeface,Typeface.BOLD);background=GradientDrawable().apply{setColor(Color.rgb(255,190,70));cornerRadius=dp(8).toFloat()}},LinearLayout.LayoutParams(-1,dp(28)))
            val appIcon=ImageView(this).apply{
                scaleType=ImageView.ScaleType.FIT_CENTER
                setPadding(dp(5),dp(5),dp(5),dp(5))
                background=GradientDrawable().apply{shape=GradientDrawable.OVAL;setColor(Color.rgb(38,105,255))}
                if(installed){
                    try{setImageDrawable(packageManager.getApplicationIcon(app.packageName))}catch(_:Exception){}
                }
            }
            if(appIcon.drawable!=null){
                card.addView(appIcon,LinearLayout.LayoutParams(dp(78),dp(78)).apply{topMargin=dp(10)})
            }else{
                card.addView(TextView(this).apply{
                    text=app.label.take(2).uppercase();gravity=Gravity.CENTER;textSize=24f;setTextColor(Color.WHITE);setTypeface(typeface,Typeface.BOLD)
                    background=appIcon.background
                },LinearLayout.LayoutParams(dp(78),dp(78)).apply{topMargin=dp(10)})
            }
            card.addView(TextView(this).apply{text=app.label+"\n"+if(installed)"INSTALADO" else "INSTALAR";gravity=Gravity.CENTER;textSize=15f;setTextColor(Color.WHITE);setPadding(0,dp(8),0,0)},LinearLayout.LayoutParams(-1,dp(70)))
            row.addView(card,LinearLayout.LayoutParams(dp(190),dp(185)).apply{rightMargin=dp(12)})
        }
        scroll.addView(row)
        return scroll
    }

    private fun isInstalled(pkg:String)=try{packageManager.getPackageInfo(pkg,0);true}catch(_:Exception){false}

    private fun requestInstall(app:RemoteApp){
        if(app.downloadUrl.isBlank()){Toast.makeText(this,"APK não configurado no painel",Toast.LENGTH_LONG).show();return}
        if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.O&&!packageManager.canRequestPackageInstalls()){
            try{startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+packageName)))}catch(_:Exception){startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS))}
            return
        }
        executor.execute{
            try{
                val file=File(cacheDir,"remote_apks/"+app.packageName+".apk")
                ApiClient.downloadApk(app,file);install(file,app)
            }catch(e:Exception){runOnUiThread{Toast.makeText(this,e.message?:"Erro no download",Toast.LENGTH_LONG).show()}}
        }
    }

    private fun install(apk:File,app:RemoteApp){
        try{
            val installer=packageManager.packageInstaller
            val params=PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
            params.setAppPackageName(app.packageName)
            val sessionId=installer.createSession(params)
            installer.openSession(sessionId).use{session->
                apk.inputStream().use{input->session.openWrite("base.apk",0,apk.length()).use{out->input.copyTo(out);session.fsync(out)}}
                val callback=Intent(this,InstallResultReceiver::class.java)
                val flags=PendingIntent.FLAG_UPDATE_CURRENT or if(Build.VERSION.SDK_INT>=31)PendingIntent.FLAG_MUTABLE else 0
                session.commit(PendingIntent.getBroadcast(this,sessionId,callback,flags).intentSender)
            }
        }catch(e:Exception){runOnUiThread{Toast.makeText(this,"Falha ao instalar: "+(e.message?:"erro"),Toast.LENGTH_LONG).show()}}
    }

    private fun launchPackage(pkg:String){
        packageManager.getLaunchIntentForPackage(pkg)?.let{startActivity(it)}?:Toast.makeText(this,"Aplicativo não instalado",Toast.LENGTH_SHORT).show()
    }

    inner class BackdropView(ctx:Context):View(ctx){
        private val p=Paint(Paint.ANTI_ALIAS_FLAG)
        override fun onDraw(c:Canvas){
            super.onDraw(c)
            val w=width.toFloat(); val h=height.toFloat()

            p.shader=LinearGradient(0f,0f,w,h,
                intArrayOf(Color.rgb(2,5,24),Color.rgb(8,16,72),Color.rgb(3,7,35),Color.rgb(18,6,40)),
                null,Shader.TileMode.CLAMP)
            c.drawRect(0f,0f,w,h,p)
            p.shader=null

            p.color=Color.argb(46,35,115,255)
            c.drawCircle(w*.76f,h*.30f,w*.28f,p)
            p.color=Color.argb(32,255,128,25)
            c.drawCircle(w*.64f,h*.53f,w*.20f,p)
            p.color=Color.argb(22,40,220,255)
            c.drawCircle(w*.24f,h*.72f,w*.24f,p)

            p.style=Paint.Style.STROKE
            p.strokeWidth=dp(2).toFloat()
            for(i in 0..7){
                p.color=Color.argb(22+i*2,30,130,255)
                val y=h*(.10f+i*.105f)
                c.drawLine(0f,y,w,y-dp(80),p)
            }
            p.style=Paint.Style.FILL

            p.textAlign=Paint.Align.RIGHT
            p.typeface=Typeface.DEFAULT_BOLD
            p.textSize=dp(38).toFloat()
            p.color=Color.argb(32,255,255,255)
            c.drawText("BBL.BOXTV",w-dp(28),h-dp(26),p)
        }
    }

    inner class HeroView(ctx:Context):View(ctx){
        private val p=Paint(Paint.ANTI_ALIAS_FLAG)
        override fun onDraw(c:Canvas){
            super.onDraw(c)
            val w=width.toFloat(); val h=height.toFloat()

            p.shader=LinearGradient(0f,0f,w,h,
                intArrayOf(Color.rgb(9,16,70),Color.rgb(18,35,120),Color.rgb(48,20,74),Color.rgb(10,8,35)),
                null,Shader.TileMode.CLAMP)
            c.drawRoundRect(0f,0f,w,h,dp(20).toFloat(),dp(20).toFloat(),p)
            p.shader=null

            p.color=Color.argb(80,255,145,25)
            c.drawCircle(w*.57f,h*.48f,h*.62f,p)
            p.color=Color.argb(70,35,150,255)
            c.drawCircle(w*.28f,h*.42f,h*.52f,p)

            p.textAlign=Paint.Align.CENTER
            p.typeface=Typeface.DEFAULT_BOLD

            p.textSize=dp(21).toFloat()
            p.color=Color.rgb(100,220,255)
            c.drawText("TV AO VIVO   •   FILMES   •   SÉRIES   •   ESPORTES   •   INFANTIL",w*.50f,h*.20f,p)

            p.setShadowLayer(dp(12).toFloat(),0f,0f,Color.rgb(255,105,10))
            p.textSize=dp(58).toFloat()
            p.color=Color.rgb(255,178,55)
            c.drawText("BBL.BOXTV",w*.50f,h*.56f,p)
            p.clearShadowLayer()

            p.textSize=dp(17).toFloat()
            p.color=Color.WHITE
            c.drawText("O MELHOR DO ENTRETENIMENTO EM UM SÓ LUGAR",w*.50f,h*.71f,p)

            val badgeW=w*.14f
            val gap=w*.018f
            val labels=arrayOf("TV","FILMES","SÉRIES","JOGOS","APPS")
            var x=w*.5f-(labels.size*badgeW+(labels.size-1)*gap)/2f
            for(label in labels){
                p.color=Color.argb(165,10,12,38)
                c.drawRoundRect(x,h*.78f,x+badgeW,h*.95f,dp(10).toFloat(),dp(10).toFloat(),p)
                p.style=Paint.Style.STROKE
                p.strokeWidth=dp(1).toFloat()
                p.color=Color.rgb(255,174,55)
                c.drawRoundRect(x,h*.78f,x+badgeW,h*.95f,dp(10).toFloat(),dp(10).toFloat(),p)
                p.style=Paint.Style.FILL
                p.textSize=dp(13).toFloat()
                p.color=Color.WHITE
                c.drawText(label,x+badgeW/2f,h*.89f,p)
                x+=badgeW+gap
            }

            p.style=Paint.Style.STROKE
            p.strokeWidth=dp(2).toFloat()
            p.color=Color.rgb(40,185,255)
            c.drawRoundRect(dp(2).toFloat(),dp(2).toFloat(),w-dp(2),h-dp(2),dp(20).toFloat(),dp(20).toFloat(),p)
            p.style=Paint.Style.FILL
        }
    }
}

internal object DeviceIdentity{
    fun get(context:Context):String{
        val prefs=context.getSharedPreferences("bbl",Context.MODE_PRIVATE)
        val saved=prefs.getString("device_id",null)
        if(saved!=null && saved!="suffix" && saved!="deviceId" && !saved.contains("$"+"{") && saved.startsWith("BOX-")) return saved
        if(saved!=null){
            prefs.edit().remove("device_id").remove("device_token").apply()
        }
        val androidId=Settings.Secure.getString(context.contentResolver,Settings.Secure.ANDROID_ID)
        val suffix=(androidId?.takeLast(8)?:UUID.randomUUID().toString().take(8)).uppercase()
        return("BOX-"+suffix).also{prefs.edit().putString("device_id",it).apply()}
    }
}
