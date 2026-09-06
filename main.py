import os, secrets, json, hashlib, shutil
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from pydantic import BaseModel

DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///./tvbox.db')
ADMIN_KEY=os.getenv('ADMIN_KEY','troque-esta-chave')
DEFAULT_ACTIVATION_KEY=os.getenv('ACTIVATION_KEY','BBL-2026')
UPLOAD_DIR=Path(os.getenv('UPLOAD_DIR','./uploads')); UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='BBL.BOXTV Manager API',version='4.0.0')

def now_iso(): return datetime.now(timezone.utc).isoformat()
def is_postgres(): return DATABASE_URL.startswith(('postgres://','postgresql://'))
def db_connect():
    if is_postgres():
        import psycopg
        return psycopg.connect(DATABASE_URL.replace('postgres://','postgresql://',1),autocommit=False)
    import sqlite3
    p=DATABASE_URL.replace('sqlite:///','',1) if DATABASE_URL.startswith('sqlite:///') else DATABASE_URL
    c=sqlite3.connect(p); c.row_factory=sqlite3.Row; return c
def execute(c,sql,params=()):
    if is_postgres(): sql=sql.replace('?','%s')
    cur=c.cursor(); cur.execute(sql,params); return cur
def rowd(row,cur=None):
    if row is None:return None
    try:return dict(row)
    except Exception:
        cols=[getattr(d,'name',d[0]) for d in cur.description]; return dict(zip(cols,row))
def addcol(c,stmt):
    try: execute(c,stmt); c.commit()
    except Exception: c.rollback()
def init_db():
    c=db_connect()
    execute(c,"""CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,token TEXT UNIQUE NOT NULL,activation_key TEXT,locked INTEGER NOT NULL DEFAULT 0,allowed_apps TEXT NOT NULL DEFAULT '[]',managed_apps TEXT NOT NULL DEFAULT '[]',display_name TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_at TEXT,last_seen TEXT)""")
    execute(c,"""CREATE TABLE IF NOT EXISTS activation_keys(key TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 1,label TEXT NOT NULL DEFAULT '',created_at TEXT)""")
    execute(c,"""CREATE TABLE IF NOT EXISTS apps(id TEXT PRIMARY KEY,name TEXT NOT NULL,package_name TEXT NOT NULL DEFAULT '',version_name TEXT NOT NULL DEFAULT '',version_code TEXT NOT NULL DEFAULT '',filename TEXT NOT NULL,size_bytes INTEGER NOT NULL DEFAULT 0,sha256 TEXT NOT NULL DEFAULT '',created_at TEXT)""")
    execute(c,"""CREATE TABLE IF NOT EXISTS layouts(id TEXT PRIMARY KEY,name TEXT NOT NULL,app_ids TEXT NOT NULL DEFAULT '[]',created_at TEXT)""")
    execute(c,"""CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,device_id TEXT,title TEXT,message TEXT,created_at TEXT,read_at TEXT)""")
    execute(c,"""CREATE TABLE IF NOT EXISTS logs(id TEXT PRIMARY KEY,device_id TEXT,event TEXT,detail TEXT,created_at TEXT)""")
    execute(c,"""CREATE TABLE IF NOT EXISTS resellers(id TEXT PRIMARY KEY,name TEXT NOT NULL,access_key TEXT UNIQUE NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,max_devices INTEGER NOT NULL DEFAULT 50,brand_name TEXT NOT NULL DEFAULT 'BBL.BOXTV',wallpaper_url TEXT NOT NULL DEFAULT '',logo_url TEXT NOT NULL DEFAULT '',message TEXT NOT NULL DEFAULT '',created_at TEXT)""")
    c.commit()
    for s in ["ALTER TABLE devices ADD COLUMN display_name TEXT NOT NULL DEFAULT ''","ALTER TABLE devices ADD COLUMN notes TEXT NOT NULL DEFAULT ''","ALTER TABLE devices ADD COLUMN expires_at TEXT","ALTER TABLE devices ADD COLUMN launcher_expires_at TEXT","ALTER TABLE devices ADD COLUMN layout_id TEXT","ALTER TABLE devices ADD COLUMN manufacturer TEXT NOT NULL DEFAULT ''","ALTER TABLE devices ADD COLUMN model TEXT NOT NULL DEFAULT ''","ALTER TABLE devices ADD COLUMN android_version TEXT NOT NULL DEFAULT ''","ALTER TABLE devices ADD COLUMN launcher_version TEXT NOT NULL DEFAULT ''","ALTER TABLE activation_keys ADD COLUMN label TEXT NOT NULL DEFAULT ''","ALTER TABLE activation_keys ADD COLUMN created_at TEXT","ALTER TABLE activation_keys ADD COLUMN reseller_id TEXT","ALTER TABLE devices ADD COLUMN reseller_id TEXT","ALTER TABLE devices ADD COLUMN brand_name TEXT NOT NULL DEFAULT ''","ALTER TABLE devices ADD COLUMN wallpaper_url TEXT NOT NULL DEFAULT ''","ALTER TABLE devices ADD COLUMN logo_url TEXT NOT NULL DEFAULT ''","ALTER TABLE devices ADD COLUMN message TEXT NOT NULL DEFAULT ''"]: addcol(c,s)
    try: execute(c,'INSERT INTO activation_keys(key,enabled,label,created_at) VALUES(?,?,?,?)',(DEFAULT_ACTIVATION_KEY,1,'Chave padrão',now_iso())); c.commit()
    except Exception:c.rollback()
    c.close()
@app.on_event('startup')
def startup(): init_db()
def bearer(a): return a.split(' ',1)[1].strip() if a and a.lower().startswith('bearer ') else None
def admin_ok(k): return bool(k) and secrets.compare_digest(k,ADMIN_KEY)
def log(c,d,e,detail=''): execute(c,'INSERT INTO logs(id,device_id,event,detail,created_at) VALUES(?,?,?,?,?)',(secrets.token_hex(8),d,e,detail,now_iso()))

def apk_meta(path:Path):
    meta={'name':path.stem,'package_name':'','version_name':'','version_code':''}
    try:
        from androguard.core.apk import APK
        a=APK(str(path)); meta={'name':a.get_app_name() or path.stem,'package_name':a.get_package() or '', 'version_name':a.get_androidversion_name() or '', 'version_code':str(a.get_androidversion_code() or '')}
    except Exception: pass
    return meta

class EnrollBody(BaseModel):
    activationCode:Optional[str]=None; activation:Optional[str]=None; activation_code:Optional[str]=None; enrollmentKey:Optional[str]=None; deviceId:Optional[str]=None; device_id:Optional[str]=None
    manufacturer:Optional[str]=None; model:Optional[str]=None; android_version:Optional[str]=None; launcher_version:Optional[str]=None
@app.get('/health')
def health(): return {'ok':True,'service':'bbl-boxtv-manager','version':'4.0.0'}
@app.post('/api/enroll')
def enroll(b:EnrollBody):
    key=b.activationCode or b.activation or b.activation_code or b.enrollmentKey
    if not key: raise HTTPException(400,'activation key required')
    c=db_connect(); cur=execute(c,'SELECT key,reseller_id FROM activation_keys WHERE key=? AND enabled=1',(key,)); kr=rowd(cur.fetchone(),cur)
    if not kr: c.close(); raise HTTPException(403,'invalid activation key')
    did=b.deviceId or b.device_id or secrets.token_hex(5).upper(); cur=execute(c,'SELECT * FROM devices WHERE id=?',(did,)); r=rowd(cur.fetchone(),cur)
    if r: token=r['token']; execute(c,'UPDATE devices SET last_seen=? WHERE id=?',(now_iso(),did))
    else:
        token=secrets.token_urlsafe(32); execute(c,'INSERT INTO devices(id,token,activation_key,created_at,last_seen,manufacturer,model,android_version,launcher_version,reseller_id) VALUES(?,?,?,?,?,?,?,?,?,?)',(did,token,key,now_iso(),now_iso(),b.manufacturer or '',b.model or '',b.android_version or '',b.launcher_version or '',kr.get('reseller_id'))); log(c,did,'enroll','device activated')
    c.commit(); c.close(); return {'device_id':did,'device_token':token,'deviceId':did,'deviceToken':token,'token':token,'status':'ok'}

def device_payload(c,r):
    appids=[]
    if r.get('layout_id'):
        cur=execute(c,'SELECT app_ids FROM layouts WHERE id=?',(r['layout_id'],)); lr=rowd(cur.fetchone(),cur)
        if lr: appids=json.loads(lr['app_ids'] or '[]')
    if not appids: appids=json.loads(r.get('allowed_apps') or '[]')
    apps=[]
    for aid in appids:
        cur=execute(c,'SELECT * FROM apps WHERE id=? OR package_name=?',(aid,aid)); ar=rowd(cur.fetchone(),cur)
        if ar: apps.append({k:ar.get(k) for k in ['id','name','package_name','version_name','version_code','size_bytes','sha256']}|{'download_url':f"/api/apps/{ar['id']}/download"})
    exp=r.get('expires_at'); expired=False
    if exp:
        try: expired=datetime.fromisoformat(exp.replace('Z','+00:00'))<datetime.now(timezone.utc)
        except: pass
    locked=bool(r.get('locked')) or expired
    brand={'name':r.get('brand_name') or 'BBL.BOXTV','wallpaper_url':r.get('wallpaper_url') or '','logo_url':r.get('logo_url') or '','message':r.get('message') or ''}
    if r.get('reseller_id'):
        cur=execute(c,'SELECT * FROM resellers WHERE id=?',(r.get('reseller_id'),)); rr=rowd(cur.fetchone(),cur)
        if rr:
            if not r.get('brand_name'): brand['name']=rr.get('brand_name') or brand['name']
            if not r.get('wallpaper_url'): brand['wallpaper_url']=rr.get('wallpaper_url') or ''
            if not r.get('logo_url'): brand['logo_url']=rr.get('logo_url') or ''
            if not r.get('message'): brand['message']=rr.get('message') or ''
    p={'locked':locked,'expired':expired,'expires_at':exp,'layout_id':r.get('layout_id'),'apps':apps,'allowed_apps':[x.get('package_name') for x in apps if x.get('package_name')]}
    return {**p,'branding':brand,'message':brand.get('message',''),'policy':p}
@app.get('/api/devices/{did}/policy')
def policy(did:str,authorization:Optional[str]=Header(None)):
    c=db_connect(); cur=execute(c,'SELECT * FROM devices WHERE id=?',(did,)); r=rowd(cur.fetchone(),cur); t=bearer(authorization)
    if not r or not t or not secrets.compare_digest(t,r['token']): c.close(); raise HTTPException(401,'unauthorized')
    execute(c,'UPDATE devices SET last_seen=? WHERE id=?',(now_iso(),did)); c.commit(); out=device_payload(c,r); c.close(); return out
@app.post('/api/devices/{did}/policy')
def policy_post(did:str,authorization:Optional[str]=Header(None)): return policy(did,authorization)
@app.get('/api/devices/{did}/notifications')
def device_notifications(did:str,authorization:Optional[str]=Header(None)):
    c=db_connect(); cur=execute(c,'SELECT token FROM devices WHERE id=?',(did,)); r=rowd(cur.fetchone(),cur); t=bearer(authorization)
    if not r or not t or not secrets.compare_digest(t,r['token']): c.close(); raise HTTPException(401)
    cur=execute(c,'SELECT id,title,message,created_at FROM notifications WHERE device_id=? AND read_at IS NULL ORDER BY created_at DESC',(did,)); out=[rowd(x,cur) for x in cur.fetchall()]; c.close(); return out
@app.get('/api/apps/{aid}/download')
def app_download(aid:str):
    c=db_connect(); cur=execute(c,'SELECT filename FROM apps WHERE id=?',(aid,)); r=rowd(cur.fetchone(),cur); c.close()
    if not r: raise HTTPException(404)
    p=UPLOAD_DIR/r['filename']
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p,media_type='application/vnd.android.package-archive',filename=r['filename'])

CSS='''body{font-family:Arial,sans-serif;background:#f4f7fb;color:#18202a;margin:0}.bar{background:#1473e6;color:white;padding:18px 4%;font-size:22px;font-weight:bold}.wrap{max-width:1250px;margin:24px auto;padding:0 18px}.nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.nav a,button{background:#1473e6;color:white;border:0;border-radius:8px;padding:10px 14px;text-decoration:none;cursor:pointer}.card{background:white;border:1px solid #dfe6ee;border-radius:12px;padding:16px;margin:10px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.muted{color:#687789}.bad{color:#d6293e}.ok{color:#16a05d}input,textarea,select{box-sizing:border-box;width:100%;padding:10px;margin:5px 0 10px;border:1px solid #cfd8e3;border-radius:8px}.danger{background:#d6293e}.good{background:#16a05d}.pill{padding:4px 8px;border-radius:99px;background:#e9eff7;font-size:12px}'''
def nav(key): return f'''<div class="nav"><a href="/?key={key}">Dispositivos</a><a href="/admin/activation-keys?key={key}">Ativações</a><a href="/admin/apps?key={key}">Aplicativos</a><a href="/admin/layouts?key={key}">Layouts</a><a href="/admin/logs?key={key}">LOGs</a><a href="/admin/branding?key={key}">Visual</a><a href="/admin/resellers?key={key}">Revendas</a></div>'''
def page(title,body,key=''): return f'<!doctype html><meta name="viewport" content="width=device-width"><title>{title}</title><style>{CSS}</style><div class="bar">BBL.BOXTV • {title}</div><div class="wrap">{nav(key) if key else ""}{body}</div>'
@app.get('/',response_class=HTMLResponse)
def dashboard(key:str=''):
    if not admin_ok(key): return page('Painel','<form><input name="key" type="password" placeholder="ADMIN_KEY"><button>Entrar</button></form>')
    c=db_connect(); cur=execute(c,'SELECT * FROM devices ORDER BY created_at DESC'); rows=[rowd(x,cur) for x in cur.fetchall()]; cur=execute(c,'SELECT id,name FROM layouts ORDER BY name'); layouts=[rowd(x,cur) for x in cur.fetchall()]; c.close(); cards=''
    opts=lambda current: '<option value="">Sem layout</option>'+''.join(f'<option value="{x["id"]}" {"selected" if x["id"]==current else ""}>{x["name"]}</option>' for x in layouts)
    for r in rows:
        state='BLOQUEADO' if r['locked'] else 'ATIVO'; cls='bad' if r['locked'] else 'ok'
        cards+=f'''<div class="card"><h3>{r.get('display_name') or 'Sem nome'} <span class="{cls}">{state}</span></h3><div class="muted">ID: {r['id']} • último contato: {r.get('last_seen') or '-'}</div><form method="post" action="/admin/device/{r['id']}/edit?key={key}"><input name="display_name" value="{r.get('display_name') or ''}" placeholder="Nome do cliente"><input type="datetime-local" name="expires_at" value="{(r.get('expires_at') or '')[:16]}"><select name="layout_id">{opts(r.get('layout_id'))}</select><textarea name="notes" placeholder="Anotações">{r.get('notes') or ''}</textarea><button>Salvar</button></form><form method="post" action="/admin/device/{r['id']}/toggle?key={key}"><button class="{'good' if r['locked'] else 'danger'}">{'Desbloquear' if r['locked'] else 'Bloquear'}</button></form><form method="post" action="/admin/device/{r['id']}/notify?key={key}"><input name="title" placeholder="Título da notificação"><input name="message" placeholder="Mensagem"><button>Enviar notificação</button></form><div class="muted">{r.get('manufacturer','')} {r.get('model','')} • Android {r.get('android_version','')} • Launcher {r.get('launcher_version','')}</div></div>'''
    return page('Dispositivos',f'<h2>Clientes / dispositivos ({len(rows)})</h2><div class="grid">{cards or "<div class=card>Nenhum dispositivo.</div>"}</div>',key)
@app.post('/admin/device/{did}/toggle')
def toggle(did:str,key:str):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); cur=execute(c,'SELECT locked FROM devices WHERE id=?',(did,)); r=rowd(cur.fetchone(),cur)
    if not r: c.close(); raise HTTPException(404)
    execute(c,'UPDATE devices SET locked=? WHERE id=?',(0 if r['locked'] else 1,did)); log(c,did,'lock','unlocked' if r['locked'] else 'locked'); c.commit(); c.close(); return RedirectResponse(f'/?key={key}',303)
@app.post('/admin/device/{did}/edit')
def edit(did:str,key:str,display_name:str=Form(''),expires_at:str=Form(''),layout_id:str=Form(''),notes:str=Form('')):
    if not admin_ok(key): raise HTTPException(401)
    exp=(expires_at+':00+00:00') if expires_at else None; c=db_connect(); execute(c,'UPDATE devices SET display_name=?,expires_at=?,layout_id=?,notes=? WHERE id=?',(display_name.strip(),exp,layout_id or None,notes.strip(),did)); log(c,did,'edit','device settings updated'); c.commit(); c.close(); return RedirectResponse(f'/?key={key}',303)
@app.post('/admin/device/{did}/notify')
def notify(did:str,key:str,title:str=Form(...),message:str=Form(...)):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); execute(c,'INSERT INTO notifications(id,device_id,title,message,created_at) VALUES(?,?,?,?,?)',(secrets.token_hex(8),did,title.strip(),message.strip(),now_iso())); log(c,did,'notification',title.strip()); c.commit(); c.close(); return RedirectResponse(f'/?key={key}',303)

@app.get('/admin/activation-keys',response_class=HTMLResponse)
def activation_keys_page(key:str=''):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); cur=execute(c,'SELECT * FROM activation_keys ORDER BY created_at DESC'); rows=[rowd(x,cur) for x in cur.fetchall()]; c.close()
    cards=''
    for r in rows:
        state='ATIVA' if r['enabled'] else 'DESATIVADA'; cls='ok' if r['enabled'] else 'bad'
        action_cls='danger' if r['enabled'] else 'good'; action_text='Desativar' if r['enabled'] else 'Ativar'
        cards+=f'''<div class="card"><h3>{r['key']} <span class="{cls}">{state}</span></h3><div class="muted">{r.get('label') or 'Sem descrição'} • criada em {r.get('created_at') or '-'}</div><form method="post" action="/admin/activation-keys/{r['key']}/toggle?key={key}"><button class="{action_cls}">{action_text}</button></form></div>'''
    empty='<div class="card">Nenhum código cadastrado.</div>'
    body=f'''<h2>Códigos de ativação</h2><div class="card"><form method="post" action="/admin/activation-keys/create?key={key}"><input name="label" placeholder="Nome/cliente (opcional)"><input name="custom_key" placeholder="Código personalizado (deixe vazio para gerar automático)"><button>Gerar código de ativação</button></form><p class="muted">O código automático é criado no formato BBL-XXXX-XXXX.</p></div><div class="grid">{cards or empty}</div>'''
    return page('Ativações',body,key)

@app.post('/admin/activation-keys/create')
def activation_key_create(key:str,label:str=Form(''),custom_key:str=Form('')):
    if not admin_ok(key): raise HTTPException(401)
    activation=(custom_key.strip().upper() if custom_key.strip() else f"BBL-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}")
    c=db_connect()
    try:
        execute(c,'INSERT INTO activation_keys(key,enabled,label,created_at) VALUES(?,?,?,?)',(activation,1,label.strip(),now_iso())); c.commit()
    except Exception:
        c.rollback(); c.close(); raise HTTPException(409,'código de ativação já existe')
    c.close(); return RedirectResponse(f'/admin/activation-keys?key={key}',303)

@app.post('/admin/activation-keys/{activation}/toggle')
def activation_key_toggle(activation:str,key:str):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); cur=execute(c,'SELECT enabled FROM activation_keys WHERE key=?',(activation,)); r=rowd(cur.fetchone(),cur)
    if not r: c.close(); raise HTTPException(404)
    execute(c,'UPDATE activation_keys SET enabled=? WHERE key=?',(0 if r['enabled'] else 1,activation)); c.commit(); c.close()
    return RedirectResponse(f'/admin/activation-keys?key={key}',303)

@app.get('/admin/apps',response_class=HTMLResponse)
def apps_page(key:str=''):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); cur=execute(c,'SELECT * FROM apps ORDER BY created_at DESC'); rows=[rowd(x,cur) for x in cur.fetchall()]; c.close(); cards=''.join(f'<div class="card"><b>{r["name"]}</b><br><span class="muted">{r["package_name"]} • {r["version_name"]} • {round(r["size_bytes"]/1048576,2)} MB</span></div>' for r in rows)
    body=f'''<h2>Upload automático de APK</h2><div class="card"><form method="post" action="/admin/apps/upload?key={key}" enctype="multipart/form-data"><input type="file" name="apk" accept=".apk" required><button>Enviar APK</button></form><p class="muted">O servidor extrai automaticamente nome, pacote e versão quando possível, além de SHA-256 e tamanho.</p></div><div class="grid">{cards}</div>'''; return page('Aplicativos',body,key)
@app.post('/admin/apps/upload')
def upload_apk(key:str,apk:UploadFile=File(...)):
    if not admin_ok(key): raise HTTPException(401)
    if not apk.filename.lower().endswith('.apk'): raise HTTPException(400,'arquivo precisa ser APK')
    aid=secrets.token_hex(8); fname=f'{aid}.apk'; p=UPLOAD_DIR/fname
    with p.open('wb') as f: shutil.copyfileobj(apk.file,f)
    h=hashlib.sha256(p.read_bytes()).hexdigest(); m=apk_meta(p); c=db_connect(); execute(c,'INSERT INTO apps(id,name,package_name,version_name,version_code,filename,size_bytes,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(aid,m['name'],m['package_name'],m['version_name'],m['version_code'],fname,p.stat().st_size,h,now_iso())); c.commit(); c.close(); return RedirectResponse(f'/admin/apps?key={key}',303)
@app.get('/admin/layouts',response_class=HTMLResponse)
def layouts_page(key:str=''):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); cur=execute(c,'SELECT * FROM apps ORDER BY name'); apps=[rowd(x,cur) for x in cur.fetchall()]; cur=execute(c,'SELECT * FROM layouts ORDER BY name'); layouts=[rowd(x,cur) for x in cur.fetchall()]; c.close(); checks=''.join(f'<label><input style="width:auto" type="checkbox" name="app_ids" value="{a["id"]}"> {a["name"]} ({a["package_name"]})</label><br>' for a in apps); cards=''.join(f'<div class="card"><b>{l["name"]}</b><br><span class="muted">{len(json.loads(l["app_ids"] or "[]"))} aplicativo(s)</span></div>' for l in layouts)
    return page('Layouts',f'<div class="card"><form method="post" action="/admin/layouts/create?key={key}"><input name="name" placeholder="Nome do layout" required>{checks}<br><button>Criar layout</button></form></div><div class="grid">{cards}</div>',key)
@app.post('/admin/layouts/create')
def create_layout(key:str,name:str=Form(...),app_ids:list[str]=Form(default=[])):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); execute(c,'INSERT INTO layouts(id,name,app_ids,created_at) VALUES(?,?,?,?)',(secrets.token_hex(8),name.strip(),json.dumps(app_ids),now_iso())); c.commit(); c.close(); return RedirectResponse(f'/admin/layouts?key={key}',303)
@app.get('/admin/logs',response_class=HTMLResponse)
def logs_page(key:str=''):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); cur=execute(c,'SELECT * FROM logs ORDER BY created_at DESC'); rows=[rowd(x,cur) for x in cur.fetchall()][:300]; c.close(); body=''.join(f'<div class="card"><b>{r["event"]}</b> • {r.get("device_id") or "-"}<br><span class="muted">{r["created_at"]} • {r.get("detail") or ""}</span></div>' for r in rows); return page('LOGs',body,key)

@app.get('/api/media/{filename}')
def media(filename:str):
    safe=Path(filename).name
    p=UPLOAD_DIR/safe
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p)

def save_image(upload:Optional[UploadFile],prefix:str):
    if not upload or not upload.filename: return ''
    ext=Path(upload.filename).suffix.lower()
    if ext not in ['.png','.jpg','.jpeg','.webp']: raise HTTPException(400,'imagem invalida')
    fname=f'{prefix}-{secrets.token_hex(6)}{ext}'
    p=UPLOAD_DIR/fname
    with p.open('wb') as f: shutil.copyfileobj(upload.file,f)
    return f'/api/media/{fname}'

@app.get('/admin/branding',response_class=HTMLResponse)
def branding_page(key:str=''):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); cur=execute(c,'SELECT * FROM devices ORDER BY created_at DESC'); rows=[rowd(x,cur) for x in cur.fetchall()]; c.close()
    cards=''
    for r in rows:
        did=r['id']
        cards += f'<div class="card"><h3>{r.get("display_name") or did}</h3><div class="muted">{did}</div><form method="post" enctype="multipart/form-data" action="/admin/device/{did}/branding?key={key}"><input name="brand_name" value="{r.get("brand_name") or ""}" placeholder="Nome da marca"><input name="message" value="{r.get("message") or ""}" placeholder="Mensagem na tela"><label>Logomarca</label><input type="file" name="logo" accept="image/*"><label>Papel de parede</label><input type="file" name="wallpaper" accept="image/*"><button>Atualizar visual</button></form></div>'
    return page('Visual',f'<h2>Logomarca, papel de parede e mensagem</h2><div class="grid">{cards or "<div class=card>Nenhum aparelho.</div>"}</div>',key)

@app.post('/admin/device/{did}/branding')
def device_branding(did:str,key:str,brand_name:str=Form(''),message:str=Form(''),logo:Optional[UploadFile]=File(None),wallpaper:Optional[UploadFile]=File(None)):
    if not admin_ok(key): raise HTTPException(401)
    logo_url=save_image(logo,'logo'); wallpaper_url=save_image(wallpaper,'wallpaper')
    c=db_connect(); cur=execute(c,'SELECT * FROM devices WHERE id=?',(did,)); r=rowd(cur.fetchone(),cur)
    if not r: c.close(); raise HTTPException(404)
    execute(c,'UPDATE devices SET brand_name=?,message=?,logo_url=?,wallpaper_url=? WHERE id=?',(brand_name.strip(),message.strip(),logo_url or r.get('logo_url',''),wallpaper_url or r.get('wallpaper_url',''),did)); log(c,did,'branding','visual atualizado'); c.commit(); c.close()
    return RedirectResponse(f'/admin/branding?key={key}',303)

@app.get('/admin/resellers',response_class=HTMLResponse)
def resellers_page(key:str=''):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); cur=execute(c,'SELECT * FROM resellers ORDER BY created_at DESC'); rows=[rowd(x,cur) for x in cur.fetchall()]; c.close()
    cards=''
    for r in rows:
        state='ATIVA' if r['enabled'] else 'DESATIVADA'
        cards += f'<div class="card"><h3>{r["name"]} - {state}</h3><div class="muted">Limite: {r["max_devices"]} aparelhos</div><div><b>Chave:</b> {r["access_key"]}</div><div class="muted">/revenda?token={r["access_key"]}</div><form method="post" action="/admin/resellers/{r["id"]}/toggle?key={key}"><button>{"Desativar" if r["enabled"] else "Ativar"}</button></form></div>'
    body=f'<h2>Revendas</h2><div class="card"><form method="post" action="/admin/resellers/create?key={key}"><input name="name" placeholder="Nome da revenda" required><input name="max_devices" type="number" value="50" min="1"><input name="brand_name" value="BBL.BOXTV" placeholder="Marca"><button>Criar revenda</button></form></div><div class="grid">{cards}</div>'
    return page('Revendas',body,key)

@app.post('/admin/resellers/create')
def reseller_create(key:str,name:str=Form(...),max_devices:int=Form(50),brand_name:str=Form('BBL.BOXTV')):
    if not admin_ok(key): raise HTTPException(401)
    rid=secrets.token_hex(6); access=secrets.token_urlsafe(18)
    c=db_connect(); execute(c,'INSERT INTO resellers(id,name,access_key,enabled,max_devices,brand_name,created_at) VALUES(?,?,?,?,?,?,?)',(rid,name.strip(),access,1,max(1,min(max_devices,10000)),brand_name.strip() or 'BBL.BOXTV',now_iso())); c.commit(); c.close()
    return RedirectResponse(f'/admin/resellers?key={key}',303)

@app.post('/admin/resellers/{rid}/toggle')
def reseller_toggle(rid:str,key:str):
    if not admin_ok(key): raise HTTPException(401)
    c=db_connect(); cur=execute(c,'SELECT enabled FROM resellers WHERE id=?',(rid,)); r=rowd(cur.fetchone(),cur)
    if not r: c.close(); raise HTTPException(404)
    execute(c,'UPDATE resellers SET enabled=? WHERE id=?',(0 if r['enabled'] else 1,rid)); c.commit(); c.close()
    return RedirectResponse(f'/admin/resellers?key={key}',303)

def reseller_by_token(token:str):
    c=db_connect(); cur=execute(c,'SELECT * FROM resellers WHERE access_key=? AND enabled=1',(token,)); r=rowd(cur.fetchone(),cur); return c,r

@app.get('/revenda',response_class=HTMLResponse)
def reseller_dashboard(token:str=''):
    c,r=reseller_by_token(token)
    if not r:
        c.close(); return page('Revenda','<form><input name="token" type="password" placeholder="Chave da revenda"><button>Entrar</button></form>')
    cur=execute(c,'SELECT * FROM devices WHERE reseller_id=? ORDER BY created_at DESC',(r['id'],)); devices=[rowd(x,cur) for x in cur.fetchall()]
    cur=execute(c,'SELECT * FROM activation_keys WHERE reseller_id=? ORDER BY created_at DESC',(r['id'],)); keys=[rowd(x,cur) for x in cur.fetchall()]; c.close()
    cards=''
    for d in devices:
        state='BLOQUEADO' if d.get('locked') else 'ATIVO'; action='Desbloquear' if d.get('locked') else 'Bloquear'
        cards += f'<div class="card"><b>{d.get("display_name") or d["id"]}</b><br><span class="muted">{d["id"]} - {state} - ultimo acesso {d.get("last_seen") or "-"}</span><form method="post" action="/revenda/device/{d["id"]}/toggle?token={token}"><button>{action}</button></form></div>'
    kcards=''.join(f'<div class="card"><b>{x["key"]}</b><br><span class="muted">{x.get("label") or ""}</span></div>' for x in keys)
    body=f'<h2>Revenda: {r["name"]}</h2><div class="card"><b>{len(devices)} / {r["max_devices"]}</b> aparelhos</div><div class="card"><form method="post" action="/revenda/activation/create?token={token}"><input name="label" placeholder="Cliente"><button>Gerar codigo</button></form></div><h3>Clientes</h3><div class="grid">{cards or "<div class=card>Nenhum cliente.</div>"}</div><h3>Codigos</h3><div class="grid">{kcards}</div>'
    return page('Revenda',body)

@app.post('/revenda/activation/create')
def reseller_activation_create(token:str,label:str=Form('')):
    c,r=reseller_by_token(token)
    if not r: c.close(); raise HTTPException(401)
    cur=execute(c,'SELECT COUNT(*) AS n FROM devices WHERE reseller_id=?',(r['id'],)); n=rowd(cur.fetchone(),cur)['n']
    if n>=r['max_devices']: c.close(); raise HTTPException(403,'limite de aparelhos atingido')
    activation=f"BBL-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
    execute(c,'INSERT INTO activation_keys(key,enabled,label,created_at,reseller_id) VALUES(?,?,?,?,?)',(activation,1,label.strip(),now_iso(),r['id'])); c.commit(); c.close()
    return RedirectResponse(f'/revenda?token={token}',303)

@app.post('/revenda/device/{did}/toggle')
def reseller_device_toggle(did:str,token:str):
    c,r=reseller_by_token(token)
    if not r: c.close(); raise HTTPException(401)
    cur=execute(c,'SELECT locked FROM devices WHERE id=? AND reseller_id=?',(did,r['id'])); d=rowd(cur.fetchone(),cur)
    if not d: c.close(); raise HTTPException(404)
    execute(c,'UPDATE devices SET locked=? WHERE id=?',(0 if d['locked'] else 1,did)); c.commit(); c.close()
    return RedirectResponse(f'/revenda?token={token}',303)
