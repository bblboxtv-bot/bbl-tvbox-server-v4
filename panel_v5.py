import html, json, secrets
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse


def install_panel(app, *, db_connect, execute, rowd, admin_ok, apk_meta, upload_dir, now_iso, log):
    router = APIRouter()

    def esc(v):
        return html.escape(str(v or ''))

    def require_admin(key: str):
        if not admin_ok(key):
            raise HTTPException(401, 'chave administrativa inválida')

    def q(key: str):
        return f'?key={key}'

    CSS = '''
    *{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#0e1117;color:#eef2f7}
    .top{background:#111827;border-bottom:1px solid #253044;padding:18px 28px;display:flex;align-items:center;justify-content:space-between}
    .brand{font-size:24px;font-weight:800;color:#f5c451}.sub{color:#9aa7b8;font-size:13px}
    .wrap{max-width:1280px;margin:0 auto;padding:24px}.nav{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}
    .nav a,.btn{display:inline-block;background:#2563eb;color:white;text-decoration:none;border:0;border-radius:9px;padding:10px 15px;cursor:pointer;font-weight:700}
    .btn.good{background:#16945a}.btn.warn{background:#b7791f}.btn.danger{background:#c9364f}.btn.gray{background:#374151}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}.card{background:#171c25;border:1px solid #293241;border-radius:14px;padding:18px}
    h1,h2,h3{margin-top:0}.muted{color:#94a3b8}.ok{color:#4ade80;font-weight:800}.bad{color:#fb7185;font-weight:800}.pill{display:inline-block;padding:4px 9px;border-radius:999px;background:#263244;color:#dbeafe;font-size:12px}
    input,select,textarea{width:100%;padding:11px;border-radius:8px;border:1px solid #344154;background:#0f141c;color:white;margin:5px 0 12px}
    input[type=checkbox]{width:auto;margin-right:8px}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.row>*{flex:1}.row .fit{flex:0 0 auto}
    table{width:100%;border-collapse:collapse;background:#171c25;border-radius:12px;overflow:hidden}th,td{padding:12px;border-bottom:1px solid #293241;text-align:left}th{background:#202838;color:#dbeafe}
    .appcheck{display:block;padding:10px;border:1px solid #2a3648;border-radius:8px;margin:7px 0;background:#111720}.hero{background:linear-gradient(135deg,#111827,#1d2838);border:1px solid #2c3b52;border-radius:16px;padding:22px;margin-bottom:20px}
    .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:16px 0}.stat{background:#171c25;border:1px solid #293241;border-radius:12px;padding:16px}.num{font-size:30px;font-weight:900;color:#f5c451}
    form.inline{display:inline}.notice{padding:12px;border-radius:8px;background:#172554;border:1px solid #1d4ed8;margin-bottom:16px}
    '''

    def page(title, body, key):
        nav = f'''<div class="nav">
        <a href="/painel?key={key}">Resumo</a>
        <a href="/painel/clientes?key={key}">Clientes</a>
        <a href="/painel/ativacoes?key={key}">Ativações</a>
        <a href="/painel/apps?key={key}">Aplicativos</a>
        <a href="/painel/revendas?key={key}">Revendas</a>
        <a href="/?key={key}" class="btn gray">Painel antigo</a>
        </div>'''
        return HTMLResponse(f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head><body>
        <div class="top"><div><div class="brand">BBL.BOXTV • CONTROLE</div><div class="sub">Clientes, revendas e aplicativos remotos</div></div></div>
        <div class="wrap">{nav}{body}</div></body></html>''')

    @router.get('/painel', response_class=HTMLResponse)
    def dashboard(key: str = ''):
        require_admin(key)
        c = db_connect()
        counts = {}
        for name, sql in [('clientes','SELECT COUNT(*) n FROM devices'),('apps','SELECT COUNT(*) n FROM apps'),('revendas','SELECT COUNT(*) n FROM resellers'),('ativacoes','SELECT COUNT(*) n FROM activation_keys WHERE enabled=1')]:
            cur=execute(c,sql); counts[name]=rowd(cur.fetchone(),cur)['n']
        cur=execute(c,'SELECT * FROM devices ORDER BY last_seen DESC LIMIT 6'); recent=[rowd(x,cur) for x in cur.fetchall()]
        c.close()
        cards=''.join(f'''<div class="stat"><div class="num">{counts[x]}</div><div class="muted">{label}</div></div>''' for x,label in [('clientes','Clientes'),('apps','Aplicativos'),('revendas','Revendas'),('ativacoes','Ativações válidas')])
        recent_html=''.join(f'''<div class="card"><b>{esc(r.get('display_name') or r['id'])}</b><br><span class="muted">{esc(r.get('manufacturer'))} {esc(r.get('model'))}</span><br><span class="{'bad' if r.get('locked') else 'ok'}">{'BLOQUEADO' if r.get('locked') else 'ATIVO'}</span></div>''' for r in recent)
        body=f'''<div class="hero"><h1>Painel principal</h1><div class="muted">Gerencie tudo que aparece no BBL Container das TV Boxes.</div></div><div class="stats">{cards}</div><h2>Últimos clientes</h2><div class="grid">{recent_html or '<div class="card">Nenhum cliente ativado.</div>'}</div>'''
        return page('Resumo',body,key)

    @router.get('/painel/clientes', response_class=HTMLResponse)
    def clients(key: str = ''):
        require_admin(key)
        c=db_connect(); cur=execute(c,'SELECT d.*, r.name reseller_name FROM devices d LEFT JOIN resellers r ON r.id=d.reseller_id ORDER BY d.created_at DESC'); rows=[rowd(x,cur) for x in cur.fetchall()]; c.close()
        cards=''
        for r in rows:
            cards += f'''<div class="card"><div class="row"><div><h3>{esc(r.get('display_name') or 'Cliente sem nome')}</h3><div class="muted">ID: {esc(r['id'])}</div></div><div class="fit"><span class="{'bad' if r.get('locked') else 'ok'}">{'BLOQUEADO' if r.get('locked') else 'ATIVO'}</span></div></div>
            <div class="muted">Revenda: {esc(r.get('reseller_name') or 'Principal')} • Android {esc(r.get('android_version'))} • {esc(r.get('manufacturer'))} {esc(r.get('model'))}</div>
            <p>Vencimento: <b>{esc((r.get('expires_at') or '-')[:16])}</b></p>
            <a class="btn" href="/painel/client/{esc(r['id'])}/apps?key={key}">Aplicativos liberados</a>
            <form class="inline" method="post" action="/painel/client/{esc(r['id'])}/toggle?key={key}"><button class="btn {'good' if r.get('locked') else 'warn'}">{'Desbloquear' if r.get('locked') else 'Bloquear'}</button></form>
            <form class="inline" method="post" action="/painel/client/{esc(r['id'])}/delete?key={key}" onsubmit="return confirm('Excluir este cliente?')"><button class="btn danger">Excluir</button></form>
            </div>'''
        body=f'''<div class="row"><div><h1>Clientes</h1><div class="muted">As TV Boxes aparecem aqui depois que usam um código de ativação.</div></div><div class="fit"><a class="btn good" href="/painel/ativacoes?key={key}">+ NOVO CLIENTE</a></div></div><div class="grid">{cards or '<div class="card">Nenhum cliente ativado ainda.</div>'}</div>'''
        return page('Clientes',body,key)

    @router.post('/painel/client/{did}/toggle')
    def client_toggle(did: str, key: str=''):
        require_admin(key); c=db_connect(); cur=execute(c,'SELECT locked FROM devices WHERE id=?',(did,)); r=rowd(cur.fetchone(),cur)
        if not r: c.close(); raise HTTPException(404)
        new=0 if r['locked'] else 1; execute(c,'UPDATE devices SET locked=? WHERE id=?',(new,did)); log(c,did,'panel_lock','locked' if new else 'unlocked'); c.commit(); c.close()
        return RedirectResponse(f'/painel/clientes?key={key}',303)

    @router.post('/painel/client/{did}/delete')
    def client_delete(did: str, key: str=''):
        require_admin(key); c=db_connect(); execute(c,'DELETE FROM notifications WHERE device_id=?',(did,)); execute(c,'DELETE FROM logs WHERE device_id=?',(did,)); execute(c,'DELETE FROM devices WHERE id=?',(did,)); c.commit(); c.close()
        return RedirectResponse(f'/painel/clientes?key={key}',303)

    @router.get('/painel/client/{did}/apps', response_class=HTMLResponse)
    def client_apps(did: str, key: str=''):
        require_admin(key); c=db_connect(); cur=execute(c,'SELECT * FROM devices WHERE id=?',(did,)); d=rowd(cur.fetchone(),cur)
        if not d: c.close(); raise HTTPException(404)
        cur=execute(c,'SELECT * FROM apps ORDER BY name'); apps=[rowd(x,cur) for x in cur.fetchall()]; c.close()
        selected=set(json.loads(d.get('allowed_apps') or '[]'))
        checks=''.join(f'''<label class="appcheck"><input type="checkbox" name="app_ids" value="{esc(a['id'])}" {'checked' if a['id'] in selected or a.get('package_name') in selected else ''}><b>{esc(a['name'])}</b><br><span class="muted">{esc(a.get('package_name'))} • {esc(a.get('version_name'))}</span></label>''' for a in apps)
        body=f'''<h1>Apps de {esc(d.get('display_name') or did)}</h1><div class="notice">Marque os aplicativos que este cliente pode ver no BBL Container. Ao retirar um app, ele deixa de ser autorizado na próxima sincronização.</div><form method="post" action="/painel/client/{esc(did)}/apps?key={key}">{checks or '<div class="card">Cadastre aplicativos primeiro.</div>'}<button class="btn good">SALVAR APLICATIVOS</button></form>'''
        return page('Apps do cliente',body,key)

    @router.post('/painel/client/{did}/apps')
    async def client_apps_save(did: str, key: str='', app_ids: list[str] = Form(default=[])):
        require_admin(key); c=db_connect(); execute(c,'UPDATE devices SET allowed_apps=?, layout_id=NULL WHERE id=?',(json.dumps(app_ids),did)); log(c,did,'apps_update',json.dumps(app_ids)); c.commit(); c.close()
        return RedirectResponse(f'/painel/client/{did}/apps?key={key}',303)

    @router.get('/painel/ativacoes', response_class=HTMLResponse)
    def activations(key: str=''):
        require_admin(key); c=db_connect(); cur=execute(c,'SELECT id,name FROM resellers WHERE enabled=1 ORDER BY name'); rs=[rowd(x,cur) for x in cur.fetchall()]; cur=execute(c,'SELECT * FROM activation_keys ORDER BY created_at DESC'); keys=[rowd(x,cur) for x in cur.fetchall()]; c.close()
        ropts='<option value="">Principal</option>'+''.join(f'<option value="{esc(r["id"])}">{esc(r["name"])}</option>' for r in rs)
        rows=''.join(f'''<tr><td><b>{esc(x['key'])}</b></td><td>{esc(x.get('label'))}</td><td>{'ATIVA' if x.get('enabled') else 'DESATIVADA'}</td><td><form class="inline" method="post" action="/painel/ativacoes/{esc(x['key'])}/toggle?key={key}"><button class="btn {'warn' if x.get('enabled') else 'good'}">{'Desativar' if x.get('enabled') else 'Ativar'}</button></form></td></tr>''' for x in keys)
        body=f'''<h1>Ativações / Novo cliente</h1><div class="grid"><div class="card"><h3>Criar código para cliente</h3><form method="post" action="/painel/ativacoes/create?key={key}"><input name="label" placeholder="Nome do cliente (ex.: João Sala)"><input name="custom_key" placeholder="Código personalizado (opcional)"><select name="reseller_id">{ropts}</select><button class="btn good">GERAR CÓDIGO</button></form></div><div class="card"><h3>Como funciona</h3><div class="muted">Crie o código aqui. Na TV Box, digite o código no BBL Container e clique ATIVAR. O aparelho aparecerá automaticamente em Clientes.</div></div></div><h2>Códigos</h2><table><tr><th>Código</th><th>Cliente</th><th>Status</th><th>Ação</th></tr>{rows}</table>'''
        return page('Ativações',body,key)

    @router.post('/painel/ativacoes/create')
    def activation_create(key: str='', label: str=Form(''), custom_key: str=Form(''), reseller_id: str=Form('')):
        require_admin(key); code=(custom_key.strip().upper() if custom_key.strip() else f"BBL-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}")
        c=db_connect()
        try: execute(c,'INSERT INTO activation_keys(key,enabled,label,created_at,reseller_id) VALUES(?,?,?,?,?)',(code,1,label.strip(),now_iso(),reseller_id or None)); c.commit()
        except Exception: c.rollback(); c.close(); raise HTTPException(400,'código já existe')
        c.close(); return RedirectResponse(f'/painel/ativacoes?key={key}',303)

    @router.post('/painel/ativacoes/{activation}/toggle')
    def activation_toggle(activation: str, key: str=''):
        require_admin(key); c=db_connect(); cur=execute(c,'SELECT enabled FROM activation_keys WHERE key=?',(activation,)); r=rowd(cur.fetchone(),cur)
        if r: execute(c,'UPDATE activation_keys SET enabled=? WHERE key=?',(0 if r['enabled'] else 1,activation)); c.commit()
        c.close(); return RedirectResponse(f'/painel/ativacoes?key={key}',303)

    @router.get('/painel/apps', response_class=HTMLResponse)
    def apps_page(key: str=''):
        require_admin(key); c=db_connect(); cur=execute(c,'SELECT * FROM apps ORDER BY created_at DESC'); apps=[rowd(x,cur) for x in cur.fetchall()]; c.close()
        cards=''.join(f'''<div class="card"><h3>{esc(a['name'])}</h3><div class="muted">{esc(a.get('package_name'))}<br>Versão {esc(a.get('version_name'))} • {round((a.get('size_bytes') or 0)/1048576,1)} MB</div><br><form method="post" action="/painel/apps/{esc(a['id'])}/delete?key={key}" onsubmit="return confirm('Excluir este app do painel e retirar das autorizações?')"><button class="btn danger">Excluir aplicativo</button></form></div>''' for a in apps)
        body=f'''<div class="row"><div><h1>Aplicativos</h1><div class="muted">Envie APKs que poderão ser liberados para os clientes.</div></div></div><div class="card"><h3>Adicionar / atualizar APK</h3><form method="post" enctype="multipart/form-data" action="/painel/apps/upload?key={key}"><input type="file" name="apk" accept=".apk" required><button class="btn good">ENVIAR APK</button></form></div><div class="grid">{cards or '<div class="card">Nenhum aplicativo cadastrado.</div>'}</div>'''
        return page('Aplicativos',body,key)

    @router.post('/painel/apps/upload')
    async def apps_upload(key: str='', apk: UploadFile=File(...)):
        require_admin(key)
        if not apk.filename or not apk.filename.lower().endswith('.apk'): raise HTTPException(400,'envie um arquivo APK')
        safe=f"{secrets.token_hex(8)}.apk"; dest=Path(upload_dir)/safe
        data=await apk.read(); dest.write_bytes(data)
        meta=apk_meta(dest); import hashlib; sha=hashlib.sha256(data).hexdigest(); aid=secrets.token_hex(8)
        c=db_connect(); cur=execute(c,'SELECT id,filename FROM apps WHERE package_name=?',(meta.get('package_name') or '',)); old=rowd(cur.fetchone(),cur) if meta.get('package_name') else None
        if old:
            oldp=Path(upload_dir)/old['filename']; execute(c,'UPDATE apps SET name=?,version_name=?,version_code=?,filename=?,size_bytes=?,sha256=?,created_at=? WHERE id=?',(meta['name'],meta.get('version_name',''),meta.get('version_code',''),safe,len(data),sha,now_iso(),old['id'])); aid=old['id']
            try:
                if oldp.exists() and oldp != dest: oldp.unlink()
            except: pass
        else:
            execute(c,'INSERT INTO apps(id,name,package_name,version_name,version_code,filename,size_bytes,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(aid,meta['name'],meta.get('package_name',''),meta.get('version_name',''),meta.get('version_code',''),safe,len(data),sha,now_iso()))
        c.commit(); c.close(); return RedirectResponse(f'/painel/apps?key={key}',303)

    @router.post('/painel/apps/{aid}/delete')
    def app_delete(aid: str, key: str=''):
        require_admin(key); c=db_connect(); cur=execute(c,'SELECT filename,package_name FROM apps WHERE id=?',(aid,)); a=rowd(cur.fetchone(),cur)
        if a:
            cur=execute(c,'SELECT id,allowed_apps FROM devices'); devices=[rowd(x,cur) for x in cur.fetchall()]
            for d in devices:
                arr=json.loads(d.get('allowed_apps') or '[]'); arr=[x for x in arr if x not in (aid,a.get('package_name'))]; execute(c,'UPDATE devices SET allowed_apps=? WHERE id=?',(json.dumps(arr),d['id']))
            execute(c,'DELETE FROM apps WHERE id=?',(aid,)); c.commit()
            try:
                p=Path(upload_dir)/a['filename'];
                if p.exists(): p.unlink()
            except: pass
        c.close(); return RedirectResponse(f'/painel/apps?key={key}',303)

    @router.get('/painel/revendas', response_class=HTMLResponse)
    def resellers(key: str=''):
        require_admin(key); c=db_connect(); cur=execute(c,'SELECT * FROM resellers ORDER BY created_at DESC'); rs=[rowd(x,cur) for x in cur.fetchall()]; c.close()
        cards=''.join(f'''<div class="card"><h3>{esc(r['name'])}</h3><div class="muted">Chave da revenda: <b>{esc(r['access_key'])}</b><br>Limite: {esc(r['max_devices'])} clientes<br>Marca: {esc(r.get('brand_name'))}</div><p><span class="{'ok' if r.get('enabled') else 'bad'}">{'ATIVA' if r.get('enabled') else 'DESATIVADA'}</span></p><form method="post" action="/painel/revendas/{esc(r['id'])}/toggle?key={key}"><button class="btn {'warn' if r.get('enabled') else 'good'}">{'Desativar' if r.get('enabled') else 'Ativar'}</button></form></div>''' for r in rs)
        body=f'''<h1>Revendas</h1><div class="card"><h3>Criar revenda</h3><form method="post" action="/painel/revendas/create?key={key}"><div class="row"><div><input name="name" placeholder="Nome da revenda" required></div><div><input type="number" name="max_devices" value="50" min="1" placeholder="Limite de clientes"></div></div><input name="brand_name" value="BBL.BOXTV" placeholder="Nome da marca"><button class="btn good">CRIAR REVENDA</button></form></div><div class="grid">{cards or '<div class="card">Nenhuma revenda cadastrada.</div>'}</div>'''
        return page('Revendas',body,key)

    @router.post('/painel/revendas/create')
    def reseller_create(key: str='', name: str=Form(...), max_devices: int=Form(50), brand_name: str=Form('BBL.BOXTV')):
        require_admin(key); rid=secrets.token_hex(6); access=f"REV-{secrets.token_hex(4).upper()}"; c=db_connect(); execute(c,'INSERT INTO resellers(id,name,access_key,enabled,max_devices,brand_name,wallpaper_url,logo_url,message,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,name.strip(),access,1,max(1,max_devices),brand_name.strip() or 'BBL.BOXTV','','','',now_iso())); c.commit(); c.close(); return RedirectResponse(f'/painel/revendas?key={key}',303)

    @router.post('/painel/revendas/{rid}/toggle')
    def reseller_toggle(rid: str, key: str=''):
        require_admin(key); c=db_connect(); cur=execute(c,'SELECT enabled FROM resellers WHERE id=?',(rid,)); r=rowd(cur.fetchone(),cur)
        if r: execute(c,'UPDATE resellers SET enabled=? WHERE id=?',(0 if r['enabled'] else 1,rid)); c.commit()
        c.close(); return RedirectResponse(f'/painel/revendas?key={key}',303)

    app.include_router(router)
