"""Pix checkout for customer purchases, kept separate from device subscriptions."""
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from fastapi import Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

MP_ACCESS_TOKEN = (os.getenv("MERCADO_PAGO_ACCESS_TOKEN") or "").strip()
MP_WEBHOOK_SECRET = (os.getenv("MERCADO_PAGO_WEBHOOK_SECRET") or "").strip()
MP_PAYER_EMAIL = (os.getenv("MERCADO_PAGO_PAYER_EMAIL") or "bbl.boxtv@gmail.com").strip()
LAUNCHER_PRICE_CENTS = 2000
PRODUCT_NAME = "BBL Launcher"


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _request_json(method, url, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raise HTTPException(502, "O Mercado Pago não conseguiu processar o pedido.") from exc
    except URLError as exc:
        raise HTTPException(502, "Não foi possível conectar ao Mercado Pago.") from exc


def _mp(method, path, body=None, idempotency_key=None):
    if not MP_ACCESS_TOKEN:
        raise HTTPException(503, "Pagamento temporariamente indisponível.")
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return _request_json(method, "https://api.mercadopago.com" + path, body, headers)


def _signature_valid(req, payment_id):
    if not MP_WEBHOOK_SECRET:
        return True  # Payment state and amount are still verified server-to-server.
    parts = {}
    for item in (req.headers.get("x-signature") or "").split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key.strip()] = value.strip()
    timestamp = parts.get("ts", "")
    received = parts.get("v1", "")
    request_id = req.headers.get("x-request-id") or ""
    if not timestamp or not received:
        return False
    manifest = f"id:{str(payment_id).lower()};request-id:{request_id};ts:{timestamp};"
    digest = hmac.new(MP_WEBHOOK_SECRET.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, received)


class LauncherOrderBody(BaseModel):
    customer_name: str = Field(min_length=2, max_length=100)
    whatsapp: str = Field(min_length=10, max_length=20)
    device_model: str = Field(min_length=2, max_length=100)


def register(app, db_connect, execute, rowd, now_iso, log):
    def init_store_orders():
        conn = db_connect()
        try:
            execute(conn, """CREATE TABLE IF NOT EXISTS store_orders(
                id TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                product TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                whatsapp TEXT NOT NULL,
                device_model TEXT NOT NULL,
                external_reference TEXT UNIQUE NOT NULL,
                provider_payment_id TEXT,
                amount_cents INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                qr_code TEXT NOT NULL DEFAULT '',
                qr_code_base64 TEXT NOT NULL DEFAULT '',
                ticket_url TEXT NOT NULL DEFAULT '',
                activation_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT
            )""")
            conn.commit()
        finally:
            conn.close()

    app.add_event_handler("startup", init_store_orders)

    def _issue_activation_key(conn, order):
        if order.get("activation_key"):
            return order["activation_key"]
        for _ in range(5):
            code = f"BBL-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
            try:
                execute(
                    conn,
                    "INSERT INTO activation_keys(key,enabled,label,created_at,single_use,used_by_device) VALUES(?,?,?,?,1,NULL)",
                    (code, 1, f"Compra BBL Launcher ({order['whatsapp']})", now_iso()),
                )
                execute(
                    conn,
                    "UPDATE store_orders SET activation_key=?,status='approved',updated_at=? WHERE id=?",
                    (code, now_iso(), order["id"]),
                )
                return code
            except Exception:
                conn.rollback()
                # A collision is rare; the next generated code is different.
        raise HTTPException(500, "Não foi possível gerar o código de ativação.")

    def _apply_mp_status(conn, order, mp):
        status = str(mp.get("status") or "pending")
        if status == "approved":
            cents = int((Decimal(str(mp.get("transaction_amount") or "0")) * 100).quantize(Decimal("1")))
            if cents != int(order["amount_cents"]):
                raise HTTPException(400, "Valor confirmado diferente do pedido.")
            current = rowd(execute(conn, "SELECT * FROM store_orders WHERE id=?", (order["id"],)).fetchone())
            _issue_activation_key(conn, current or order)
        else:
            execute(conn, "UPDATE store_orders SET status=?,updated_at=? WHERE id=?", (status, now_iso(), order["id"]))
        conn.commit()

    @app.get("/api/store/catalog")
    def launcher_catalog():
        return {"items": [{"id": "bbl_launcher", "name": PRODUCT_NAME, "price_cents": LAUNCHER_PRICE_CENTS, "currency": "BRL", "includes_apps": True}]}

    @app.post("/api/store/orders")
    def create_launcher_order(body: LauncherOrderBody, req: Request):
        # Prevent arbitrarily many Pix charges from the same WhatsApp number.
        digits = "".join(ch for ch in body.whatsapp if ch.isdigit())
        if len(digits) < 10 or len(digits) > 13:
            raise HTTPException(400, "Informe um WhatsApp válido com DDD.")
        conn = db_connect()
        try:
            recent = rowd(execute(conn, "SELECT COUNT(*) AS n FROM store_orders WHERE whatsapp=? AND created_at>?", (digits, (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat())).fetchone())
            if int((recent or {}).get("n") or 0) >= 3:
                raise HTTPException(429, "Aguarde alguns minutos antes de gerar outro Pix.")
            order_id = secrets.token_hex(12)
            access_token = secrets.token_urlsafe(32)
            external_reference = "BBL-LAUNCHER-" + secrets.token_hex(12).upper()
            now = now_iso()
            execute(
                conn,
                """INSERT INTO store_orders(id,access_token,product,customer_name,whatsapp,device_model,external_reference,amount_cents,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (order_id, access_token, "bbl_launcher", body.customer_name.strip(), digits, body.device_model.strip(), external_reference, LAUNCHER_PRICE_CENTS, "creating", now, now),
            )
            conn.commit()
            payment_body = {
                "transaction_amount": LAUNCHER_PRICE_CENTS / 100,
                "description": "BBL.BOXTV - BBL Launcher com aplicativos inclusos",
                "payment_method_id": "pix",
                "external_reference": external_reference,
                "payer": {"email": MP_PAYER_EMAIL},
                "notification_url": str(req.base_url).rstrip("/") + "/api/store/mercadopago/webhook",
                "date_of_expiration": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec="seconds"),
            }
            try:
                mp = _mp("POST", "/v1/payments", payment_body, secrets.token_hex(16))
            except Exception:
                execute(conn, "UPDATE store_orders SET status='error',updated_at=? WHERE id=?", (now_iso(), order_id))
                conn.commit()
                raise
            details = ((mp.get("point_of_interaction") or {}).get("transaction_data") or {})
            qr_code = str(details.get("qr_code") or "").strip()
            if not qr_code:
                execute(conn, "UPDATE store_orders SET status='error',updated_at=? WHERE id=?", (now_iso(), order_id))
                conn.commit()
                raise HTTPException(502, "O Mercado Pago não retornou o Pix para este pedido.")
            execute(
                conn,
                """UPDATE store_orders SET provider_payment_id=?,status=?,qr_code=?,qr_code_base64=?,ticket_url=?,expires_at=?,updated_at=? WHERE id=?""",
                (str(mp.get("id") or ""), str(mp.get("status") or "pending"), qr_code, details.get("qr_code_base64") or "", details.get("ticket_url") or "", mp.get("date_of_expiration") or "", now_iso(), order_id),
            )
            conn.commit()
            return {
                "order_id": order_id,
                "order_token": access_token,
                "product": PRODUCT_NAME,
                "amount_cents": LAUNCHER_PRICE_CENTS,
                "status": str(mp.get("status") or "pending"),
                "qr_code": qr_code,
                "qr_code_base64": details.get("qr_code_base64") or "",
                "ticket_url": details.get("ticket_url") or "",
                "expires_at": mp.get("date_of_expiration") or "",
                "status_url": f"/api/store/orders/{order_id}",
            }
        finally:
            conn.close()

    @app.get("/api/store/orders/{order_id}")
    def get_launcher_order(order_id: str, token: str):
        conn = db_connect()
        try:
            order = rowd(execute(conn, "SELECT * FROM store_orders WHERE id=?", (order_id,)).fetchone())
            if not order or not secrets.compare_digest(str(order.get("access_token") or ""), token):
                raise HTTPException(404, "Pedido não encontrado.")
            if order.get("provider_payment_id") and order.get("status") not in ("approved", "cancelled", "rejected", "refunded", "charged_back"):
                try:
                    mp = _mp("GET", f"/v1/payments/{order['provider_payment_id']}")
                    _apply_mp_status(conn, order, mp)
                    order = rowd(execute(conn, "SELECT * FROM store_orders WHERE id=?", (order_id,)).fetchone()) or order
                except HTTPException:
                    pass
            out = {"order_id": order_id, "product": PRODUCT_NAME, "amount_cents": int(order["amount_cents"]), "status": order["status"], "expires_at": order.get("expires_at") or ""}
            if order["status"] == "approved":
                out["activation_code"] = order.get("activation_key") or ""
            return out
        finally:
            conn.close()

    @app.post("/api/store/mercadopago/webhook")
    async def launcher_payment_webhook(req: Request):
        try:
            body = await req.json()
        except Exception:
            body = {}
        payment_id = str((body.get("data") or {}).get("id") or req.query_params.get("data.id") or "")
        if not payment_id:
            return {"ok": True, "ignored": "no_data_id"}
        if not _signature_valid(req, payment_id):
            raise HTTPException(401, "Assinatura de webhook inválida.")
        mp = _mp("GET", f"/v1/payments/{payment_id}")
        external_reference = str(mp.get("external_reference") or "")
        conn = db_connect()
        try:
            order = rowd(execute(conn, "SELECT * FROM store_orders WHERE external_reference=?", (external_reference,)).fetchone())
            if not order or str(order.get("provider_payment_id") or "") != payment_id:
                return {"ok": True, "ignored": "order_not_linked"}
            _apply_mp_status(conn, order, mp)
            return {"ok": True, "status": str(mp.get("status") or "unknown")}
        finally:
            conn.close()


CHECKOUT_PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#09111f"><title>BBL Launcher</title>
<style>
:root{color-scheme:dark;--bg:#09111f;--panel:#111d2d;--gold:#f3bd55;--text:#f5f7fb;--muted:#a9b6c8}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse at top,#172c49 0,#09111f 55%);color:var(--text);font:16px/1.45 system-ui,sans-serif;display:grid;place-items:center;padding:18px}
main{width:min(100%,520px)}.card{background:#101d2c;border:1px solid #ffffff20;border-radius:22px;padding:24px;box-shadow:0 20px 65px #0008}
.brand{text-align:center}.mark{display:inline-grid;place-items:center;width:52px;height:52px;border-radius:16px;background:linear-gradient(145deg,#f7d58d,#d99125);color:#101827;font-weight:900;font-size:20px}
h1{font-size:24px;margin:12px 0 2px}.muted{color:var(--muted);font-size:14px}.price{font-size:28px;color:var(--gold);font-weight:850;margin:16px 0}
label{display:block;font-size:13px;margin:13px 0 5px;color:#d9e2ef}input{width:100%;padding:12px;border:1px solid #ffffff2b;border-radius:10px;background:#17263a;color:white;font:inherit}
button{width:100%;padding:13px;border:0;border-radius:11px;background:var(--gold);color:#1b1c20;font:inherit;font-weight:800;margin-top:16px;cursor:pointer}
#payment{display:none;margin-top:20px;border-top:1px solid #ffffff20;padding-top:18px}.qr{display:block;max-width:220px;width:100%;margin:14px auto;border-radius:12px;background:white;padding:8px}
textarea{width:100%;min-height:82px;padding:10px;border:1px solid #ffffff25;border-radius:10px;background:#17263a;color:white;resize:vertical}
.status{text-align:center;padding:12px;border-radius:10px;background:#17263a;margin:14px 0}.error{color:#ffaaaa}.success{color:#a9f2c8}.small{font-size:12px;color:var(--muted);margin-top:14px}
</style></head><body><main><section class="card">
<header class="brand"><div class="mark">BBL</div><h1>BBL Launcher</h1><div class="muted">Aplicativos da oferta incluídos</div><div class="price">R$ 20,00</div></header>
<div id="formArea"><label>Seu nome</label><input id="name" autocomplete="name" required>
<label>WhatsApp com DDD</label><input id="phone" inputmode="tel" autocomplete="tel" placeholder="(21) 99999-9999" required>
<label>Marca e modelo da TV Box</label><input id="model" placeholder="Ex.: MXQ Pro 4K" required>
<button id="pay">Gerar Pix</button><p class="small">O código de ativação aparece nesta página depois da confirmação do Mercado Pago.</p></div>
<section id="payment"><h2>Pagamento Pix</h2><img id="qr" class="qr" alt="QR Code Pix"><div class="muted">Escaneie o QR Code ou copie o código Pix abaixo.</div><textarea id="pix" readonly></textarea><button id="copy" type="button">Copiar código Pix</button><div id="status" class="status">Aguardando pagamento…</div><div id="activation" hidden></div></section>
<div id="error" class="error" role="alert"></div></section></main>
<script>
const byId=id=>document.getElementById(id);let order=null,timer=null;
byId("pay").addEventListener("click",async()=>{
  byId("error").textContent="";
  const data={customer_name:byId("name").value.trim(),whatsapp:byId("phone").value.trim(),device_model:byId("model").value.trim()};
  if(Object.values(data).some(v=>!v)){byId("error").textContent="Preencha seu nome, WhatsApp e modelo do aparelho.";return}
  byId("pay").disabled=true;byId("pay").textContent="Gerando Pix…";
  try{
    const r=await fetch("/api/store/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    const result=await r.json();if(!r.ok)throw new Error(typeof result.detail==="string"?result.detail:"Não foi possível gerar o Pix.");
    order=result;byId("formArea").hidden=true;byId("payment").style.display="block";
    byId("pix").value=result.qr_code;
    if(result.qr_code_base64)byId("qr").src="data:image/png;base64,"+result.qr_code_base64;else byId("qr").hidden=true;
    timer=setInterval(refresh,4000);refresh();
  }catch(e){byId("error").textContent=e.message;byId("pay").disabled=false;byId("pay").textContent="Gerar Pix"}
});
byId("copy").addEventListener("click",async()=>{await navigator.clipboard.writeText(byId("pix").value);byId("copy").textContent="Pix copiado"});
async function refresh(){
  if(!order)return;
  try{
    const r=await fetch(order.status_url+"?token="+encodeURIComponent(order.order_token));const s=await r.json();if(!r.ok)return;
    if(s.status==="approved"){clearInterval(timer);byId("status").innerHTML='<span class="success">Pagamento aprovado!</span>';byId("activation").hidden=false;byId("activation").innerHTML="<h3>Seu código de ativação</h3><div class='status success' style='font-size:23px;font-weight:850'>"+s.activation_code+"</div><div class='muted'>Digite esse código na BBL Launcher no aparelho informado.</div>"}
    else if(["cancelled","rejected","refunded"].includes(s.status)){clearInterval(timer);byId("status").textContent="Este pagamento não foi aprovado. Volte ao atendimento para receber ajuda."}
  }catch(_){}
}
</script></body></html>"""


@app.get("/launcher", response_class=HTMLResponse)
def launcher_checkout_page():
    return HTMLResponse(CHECKOUT_PAGE)
